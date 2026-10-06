"""POST /uploads/images and the image references the API accepts afterwards."""

import contextlib
import io
import os
import re
import time
import uuid

import pytest
from PIL import Image

from app.api.v1.uploads import _InvalidImage, _store, _TooLarge
from app.core.config import settings
from app.core.uploads import (
    DAY,
    MAX_FRAMES,
    ImageTooBig,
    delete_own_upload,
    detect_image_extension,
    is_allowed_image_ref,
    own_upload_missing,
    purge_orphaned_uploads,
    reencode_image,
    usage,
)


def _make_image(fmt: str, size: tuple[int, int] = (2, 2)) -> bytes:
    """A small, genuinely decodable image - uploads are now re-encoded, so a
    bare signature followed by padding (what these used to be) is rejected."""
    out = io.BytesIO()
    Image.new("RGB", size, (200, 50, 50)).save(out, format=fmt)
    return out.getvalue()


PNG = _make_image("PNG")
JPEG = _make_image("JPEG")
GIF = _make_image("GIF")
WEBP = _make_image("WEBP")

URL = "/api/v1/uploads/images"


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    return tmp_path


def _upload(client, content, name="photo.png", content_type="image/png"):
    return client.post(URL, files={"file": (name, content, content_type)})


def _stored(media, user):
    directory = media / "images" / str(user.public_id)
    return sorted(directory.iterdir()) if directory.exists() else []


# ── the endpoint ──────────────────────────────────────────────────


async def test_upload_requires_authentication(client, media):
    response = await _upload(client, PNG)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("content", "extension"), [(PNG, "png"), (JPEG, "jpg"), (GIF, "gif"), (WEBP, "webp")]
)
async def test_upload_stores_each_image_type_and_answers_its_path(
    client, create_user, login_as, media, content, extension
):
    me = await create_user()
    login_as(me)

    response = await _upload(client, content)

    assert response.status_code == 201
    path = response.json()["path"]
    assert re.fullmatch(rf"/media/images/{me.public_id}/[0-9a-f]{{32}}\.{extension}", path)
    [stored] = _stored(media, me)
    assert path.endswith(stored.name)
    with Image.open(stored) as decoded:
        decoded.load()
        assert decoded.size == (2, 2)


async def test_the_type_comes_from_the_bytes_not_the_name_or_content_type(
    client, create_user, login_as, media
):
    login_as(await create_user())

    fake = await _upload(client, b"just some text", name="photo.png", content_type="image/png")
    real = await _upload(client, PNG, name="notes.txt", content_type="text/plain")

    assert fake.status_code == 415
    assert real.status_code == 201
    assert real.json()["path"].endswith(".png")


async def test_an_empty_file_is_refused(client, create_user, login_as, media):
    login_as(await create_user())

    assert (await _upload(client, b"")).status_code == 415


async def test_a_file_that_only_has_the_right_signature_is_refused(client, create_user, login_as, media):
    # Passes the cheap header sniff but doesn't actually decode: caught
    # further in, by reencode_image, not by detect_image_extension.
    me = await create_user()
    login_as(me)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    response = await _upload(client, fake_png)

    assert response.status_code == 415
    assert _stored(media, me) == []


async def test_a_filesystem_error_is_not_reported_as_a_bad_upload(
    client, create_user, login_as, media, monkeypatch
):
    # A real image that fails to write (full disk, permissions) is a server
    # problem, not a bad upload - it must not come back as a 415.
    login_as(await create_user())

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        await _upload(client, PNG)


async def test_the_client_file_name_never_reaches_the_disk(client, create_user, login_as, media):
    me = await create_user()
    login_as(me)

    response = await _upload(client, PNG, name="../../../etc/evil.png")

    assert response.status_code == 201
    assert [p.parent for p in _stored(media, me)] == [media / "images" / str(me.public_id)]
    assert not (media.parent / "evil.png").exists()


async def test_an_oversized_image_is_refused_and_leaves_nothing_behind(
    client, create_user, login_as, media, monkeypatch
):
    me = await create_user()
    login_as(me)
    monkeypatch.setattr(settings, "max_upload_bytes", len(PNG))

    at_limit = await _upload(client, PNG)
    over = await _upload(client, PNG + b"\x00")  # one byte past the raw cap

    assert at_limit.status_code == 201
    assert over.status_code == 413
    assert len(_stored(media, me)) == 1  # no leftover, no .part file


