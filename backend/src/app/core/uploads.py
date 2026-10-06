"""Image uploads: what is accepted, where it is stored, and which image
references the API accepts afterwards.

A file goes under `<media_root>/images/<owner public_id>/<random>.<ext>` and
is served by nginx at `/media/images/...`; the database only keeps that path.
One directory per owner makes the quotas a directory scan (no table) and lets
a user's files be removed with the user. A file uploaded but never attached
to a listing or an avatar is removed later by purge_orphaned_uploads.

The type comes from the first bytes of the file, never from the file name or
the Content-Type the client sent. Every file is then decoded and re-saved
with Pillow: this confirms it truly is a well-formed image, not just
something whose start looks like one, and drops whatever metadata it
carried - EXIF GPS position on a phone photo, in particular.
"""

import io
import logging
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageOps, ImageSequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ListingImage, User

logger = logging.getLogger(__name__)

IMAGES_DIR = "images"
PUBLIC_PREFIX = "/media/images"
DAY = 24 * 60 * 60

_OWN_UPLOAD = re.compile(
    r"^/media/images/(?P<owner>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"/[0-9a-f]{32}\.(?:jpg|png|webp|gif)$"
)
_FRONT_ASSET = re.compile(r"^/mock/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


def detect_image_extension(head: bytes) -> str | None:
    """The extension for what the first bytes say the file is, or None."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


_PIL_FORMAT = {"jpg": "JPEG", "png": "PNG", "gif": "GIF", "webp": "WEBP"}
_SAVE_KWARGS = {"JPEG": {"quality": 90}, "WEBP": {"quality": 90}}

MAX_PIXELS = 40_000_000
MAX_FRAMES = 200
MAX_TOTAL_PIXELS = 50_000_000


class ImageTooBig(ValueError):
    """Dimensions or frame count past what reencode_image agrees to decode."""


def reencode_image(data: bytes, extension: str) -> bytes:
    """Decode `data` (already known, from its first bytes, to plausibly be
    `extension`) and re-save it clean. This confirms it really is a well-formed
    image - not just something whose start looks right - and drops whatever
    metadata it carried. A photo's EXIF orientation is baked into the pixels
    first, so it still looks right once that tag is gone.

    Raises OSError (Pillow's own exception for anything it cannot open or
    decode) or Image.DecompressionBombError (dimensions far past what a photo
    needs) for anything that isn't a real, reasonably sized image - the
    caller should treat both as a rejected upload.

    An animated GIF is only decoded frame by frame to check it is genuinely
    well-formed, then stored as received: GIF does not carry EXIF GPS data
    the way a phone photo does, and Pillow's GIF writer is prone to visibly
    degrading an animation on re-save (palette, frame disposal), which isn't
    worth it for metadata that was never there. An animated WebP or PNG can
    carry EXIF, and Pillow round-trips their animation cleanly, so those are
    genuinely re-saved frame by frame, the same as a static image."""
    save_format = _PIL_FORMAT[extension]
    with Image.open(io.BytesIO(data)) as image:
        # Read from the header, before anything is decoded: a few KB of PNG or GIF can
        # otherwise unpack to gigabytes, or to hours of compositing. 40 MP is past any
        # phone photo; 50 M pixels over all frames still allows any normal animation.
        width, height = image.size
        n_frames = getattr(image, "n_frames", 1)
        if (
            width * height > MAX_PIXELS
            or n_frames > MAX_FRAMES
            or width * height * n_frames > MAX_TOTAL_PIXELS
        ):
            raise ImageTooBig

        # An MPO (a JPEG with more pictures behind it: a camera's large preview,
        # a depth or gain map) opens as multi-frame; only the first is the photo.
        animated = n_frames > 1 and image.format != "MPO"

        if extension == "gif" and animated:
            for frame in ImageSequence.Iterator(image):
                frame.load()
            return data

        if animated:
            frames: list[Image.Image] = []
            durations: list[int] = []
            for frame in ImageSequence.Iterator(image):
                durations.append(frame.info.get("duration", 100))
                copy = frame.copy()
                frames.append(ImageOps.exif_transpose(copy) or copy)
            out = io.BytesIO()
            frames[0].save(
                out,
                format=save_format,
                save_all=True,
                append_images=frames[1:],
                loop=image.info.get("loop", 0),
                duration=durations,
                **_SAVE_KWARGS.get(save_format, {}),
            )
            return out.getvalue()

        image.load()
        transposed = ImageOps.exif_transpose(image) or image
        out = io.BytesIO()
        transposed.save(out, format=save_format, **_SAVE_KWARGS.get(save_format, {}))
        return out.getvalue()


def owner_dir(owner: uuid.UUID) -> Path:
    return Path(settings.media_root) / IMAGES_DIR / str(owner)


def usage(owner: uuid.UUID) -> tuple[int, int]:
    """(files stored in the last 24 h, bytes stored in total) for this owner."""
    directory = owner_dir(owner)
    if not directory.is_dir():
        return 0, 0
    recent, total, since = 0, 0, time.time() - DAY
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file(follow_symlinks=False):
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                # Raced with a concurrent delete (an avatar/listing cleanup,
                # or the hourly purge) - gone means it no longer counts.
                continue
            total += info.st_size
            recent += info.st_mtime > since
    return recent, total


def new_upload_path(owner: uuid.UUID, extension: str) -> tuple[Path, str]:
    """(where to write it, the public path to store), with a random name."""
    name = f"{uuid.uuid4().hex}.{extension}"
    return owner_dir(owner) / name, f"{PUBLIC_PREFIX}/{owner}/{name}"


async def purge_orphaned_uploads(session: AsyncSession, older_than: float) -> int:
    """Remove uploaded files that nothing ever attached: an upload the caller
    abandoned before submitting the listing or profile form it was for.
    Only files last modified more than `older_than` seconds ago are removed,
    so a file still mid-flow is never at risk. Returns how many were removed.

    What is "referenced" comes straight from the two columns that can hold an
    own-upload path - deliberately not restricted to active listings: a
    moderator-deleted listing (see reports.py) keeps its images on disk on
    purpose, and this must not undo that."""
    referenced = set(
        await session.scalars(
            select(ListingImage.storage_path).where(
                ListingImage.storage_path.startswith(PUBLIC_PREFIX)
            )
        )
    )
    referenced.update(
        await session.scalars(
            select(User.avatar_path).where(User.avatar_path.startswith(PUBLIC_PREFIX))
        )
    )

    root = Path(settings.media_root) / IMAGES_DIR
    if not root.is_dir():
        return 0

    cutoff = time.time() - older_than
    removed = 0
    with os.scandir(root) as owners:
        for owner in owners:
            if not owner.is_dir(follow_symlinks=False):
                continue
            with os.scandir(owner.path) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if entry.stat(follow_symlinks=False).st_mtime > cutoff:
                        continue
                    if f"{PUBLIC_PREFIX}/{owner.name}/{entry.name}" in referenced:
                        continue
                    os.unlink(entry.path)
                    removed += 1
    return removed


def delete_own_upload(ref: str, owner: uuid.UUID) -> None:
    """Remove one of `owner`'s own uploaded files from disk, given its public
    path. A no-op for anything that isn't exactly that - a front asset, an
    external URL, or someone else's file - so it's safe to call on whatever a
    field used to hold. Best-effort: logged and swallowed on failure, since
    the row that pointed at this file has already been updated by the time
    this runs and a stray file is not worth failing the request over."""
    match = _OWN_UPLOAD.match(ref)
    if match is None or match["owner"] != str(owner):
        return
    try:
        (owner_dir(owner) / Path(ref).name).unlink(missing_ok=True)
    except OSError:
        logger.exception("could not delete %s", ref)


def own_upload_missing(ref: str) -> bool:
    """Whether `ref` looks like one of our own uploads but the file is no
    longer on disk. False for anything else - a front asset or an external
    URL was never ours to lose. Used to clean up a dangling reference, e.g.
    when restoring a listing whose seller had already deleted it (and its
    files, independently of whatever report is being resolved) themselves."""
    match = _OWN_UPLOAD.match(ref)
    if match is None:
        return False
    return not (Path(settings.media_root) / IMAGES_DIR / match["owner"] / Path(ref).name).is_file()


def is_allowed_image_ref(ref: str, owner: uuid.UUID) -> bool:
    """Whether the API accepts `ref` as an image of `owner`: one of their own
    uploads, a static asset of the front (placeholders, demo data), or an https
    URL on an allowed host."""
    match = _OWN_UPLOAD.match(ref)
    if match:
        return match["owner"] == str(owner)
    if _FRONT_ASSET.match(ref):
        return ".." not in ref.split("/")
    parts = urlsplit(ref)
    hosts = {h.strip() for h in settings.allowed_image_hosts.split(",") if h.strip()}
    return (
        parts.scheme == "https"
        and parts.hostname in hosts
        and parts.username is None
        and parts.password is None
    )
