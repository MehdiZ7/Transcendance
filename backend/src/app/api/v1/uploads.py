"""POST /uploads/images: the only way a file gets on the server. What is stored
and how it is served is in app/core/uploads.py."""

import asyncio
import logging
import os
from pathlib import Path
from typing import BinaryIO

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.ratelimit import limit_uploads
from app.core.security import get_current_user
from app.core.uploads import (
    ImageTooBig,
    detect_image_extension,
    new_upload_path,
    reencode_image,
    usage,
)
from app.models import User
from app.schemas.upload import UploadedImage

logger = logging.getLogger(__name__)

router = APIRouter()


class _TooLarge(Exception):
    pass


class _InvalidImage(Exception):
    pass


def _store(source: BinaryIO, destination: Path, limit: int, extension: str) -> None:
    """Write `source` to `destination` through a temporary name, so a half-written
    or oversized file is never left where it could be served. `source` is Starlette's
    own buffer - the whole body is already in hand by the time a route runs, so this
    reads it once rather than pretending to stream it.

    Re-encoded through Pillow before being written: an error from that step
    alone means the upload itself is bad, so it's the only one turned into
    _InvalidImage (or _TooLarge, for ImageTooBig). Anything past OSError and
    Image.DecompressionBombError is still refused, not a 500, but logged: it
    may as well be a case reencode_image does not handle. The same exceptions
    from mkdir/write/replace mean something is wrong with the server (a full
    disk, a permissions issue) and are left to propagate as themselves - the
    caller should not mistake those for a bad upload."""
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        data = source.read(limit + 1)
        if len(data) > limit:
            raise _TooLarge
        try:
            data = reencode_image(data, extension)
        except ImageTooBig:
            raise _TooLarge from None
        except (OSError, Image.DecompressionBombError) as exc:
            raise _InvalidImage from exc
        except Exception as exc:
            logger.exception("unexpected error re-encoding a .%s upload", extension)
            raise _InvalidImage from exc
        if len(data) > limit:
            raise _TooLarge
        partial.write_bytes(data)
        os.replace(partial, destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


_REENCODE_SLOTS = asyncio.Semaphore(2)

@router.post("/uploads/images", status_code=201, dependencies=[Depends(limit_uploads)])
async def upload_image(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
) -> UploadedImage:
    """Store an image and answer its path, to use as an image of a listing or as
    the avatar. 413 over `max_upload_bytes`, 415 if the file does not start like,
    or does not actually decode as, a PNG, JPEG, GIF or WebP, 429 past the daily
    count, 409 past the storage cap."""
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image too large")

    extension = detect_image_extension(await file.read(16))
    if extension is None:
        raise HTTPException(status_code=415, detail="Unsupported image type")
    await file.seek(0)

    recent, total = await run_in_threadpool(usage, current_user.public_id)
    if recent >= settings.quota_uploads_per_day:
        raise HTTPException(status_code=429, detail="Too many images uploaded today")
    if total >= settings.quota_upload_bytes:
        raise HTTPException(status_code=409, detail="Image storage is full")

    destination, public_path = new_upload_path(current_user.public_id, extension)
    try:
        async with _REENCODE_SLOTS:
            await run_in_threadpool(_store, file.file, destination, settings.max_upload_bytes, extension)
    except _TooLarge:
        raise HTTPException(status_code=413, detail="Image too large") from None
    except _InvalidImage:
        raise HTTPException(status_code=415, detail="Unsupported image type") from None
    return UploadedImage(path=public_path)