async def test_the_daily_upload_quota_answers_429_and_old_files_do_not_count(
    client, create_user, login_as, media, monkeypatch
):
    me = await create_user()
    login_as(me)
    monkeypatch.setattr(settings, "quota_uploads_per_day", 2)
    first = await _upload(client, PNG)
    await _upload(client, PNG)
    assert (await _upload(client, PNG)).status_code == 429

    # one of them is now more than a day old: it leaves the window
    old = _stored(media, me)[0]
    os.utime(old, (time.time() - DAY - 60,) * 2)

    assert first.status_code == 201
    assert (await _upload(client, PNG)).status_code == 201


async def test_the_storage_cap_answers_409(client, create_user, login_as, media, monkeypatch):
    login_as(await create_user())
    monkeypatch.setattr(settings, "quota_upload_bytes", len(PNG))
    await _upload(client, PNG)

    assert (await _upload(client, PNG)).status_code == 409


async def test_another_users_files_do_not_count_for_my_quota(
    client, create_user, login_as, media, monkeypatch
):
    monkeypatch.setattr(settings, "quota_uploads_per_day", 1)
    login_as(await create_user())
    await _upload(client, PNG)
    login_as(await create_user())

    assert (await _upload(client, PNG)).status_code == 201


async def test_uploads_are_rate_limited(client, create_user, login_as, media, monkeypatch):
    login_as(await create_user())
    monkeypatch.setattr(settings, "rate_uploads_per_hour", 1)

    first = await _upload(client, PNG)
    second = await _upload(client, PNG)

    assert (first.status_code, second.status_code) == (201, 429)


# ── using the path ────────────────────────────────────────────────


async def test_a_listing_can_use_the_users_own_upload(
    client, create_user, login_as, media, listing_payload
):
    login_as(await create_user())
    path = (await _upload(client, JPEG)).json()["path"]

    response = await client.post("/api/v1/listings", json=await listing_payload(image_urls=[path]))

    assert response.status_code == 201
    assert response.json()["images"][0]["storage_path"] == path


async def test_a_listing_cannot_use_someone_elses_upload(
    client, create_user, login_as, media, listing_payload
):
    login_as(await create_user())
    theirs = (await _upload(client, JPEG)).json()["path"]
    login_as(await create_user())

    response = await client.post("/api/v1/listings", json=await listing_payload(image_urls=[theirs]))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        "https://evil.example/a.jpg",
        "http://cdn.intra.42.fr/a.jpg",
        "https://user:pw@cdn.intra.42.fr/a.jpg",
        "data:image/png;base64,AAAA",
        "javascript:alert(1)",
        "/mock/../../etc/passwd",
        "/media/images/not-a-uuid/" + "a" * 32 + ".png",
        "relative/path.png",
    ],
)
async def test_a_listing_refuses_other_image_references(
    client, create_user, login_as, listing_payload, bad
):
    login_as(await create_user())

    response = await client.post("/api/v1/listings", json=await listing_payload(image_urls=[bad]))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "good", ["/mock/listings/keychron-k2.jpg", "/mock/placeholders/cat-objet.svg",
             "https://cdn.intra.42.fr/users/a.jpg?w=150"]
)
async def test_a_listing_accepts_front_assets_and_allowed_hosts(
    client, create_user, login_as, listing_payload, good
):
    login_as(await create_user())

    response = await client.post("/api/v1/listings", json=await listing_payload(image_urls=[good]))

    assert response.status_code == 201


async def test_the_avatar_can_be_an_own_upload_but_not_someone_elses(
    client, create_user, login_as, media
):
    me = await create_user()
    login_as(me)
    mine = (await _upload(client, PNG)).json()["path"]
    other = await create_user()
    login_as(other)
    theirs = (await _upload(client, PNG)).json()["path"]
    login_as(me)

    ok = await client.patch("/api/v1/users/me", json={"avatar_path": mine})
    refused = await client.patch("/api/v1/users/me", json={"avatar_path": theirs})

    assert ok.status_code == 200
    assert refused.status_code == 422


async def test_replacing_the_avatar_deletes_the_old_upload(client, create_user, login_as, media):
    me = await create_user()
    login_as(me)
    first = (await _upload(client, PNG)).json()["path"]
    await client.patch("/api/v1/users/me", json={"avatar_path": first})
    second = (await _upload(client, PNG)).json()["path"]

    response = await client.patch("/api/v1/users/me", json={"avatar_path": second})

    assert response.status_code == 200
    stored = _stored(media, me)
    assert len(stored) == 1
    assert second.endswith(stored[0].name)


async def test_clearing_the_avatar_deletes_the_old_upload(client, create_user, login_as, media):
    me = await create_user()
    login_as(me)
    path = (await _upload(client, PNG)).json()["path"]
    await client.patch("/api/v1/users/me", json={"avatar_path": path})

    response = await client.patch("/api/v1/users/me", json={"avatar_path": None})

    assert response.status_code == 200
    assert _stored(media, me) == []


async def test_sending_back_the_same_avatar_does_not_delete_it(client, create_user, login_as, media):
    me = await create_user()
    login_as(me)
    path = (await _upload(client, PNG)).json()["path"]
    await client.patch("/api/v1/users/me", json={"avatar_path": path})

    response = await client.patch("/api/v1/users/me", json={"avatar_path": path, "bio": "hey"})

    assert response.status_code == 200
    assert len(_stored(media, me)) == 1


async def test_switching_to_an_external_avatar_still_deletes_the_old_upload(
    client, create_user, login_as, media
):
    me = await create_user()
    login_as(me)
    path = (await _upload(client, PNG)).json()["path"]
    await client.patch("/api/v1/users/me", json={"avatar_path": path})

    response = await client.patch(
        "/api/v1/users/me", json={"avatar_path": "https://cdn.intra.42.fr/a.jpg"}
    )

    assert response.status_code == 200
    assert _stored(media, me) == []


async def test_the_avatar_refuses_base64_but_accepts_its_current_value_back(
    client, create_user, login_as
):
    me = await create_user(avatar_path="/legacy/avatar.png")
    login_as(me)

    data_uri = await client.patch("/api/v1/users/me", json={"avatar_path": "data:image/png;base64,AAAA"})
    echoed = await client.patch("/api/v1/users/me", json={"avatar_path": "/legacy/avatar.png"})
    cleared = await client.patch("/api/v1/users/me", json={"avatar_path": None})

    assert data_uri.status_code == 422
    assert echoed.status_code == 200  # the profile form sends the value it loaded
    assert cleared.status_code == 200


# ── units ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("head", "expected"),
    [(PNG, "png"), (JPEG, "jpg"), (GIF, "gif"), (b"GIF87a", "gif"), (WEBP, "webp"),
     (b"RIFF\x00\x00\x00\x00WAVEfmt ", None), (b"", None), (b"%PDF-1.7", None), (b"<svg", None)],
)
def test_detect_image_extension(head, expected):
    assert detect_image_extension(head) == expected


@pytest.mark.parametrize(
    ("content", "fmt", "extension"),
    [(PNG, "PNG", "png"), (JPEG, "JPEG", "jpg"), (GIF, "GIF", "gif"), (WEBP, "WEBP", "webp")],
)
def test_reencode_image_keeps_a_real_image_decodable(content, fmt, extension):
    reencoded = reencode_image(content, extension)

    with Image.open(io.BytesIO(reencoded)) as decoded:
        decoded.load()
        assert decoded.format == fmt
        assert decoded.size == (2, 2)


def test_reencode_image_rejects_a_file_that_only_has_the_right_signature():
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # right signature, not a real PNG

    with pytest.raises(OSError):
        reencode_image(fake_png, "png")


def test_reencode_image_applies_exif_orientation_before_dropping_it():
    image = Image.new("RGB", (4, 2), (10, 20, 30))  # 4 wide, 2 tall
    exif = image.getexif()
    exif[0x0112] = 6  # "rotate 90° CW to display" - width and height swap
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)

    reencoded = reencode_image(out.getvalue(), "jpg")

    with Image.open(io.BytesIO(reencoded)) as after:
        assert after.size == (2, 4)
        assert not after.getexif()


def test_reencode_image_keeps_every_frame_of_an_animated_gif():
    frames = [Image.new("RGB", (2, 2), color) for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
    out = io.BytesIO()
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:])
    animated = out.getvalue()

    reencoded = reencode_image(animated, "gif")

    assert reencoded == animated  # not re-saved: kept as received, only validated
    with Image.open(io.BytesIO(reencoded)) as decoded:
        assert decoded.n_frames == 3


def test_reencode_image_strips_exif_and_keeps_every_frame_of_an_animated_webp():
    # Unlike GIF, an animated WebP can carry EXIF - it must actually be
    # stripped, not just validated and passed through.
    frames = [Image.new("RGB", (2, 2), color) for color in [(255, 0, 0), (0, 255, 0)]]
    exif = frames[0].getexif()
    exif[0x0112] = 1  # any tag proves EXIF was present at all
    out = io.BytesIO()
    frames[0].save(out, format="WEBP", save_all=True, append_images=frames[1:], exif=exif)
    animated = out.getvalue()

    reencoded = reencode_image(animated, "webp")

    with Image.open(io.BytesIO(animated)) as before:
        assert before.getexif().get(0x0112) == 1
    with Image.open(io.BytesIO(reencoded)) as after:
        after.load()
        assert after.n_frames == 2
        assert not after.getexif()


def test_reencode_image_keeps_the_main_picture_of_an_mpo():
    # A JPEG with a second picture behind it (a camera's large preview, a
    # depth map) opens as multi-frame, but it is still one photo.
    first, second = Image.new("RGB", (8, 8), "red"), Image.new("RGB", (8, 8), "blue")
    out = io.BytesIO()
    first.save(out, "MPO", save_all=True, append_images=[second])

    reencoded = reencode_image(out.getvalue(), "jpg")

    with Image.open(io.BytesIO(reencoded)) as result:
        assert result.format == "JPEG"
        assert getattr(result, "n_frames", 1) == 1
        assert result.getpixel((4, 4))[0] > 200  # the red one, the first picture


def test_usage_ignores_a_file_that_vanishes_between_listing_and_stat(media, monkeypatch):
    # A concurrent delete_own_upload (avatar/listing cleanup) or the hourly
    # purge can remove a file between os.scandir listing it and usage()
    # calling .stat() on it. That must not crash the request that's just
    # trying to read the quota - and the file no longer counts anyway.
    owner = uuid.uuid4()
    directory = media / "images" / str(owner)
    directory.mkdir(parents=True)
    survives = directory / ("a" * 32 + ".png")
    survives.write_bytes(PNG)
    raced = directory / ("b" * 32 + ".png")
    raced.write_bytes(PNG)

    real_scandir = os.scandir

    @contextlib.contextmanager
    def racy_scandir(path):
        with real_scandir(path) as entries:

            def gen():
                for entry in entries:
                    if entry.name == raced.name:
                        raced.unlink()  # simulate the race right here
                    yield entry

            yield gen()

    monkeypatch.setattr(os, "scandir", racy_scandir)

    recent, total = usage(owner)

    assert total == len(PNG)  # only the surviving file counted
    assert recent == 1


def test_store_writes_the_source_under_the_limit(tmp_path):
    destination = tmp_path / "photo.png"

    _store(io.BytesIO(PNG), destination, limit=len(PNG), extension="png")

    with Image.open(destination) as decoded:
        decoded.load()
        assert decoded.size == (2, 2)
    assert not destination.with_name(destination.name + ".part").exists()


def test_store_refuses_a_source_over_the_limit_and_leaves_nothing_behind(tmp_path):
    destination = tmp_path / "photo.png"

    with pytest.raises(_TooLarge):
        _store(io.BytesIO(PNG + b"\x00"), destination, limit=len(PNG), extension="png")

    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()


def test_store_refuses_a_source_that_only_has_the_right_signature(tmp_path):
    destination = tmp_path / "photo.png"
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # right signature, not a real PNG

    with pytest.raises(_InvalidImage):
        _store(io.BytesIO(fake_png), destination, limit=len(fake_png), extension="png")

    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()


def test_store_lets_a_filesystem_error_propagate_unconverted(tmp_path, monkeypatch):
    # A real image failing to write (full disk, permissions) is a server
    # problem, not a bad upload - it must not be reported as one.
    destination = tmp_path / "photo.png"

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError) as excinfo:
        _store(io.BytesIO(PNG), destination, limit=len(PNG), extension="png")

    assert not isinstance(excinfo.value, _InvalidImage)
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()


def test_store_refuses_an_unexpected_reencode_error_as_invalid_and_logs_it(
    tmp_path, monkeypatch, caplog
):
    # Pillow raises more than OSError on malformed input (an MPO used to end
    # in a KeyError): still a refused upload, not a 500 - but logged.
    destination = tmp_path / "photo.png"

    def failing_reencode(data, extension):
        raise KeyError("JPEG")

    monkeypatch.setattr("app.api.v1.uploads.reencode_image", failing_reencode)

    with pytest.raises(_InvalidImage):
        _store(io.BytesIO(PNG), destination, limit=len(PNG), extension="png")

    assert "unexpected error re-encoding" in caplog.text
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()


def test_delete_own_upload_removes_the_file(media):
    owner = uuid.uuid4()
    path = media / "images" / str(owner) / ("a" * 32 + ".png")
    path.parent.mkdir(parents=True)
    path.write_bytes(PNG)

    delete_own_upload(f"/media/images/{owner}/{'a' * 32}.png", owner)

    assert not path.exists()


def test_delete_own_upload_ignores_someone_elses_file(media):
    owner, other = uuid.uuid4(), uuid.uuid4()
    path = media / "images" / str(other) / ("a" * 32 + ".png")
    path.parent.mkdir(parents=True)
    path.write_bytes(PNG)

    delete_own_upload(f"/media/images/{other}/{'a' * 32}.png", owner)

    assert path.exists()


@pytest.mark.parametrize(
    "ref",
    ["/mock/placeholders/default-listing.svg", "https://cdn.intra.42.fr/a.jpg", "not a path"],
)
def test_delete_own_upload_is_a_noop_on_anything_else(media, ref):
    # must not raise, whatever the input
    delete_own_upload(ref, uuid.uuid4())


def test_delete_own_upload_on_an_already_gone_file_does_not_raise(media):
    delete_own_upload(f"/media/images/{uuid.uuid4()}/{'a' * 32}.png", uuid.uuid4())


def test_own_upload_missing_is_false_when_the_file_is_there(media):
    owner = uuid.uuid4()
    path = media / "images" / str(owner) / ("a" * 32 + ".png")
    path.parent.mkdir(parents=True)
    path.write_bytes(PNG)

    assert not own_upload_missing(f"/media/images/{owner}/{'a' * 32}.png")


def test_own_upload_missing_is_true_when_the_file_is_gone(media):
    owner = uuid.uuid4()

    assert own_upload_missing(f"/media/images/{owner}/{'a' * 32}.png")


@pytest.mark.parametrize(
    "ref",
    ["/mock/placeholders/default-listing.svg", "https://cdn.intra.42.fr/a.jpg", "not a path"],
)
def test_own_upload_missing_is_false_on_anything_that_is_not_our_own_upload(media, ref):
    # not ours to lose, so never "missing"
    assert not own_upload_missing(ref)


def test_is_allowed_image_ref_needs_the_owner_to_match():
    owner, other = uuid.uuid4(), uuid.uuid4()
    ref = f"/media/images/{owner}/{'a' * 32}.png"

    assert is_allowed_image_ref(ref, owner)
    assert not is_allowed_image_ref(ref, other)


# ── purging orphans ──────────────────────────────────────────────


def _write_upload(media, owner, age_seconds=0, name=None):
    path = media / "images" / str(owner) / (name or f"{uuid.uuid4().hex}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
    return path


async def test_purge_orphaned_uploads_removes_an_old_unreferenced_file(db_session, media):
    path = _write_upload(media, uuid.uuid4(), age_seconds=DAY + 60)

    removed = await purge_orphaned_uploads(db_session, older_than=DAY)

    assert removed == 1
    assert not path.exists()


async def test_purge_orphaned_uploads_keeps_a_recent_unreferenced_file(db_session, media):
    path = _write_upload(media, uuid.uuid4(), age_seconds=60)

    removed = await purge_orphaned_uploads(db_session, older_than=DAY)

    assert removed == 0
    assert path.exists()


async def test_purge_orphaned_uploads_keeps_a_file_used_as_an_avatar(
    db_session, create_user, media
):
    me = await create_user()
    path = _write_upload(media, me.public_id, age_seconds=DAY + 60)
    me.avatar_path = f"/media/images/{me.public_id}/{path.name}"
    await db_session.flush()

    removed = await purge_orphaned_uploads(db_session, older_than=DAY)

    assert removed == 0
    assert path.exists()


async def test_purge_orphaned_uploads_keeps_a_file_used_by_a_listing_image(
    db_session, create_user, create_listing, create_listing_image, media
):
    seller = await create_user()
    path = _write_upload(media, seller.public_id, age_seconds=DAY + 60)
    listing = await create_listing(seller_id=seller.id)
    await create_listing_image(
        listing_id=listing.id, storage_path=f"/media/images/{seller.public_id}/{path.name}"
    )

    removed = await purge_orphaned_uploads(db_session, older_than=DAY)

    assert removed == 0
    assert path.exists()


async def test_purge_orphaned_uploads_keeps_a_moderator_deleted_listings_image(
    db_session, create_user, create_listing, create_listing_image, media
):
    # A listing removed via moderation keeps its images on disk on purpose
    # (see reports.py): the purge must not undo that.
    seller = await create_user()
    path = _write_upload(media, seller.public_id, age_seconds=DAY + 60)
    listing = await create_listing(seller_id=seller.id, status="deleted")
    await create_listing_image(
        listing_id=listing.id, storage_path=f"/media/images/{seller.public_id}/{path.name}"
    )

    removed = await purge_orphaned_uploads(db_session, older_than=DAY)

    assert removed == 0
    assert path.exists()


async def test_purge_orphaned_uploads_returns_zero_when_nothing_was_ever_uploaded(
    db_session, media
):
    assert await purge_orphaned_uploads(db_session, older_than=DAY) == 0


def test_reencode_image_refuses_huge_dimensions_without_decoding():
    out = io.BytesIO()
    Image.new("1", (8000, 6000)).save(out, "PNG")  # 48 MP in a few KB
    with pytest.raises(ImageTooBig):
        reencode_image(out.getvalue(), "png")


def _animated(fmt: str, n_frames: int, size: tuple[int, int] = (2, 2)) -> bytes:
    """An animated image of `n_frames` frames. The colours alternate so that no
    encoder merges two identical frames into one."""
    colors = [(255, 0, 0), (0, 0, 255)]
    frames = [Image.new("RGB", size, colors[i % 2]) for i in range(n_frames)]
    out = io.BytesIO()
    frames[0].save(out, format=fmt, save_all=True, append_images=frames[1:])
    return out.getvalue()


ANIMATED_FORMATS = [("GIF", "gif"), ("PNG", "png"), ("WEBP", "webp")]


@pytest.mark.parametrize(("fmt", "extension"), ANIMATED_FORMATS)
def test_reencode_image_refuses_more_frames_than_max_frames(fmt, extension):
    # 2x2 frames: far under both pixel limits, only the count is over.
    with pytest.raises(ImageTooBig):
        reencode_image(_animated(fmt, MAX_FRAMES + 1), extension)


@pytest.mark.parametrize(("fmt", "extension"), ANIMATED_FORMATS)
def test_reencode_image_accepts_exactly_max_frames(fmt, extension):
    reencoded = reencode_image(_animated(fmt, MAX_FRAMES), extension)

    with Image.open(io.BytesIO(reencoded)) as decoded:
        assert decoded.n_frames == MAX_FRAMES


def test_reencode_image_refuses_frames_that_add_up_past_max_total_pixels(monkeypatch):
    # Lowered so the test needs no large image: each 4x4 frame (16 pixels) and
    # the frame count stay under their own limits, only the sum is over.
    monkeypatch.setattr("app.core.uploads.MAX_TOTAL_PIXELS", 40)

    reencode_image(_animated("GIF", 2, size=(4, 4)), "gif")  # 32 pixels: accepted
    with pytest.raises(ImageTooBig):
        reencode_image(_animated("GIF", 3, size=(4, 4)), "gif")  # 48 pixels


def test_store_answers_too_large_past_the_pixel_limit_and_leaves_nothing_behind(
    tmp_path, monkeypatch
):
    # Under the byte limit but over the pixel limit: a 413, not a 415.
    monkeypatch.setattr("app.core.uploads.MAX_PIXELS", 3)  # PNG is 2x2
    destination = tmp_path / "photo.png"

    with pytest.raises(_TooLarge):
        _store(io.BytesIO(PNG), destination, limit=len(PNG), extension="png")

    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()
