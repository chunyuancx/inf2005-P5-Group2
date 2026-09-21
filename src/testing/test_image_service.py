"""Tests for src.services.image_steganography.ImageSteganography (Member 1) - the REAL service.

Three layers, mirroring tests/test_engine.py:
  1. service level   - round trip, capacity, framing, wrong start, bad input
  2. hash/locator contract - what Members 3 and 4 must rely on for real images
  3. controller level - full protect -> save -> verify through the group's
     ApplicationController and VerificationEngine, with the fakes for the
     services that are not mine (crypto, payload, location)

Why some fakes are wrapped: tests/fakes.py treats raw file bytes as the cover
(byte-masked hashing, offsets from len(media.data)).  That is right for the
fake stego service but wrong for a real PNG/BMP, which is re-encoded on embed.
PixelCrypto and PixelGeometryLocator below are the image-aware equivalents.

Run:  python -m pytest tests/test_image_service.py -v
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import sys

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers import ApplicationController  # noqa: E402
from src.exceptions import IntegrationError, PayloadMissing, UnsupportedFileType  # noqa: E402
from src.models import Media, MediaType, Verdict  # noqa: E402
from src.services import UnconfiguredService  # noqa: E402
from src.services.image_steganography import ImageSteganography  # noqa: E402
from tests.fakes import FakeCrypto, FakePayloadService, NaiveStartLocation  # noqa: E402

SVC = ImageSteganography()
FORMATS = {"png": ".png", "bmp": ".bmp"}
HEADER_BITS = ImageSteganography.HEADER.size * 8


# ------------------------------------------------------------------ helpers

def encode(arr: np.ndarray, fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format=fmt.upper())
    return buf.getvalue()


def make_array(size=(64, 64), mode="RGB", seed=1, smooth=False) -> np.ndarray:
    width, height = size
    channels = {"L": 1, "RGB": 3, "RGBA": 4}[mode]
    shape = (height, width) if channels == 1 else (height, width, channels)
    if smooth:  # compressible gradient: makes re-encoded file size change visibly
        grid = (np.add.outer(np.arange(height), np.arange(width)) % 256).astype(np.uint8)
        return grid if channels == 1 else np.stack([grid] * channels, axis=-1)
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


def make_cover(size=(64, 64), mode="RGB", fmt="png", seed=1, smooth=False) -> Media:
    data = encode(make_array(size, mode, seed, smooth), fmt)
    return Media(data, FORMATS[fmt], MediaType.IMAGE)


def write_cover(tmp_path, name="cover.png", **kwargs) -> str:
    fmt = name.rsplit(".", 1)[1]
    path = tmp_path / name
    path.write_bytes(make_cover(fmt=fmt, **kwargs).data)
    return str(path)


def payload_bytes(n: int, seed: int = 7) -> bytes:
    return np.random.default_rng(seed).bytes(n)


def stego_media(cover: Media, payload: bytes, lsb: int, start: int) -> Media:
    return Media(SVC.embed(cover, payload, lsb, start), cover.suffix, cover.kind)


def decoded(media: Media) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(media.data)))


def color_units(media: Media) -> np.ndarray:
    """Independent re-derivation of the unit convention: colour samples,
    row-major, alpha excluded."""
    arr = decoded(media)
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[..., :3]
    return arr.reshape(-1)


def used_units(payload_len: int, lsb: int) -> int:
    return -(-(HEADER_BITS + payload_len * 8) // lsb)


def edit_pixels(path: str, edit) -> None:
    """Decode an RGB image file, apply ``edit(array)``, re-save in place."""
    fmt = Image.open(path).format
    arr = np.array(Image.open(path))
    edit(arr)
    Image.fromarray(arr).save(path, format=fmt)


def flip_unit_bit(media: Media, unit: int, bit: int = 0) -> Media:
    arr = decoded(media)  # RGB only, so unit index == flat index
    arr.reshape(-1)[unit] ^= 1 << bit
    return Media(encode(arr, media.suffix[1:]), media.suffix, media.kind)


# ------------------------------------------------- image-aware test doubles

class PixelCrypto(FakeCrypto):
    """FakeCrypto with the image-correct canonical hash (decoded pixels with the
    low `lsb` bits masked) instead of byte-masking the compressed file."""

    def hash_media(self, media: Media, lsb: int) -> bytes:
        return hashlib.sha256(ImageSteganography.canonical_bytes(media, lsb)).digest()


class PixelGeometryLocator:
    """Keyed start location derived from the image's unit count, which embedding
    does not change (unlike len(media.data)).  Naive recover(): no self-check."""

    def __init__(self, key: str = "team-key") -> None:
        self.key = key

    def _derive(self, media: Media) -> int:
        units = ImageSteganography.unit_count(media)
        seed = hashlib.sha256(f"{self.key}|{units}".encode()).digest()
        return int.from_bytes(seed[:8], "big") % max(1, units // 2)

    def generate(self, media: Media, lsb: int) -> int:
        return self._derive(media)

    def recover(self, media: Media, lsb: int) -> int:
        return self._derive(media)


class SpyImage(ImageSteganography):
    def __init__(self) -> None:
        self.embed_calls = 0

    def embed(self, media, payload, lsb, start):
        self.embed_calls += 1
        return super().embed(media, payload, lsb, start)


def controller(location=None, crypto=None, image=None) -> ApplicationController:
    return ApplicationController(
        image=image or ImageSteganography(),
        audio=UnconfiguredService(),
        crypto=crypto or PixelCrypto(),
        payload=FakePayloadService(),
        location=location or PixelGeometryLocator(),
    )


def protect_and_save(ctl, tmp_path, name="cover.png", lsb=1, **cover_kwargs) -> str:
    src = write_cover(tmp_path, name=name, **cover_kwargs)
    stego = ctl.protect(src, lsb=lsb)
    out = str(tmp_path / f"stego_{name}")
    ctl.save(stego, out)
    return out


# ============================================================ 1. service level

@pytest.mark.parametrize("fmt", ["png", "bmp"])
@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA"])
@pytest.mark.parametrize("lsb", [1, 2, 3, 4, 5, 6, 7, 8])
def test_round_trip_every_lsb_depth(fmt, mode, lsb):
    cover = make_cover(size=(48, 40), mode=mode, fmt=fmt)
    payload = payload_bytes(150)
    stego = stego_media(cover, payload, lsb, start=37)
    assert SVC.extract(stego, lsb, 37) == payload


@pytest.mark.parametrize("size", [1, 2, 31, 256, 1000])
def test_round_trip_various_payload_sizes(size):
    cover = make_cover(size=(96, 96))
    payload = payload_bytes(size)
    assert SVC.extract(stego_media(cover, payload, 2, 500), 2, 500) == payload


def test_bit_order_is_msb_first_after_the_header():
    """Pins the convention Members 3/4 may rely on, independent of the service:
    payload byte 0x41 = 01000001 lands MSB-first in the low bits after the header."""
    cover = make_cover(size=(32, 32))
    before = color_units(cover)

    stego = stego_media(cover, b"A", 1, start=10)
    after = color_units(stego)
    payload_units = after[10 + HEADER_BITS: 10 + HEADER_BITS + 8] & 1
    assert payload_units.tolist() == [0, 1, 0, 0, 0, 0, 0, 1]

    stego2 = stego_media(cover, b"A", 2, start=10)
    after2 = color_units(stego2)
    first = 10 + HEADER_BITS // 2
    assert (after2[first: first + 4] & 3).tolist() == [1, 0, 0, 1]  # 01 00 00 01
    assert before.shape == after.shape


def test_capacity_known_values():
    rgb = make_cover(size=(64, 64), mode="RGB")  # 12288 units
    assert SVC.capacity(rgb, 1, 0) == (12288 - HEADER_BITS) // 8
    assert SVC.capacity(rgb, 8, 0) == (12288 * 8 - HEADER_BITS) // 8
    assert SVC.capacity(rgb, 1, 100) == ((12288 - 100) - HEADER_BITS) // 8
    gray = make_cover(size=(64, 64), mode="L")  # 4096 units
    assert SVC.capacity(gray, 1, 0) == (4096 - HEADER_BITS) // 8
    rgba = make_cover(size=(64, 64), mode="RGBA")  # alpha not used -> same as RGB
    assert SVC.capacity(rgba, 1, 0) == SVC.capacity(rgb, 1, 0)


def test_capacity_edges():
    cover = make_cover(size=(8, 8))  # 192 units
    assert SVC.capacity(cover, 1, 192) == 0          # start at the end
    assert SVC.capacity(cover, 1, 10_000) == 0       # start beyond the image
    assert SVC.capacity(cover, 1, -1) == 0           # negative start
    assert SVC.capacity(cover, 1, 0) == (192 - HEADER_BITS) // 8
    caps = [SVC.capacity(cover, lsb, 0) for lsb in range(1, 9)]
    assert caps == sorted(caps) and caps[0] < caps[-1]


@pytest.mark.parametrize("lsb", [1, 3, 8])
def test_payload_exactly_at_capacity_fits_and_one_more_byte_is_rejected(lsb):
    cover = make_cover(size=(32, 32))
    start = 20
    cap = SVC.capacity(cover, lsb, start)
    payload = payload_bytes(cap)
    assert SVC.extract(stego_media(cover, payload, lsb, start), lsb, start) == payload
    with pytest.raises(IntegrationError):
        SVC.embed(cover, payload_bytes(cap + 1), lsb, start)


def test_embed_rejects_bad_arguments():
    cover = make_cover(size=(16, 16))
    for lsb in (0, 9, True, 1.5, None):
        with pytest.raises(IntegrationError):
            SVC.embed(cover, b"x", lsb, 0)
    with pytest.raises(IntegrationError):
        SVC.embed(cover, b"", 1, 0)                   # empty payload
    with pytest.raises(IntegrationError):
        SVC.embed(cover, b"x", 1, -1)                 # negative start
    with pytest.raises(IntegrationError):
        SVC.embed(cover, b"x", 1, 16 * 16 * 3)        # start at the end
    with pytest.raises(IntegrationError):
        SVC.capacity(cover, 9, 0)


def test_numpy_integer_start_is_accepted():
    cover = make_cover(size=(32, 32))
    stego = stego_media(cover, b"hello", 2, np.int64(50))
    assert SVC.extract(stego, 2, np.int64(50)) == b"hello"


@pytest.mark.parametrize("fmt", ["png", "bmp"])
@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA"])
def test_only_the_embedded_run_changes_and_by_less_than_2_pow_lsb(fmt, mode):
    lsb, start, n = 3, 91, 120
    cover = make_cover(size=(40, 40), mode=mode, fmt=fmt)
    stego = stego_media(cover, payload_bytes(n), lsb, start)

    a, b = color_units(cover).astype(int), color_units(stego).astype(int)
    changed = np.flatnonzero(a != b)
    assert changed.size > 0
    assert changed.min() >= start
    assert changed.max() < start + used_units(n, lsb)
    assert np.abs(a - b).max() < 2 ** lsb
    if mode == "RGBA" and fmt == "png":  # transparency is never touched
        assert np.array_equal(decoded(cover)[..., 3], decoded(stego)[..., 3])


@pytest.mark.parametrize("fmt", ["png", "bmp"])
@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA"])
def test_output_keeps_container_geometry_and_unit_count(fmt, mode):
    cover = make_cover(size=(37, 29), mode=mode, fmt=fmt)
    stego = stego_media(cover, b"payload", 2, 0)
    img_c, img_s = Image.open(io.BytesIO(cover.data)), Image.open(io.BytesIO(stego.data))
    assert img_s.format == fmt.upper() == img_c.format
    assert img_s.size == img_c.size
    assert ImageSteganography.unit_count(stego) == ImageSteganography.unit_count(cover)


@pytest.mark.parametrize("fmt", ["png", "bmp"])
@pytest.mark.parametrize("src_mode,expected", [("1", "L"), ("P", "RGB"), ("LA", "RGB")])
def test_other_modes_are_normalised_and_still_round_trip(fmt, src_mode, expected):
    if fmt == "bmp" and src_mode == "LA":
        pytest.skip("Pillow cannot write LA as BMP")
    img = Image.new(src_mode, (24, 24))
    if src_mode == "P":
        img.putpalette([(i * 7) % 256 for i in range(768)])
        img.putdata([(x * 5) % 256 for x in range(24 * 24)])
    buf = io.BytesIO()
    img.save(buf, format=fmt.upper())
    cover = Media(buf.getvalue(), FORMATS[fmt], MediaType.IMAGE)

    stego = stego_media(cover, b"normalise me", 2, 5)
    assert SVC.extract(stego, 2, 5) == b"normalise me"
    out_mode = Image.open(io.BytesIO(stego.data)).mode
    if src_mode == "LA" and fmt == "png":
        expected = "RGBA"
    assert out_mode == expected
    assert ImageSteganography.unit_count(stego) == ImageSteganography.unit_count(cover)


def test_reembedding_replaces_the_previous_payload():
    cover = make_cover(size=(48, 48))
    once = stego_media(cover, b"first payload", 2, 30)
    twice = stego_media(once, b"second", 2, 30)
    assert SVC.extract(twice, 2, 30) == b"second"


# ---------------------------------------------- framing / wrong-start / abuse

@pytest.mark.parametrize("delta", [1, 7, 40, 500, -1, -13])
def test_wrong_start_raises_payload_missing(delta):
    cover = make_cover(size=(64, 64))
    stego = stego_media(cover, payload_bytes(100), 1, 600)
    with pytest.raises(PayloadMissing):
        SVC.extract(stego, 1, 600 + delta)


@pytest.mark.parametrize("embed_lsb,read_lsb", [(1, 2), (2, 1), (4, 8), (8, 1), (3, 5)])
def test_wrong_lsb_depth_raises_payload_missing(embed_lsb, read_lsb):
    cover = make_cover(size=(64, 64))
    stego = stego_media(cover, payload_bytes(100), embed_lsb, 200)
    with pytest.raises(PayloadMissing):
        SVC.extract(stego, read_lsb, 200)


def test_unprotected_image_raises_payload_missing():
    with pytest.raises(PayloadMissing):
        SVC.extract(make_cover(size=(64, 64)), 1, 0)


@pytest.mark.parametrize("start", [-1, 64 * 64 * 3, 10 ** 9])
def test_start_outside_image_raises_payload_missing(start):
    with pytest.raises(PayloadMissing):
        SVC.extract(make_cover(size=(64, 64)), 1, start)


def test_start_too_close_to_the_end_for_a_header_raises_payload_missing():
    cover = make_cover(size=(16, 16))  # 768 units
    with pytest.raises(PayloadMissing):
        SVC.extract(cover, 1, 768 - HEADER_BITS + 1)


def test_flipped_header_bit_is_caught_at_the_framing_layer():
    cover = make_cover(size=(64, 64))
    stego = stego_media(cover, payload_bytes(60), 1, 100)
    for unit in (100 + 3, 100 + 20, 100 + 45, 100 + 79):  # magic, length, CRC
        with pytest.raises(PayloadMissing):
            SVC.extract(flip_unit_bit(stego, unit), 1, 100)


def test_flipped_payload_bit_passes_through_to_the_crypto_layer():
    """By design the LSB layer does not checksum the payload: a modified payload
    must reach the signature check (-> Signature Invalid), not die here."""
    cover = make_cover(size=(64, 64))
    payload = payload_bytes(60)
    stego = stego_media(cover, payload, 1, 100)
    got = SVC.extract(flip_unit_bit(stego, 100 + HEADER_BITS + 5), 1, 100)
    assert len(got) == len(payload) and got != payload
    diff_bits = sum(bin(x ^ y).count("1") for x, y in zip(got, payload))
    assert diff_bits == 1


def test_non_image_bytes_are_an_integration_error_not_payload_missing():
    junk = Media(b"definitely not an image", ".png", MediaType.IMAGE)
    for call in (lambda: SVC.extract(junk, 1, 0), lambda: SVC.capacity(junk, 1, 0),
                 lambda: SVC.embed(junk, b"x", 1, 0)):
        with pytest.raises(IntegrationError) as info:
            call()
        assert not isinstance(info.value, PayloadMissing)


def test_jpeg_disguised_as_png_is_rejected():
    buf = io.BytesIO()
    Image.fromarray(make_array()).save(buf, format="JPEG")
    fake_png = Media(buf.getvalue(), ".png", MediaType.IMAGE)
    with pytest.raises(UnsupportedFileType):
        SVC.embed(fake_png, b"x", 1, 0)
    with pytest.raises(UnsupportedFileType):
        SVC.extract(fake_png, 1, 0)


def test_unsupported_suffix_and_16_bit_images_are_rejected():
    with pytest.raises(UnsupportedFileType):
        SVC.embed(Media(make_cover().data, ".jpg", MediaType.IMAGE), b"x", 1, 0)
    buf = io.BytesIO()
    try:
        Image.new("I;16", (8, 8)).save(buf, format="PNG")
    except Exception:
        pytest.skip("this Pillow build cannot write 16-bit PNG")
    with pytest.raises(UnsupportedFileType):
        SVC.capacity(Media(buf.getvalue(), ".png", MediaType.IMAGE), 1, 0)


# ================================================ 2. hash / locator contract

@pytest.mark.parametrize("fmt", ["png", "bmp"])
@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA"])
@pytest.mark.parametrize("lsb", [1, 4, 8])
def test_canonical_bytes_identical_for_cover_and_stego(fmt, mode, lsb):
    """What makes hash_media agree before and after protect(), for any start."""
    cover = make_cover(size=(40, 40), mode=mode, fmt=fmt)
    for start in (0, 333):
        stego = stego_media(cover, payload_bytes(80), lsb, start)
        assert ImageSteganography.canonical_bytes(stego, lsb) == \
            ImageSteganography.canonical_bytes(cover, lsb)


def test_canonical_bytes_react_to_real_changes():
    lsb = 2
    cover = make_cover(size=(32, 32), mode="RGBA")
    base = ImageSteganography.canonical_bytes(cover, lsb)

    arr = decoded(cover)
    arr[5, 5, 0] ^= 0x80                       # high bit of a colour sample
    assert ImageSteganography.canonical_bytes(
        Media(encode(arr, "png"), ".png", MediaType.IMAGE), lsb) != base

    arr = decoded(cover)
    arr[5, 5, 3] ^= 0x01                       # alpha is hashed unmasked
    assert ImageSteganography.canonical_bytes(
        Media(encode(arr, "png"), ".png", MediaType.IMAGE), lsb) != base

    arr = decoded(cover)[:31]                  # different dimensions
    assert ImageSteganography.canonical_bytes(
        Media(encode(arr, "png"), ".png", MediaType.IMAGE), lsb) != base

    arr = decoded(cover)
    arr[5, 5, 0] ^= 0x01                       # only a reserved low bit
    assert ImageSteganography.canonical_bytes(
        Media(encode(arr, "png"), ".png", MediaType.IMAGE), lsb) == base


def test_file_length_and_raw_bytes_change_on_embedding():
    """Why Members 3/4 must not use len(media.data) or raw-byte hashes."""
    cover = make_cover(size=(64, 64), smooth=True)
    stego = stego_media(cover, payload_bytes(200), 1, 100)
    assert len(stego.data) != len(cover.data)
    assert hashlib.sha256(stego.data).digest() != hashlib.sha256(cover.data).digest()
    assert ImageSteganography.unit_count(stego) == ImageSteganography.unit_count(cover)


# ================================================== 3. controller level

@pytest.mark.parametrize("fmt", ["png", "bmp"])
@pytest.mark.parametrize("lsb", [1, 2, 3, 4, 5, 6, 7, 8])
def test_authentic_round_trip_through_a_saved_file(tmp_path, fmt, lsb):
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, name=f"cover.{fmt}", lsb=lsb)
    res = ctl.verify(out, lsb=lsb)
    assert res.verdict is Verdict.AUTHENTIC, res.message


def test_party_a_to_party_b_via_a_copied_file(tmp_path):
    a_dir, b_dir = tmp_path / "party_a", tmp_path / "party_b"
    a_dir.mkdir()
    b_dir.mkdir()
    out = protect_and_save(controller(), a_dir, lsb=2)
    received = str(b_dir / "downloaded.png")
    shutil.copy(out, received)

    res = controller().verify(received, lsb=2)      # Party B's own controller
    assert res.verdict is Verdict.AUTHENTIC, res.message
    assert res.statuses["signature"] == "Valid"


def test_capacity_is_checked_before_embedding(tmp_path):
    spy = SpyImage()
    ctl = controller(image=spy)
    tiny = write_cover(tmp_path, name="thumb.png", size=(16, 16))   # 768 units, 1 bit
    with pytest.raises(IntegrationError) as info:
        ctl.protect(tiny, lsb=1)
    assert "capacity" in str(info.value)
    assert spy.embed_calls == 0


def test_same_thumbnail_fits_at_a_deeper_lsb(tmp_path):
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, name="thumb.png", lsb=8, size=(16, 16))
    assert ctl.verify(out, lsb=8).verdict is Verdict.AUTHENTIC


def test_pixel_tamper_outside_the_run_is_reported_tampered(tmp_path):
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, lsb=1)
    edit_pixels(out, lambda a: a.__setitem__((-1, -1, 0), a[-1, -1, 0] ^ 0x80))
    res = ctl.verify(out, lsb=1)
    assert res.verdict is Verdict.TAMPERED, res.message
    assert res.statuses["signature"] == "Valid" and res.statuses["hash"] == "Mismatch"


def test_bmp_raw_byte_edit_is_reported_tampered(tmp_path):
    """BMP stores raw pixels, so editing the file bytes IS a pixel edit.  The
    pixel data starts at the offset in the header; the first stored row is the
    image's bottom row, i.e. clear of the embedded run."""
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, name="cover.bmp", lsb=1)
    data = bytearray(open(out, "rb").read())
    offset = int.from_bytes(data[10:14], "little")
    data[offset + 3] ^= 0x80
    open(out, "wb").write(bytes(data))
    res = ctl.verify(out, lsb=1)
    assert res.verdict is Verdict.TAMPERED, res.message


def test_png_raw_byte_edit_is_never_authentic(tmp_path):
    """A raw edit to a compressed PNG corrupts the container instead of changing
    a pixel (PNG chunk CRCs fail), so it surfaces as Cannot Verify rather than
    the 'Tampered' the fakes' byte edits produce.  It must never verify."""
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, lsb=1)
    data = bytearray(open(out, "rb").read())
    data[len(data) // 2] ^= 0xFF
    open(out, "wb").write(bytes(data))
    res = ctl.verify(out, lsb=1)
    assert res.verdict is Verdict.CANNOT_VERIFY, res.message


def test_edit_confined_to_reserved_low_bits_outside_run_is_not_detected(tmp_path):
    """KNOWN LIMITATION (worth stating in the demo Q&A): the canonical hash
    excludes the low `lsb` bits of every sample, because hash_media does not
    know where the payload is.  So a change confined to those bits, outside the
    embedded run, still verifies as Authentic."""
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, lsb=2)
    edit_pixels(out, lambda a: a.__setitem__((-1, -1, 0), a[-1, -1, 0] ^ 0x01))
    assert ctl.verify(out, lsb=2).verdict is Verdict.AUTHENTIC


def test_wrong_signing_key_is_signature_invalid(tmp_path):
    out = protect_and_save(controller(crypto=PixelCrypto("alice", "alice")), tmp_path)
    res = controller(crypto=PixelCrypto("mallory", "mallory")).verify(out, lsb=1)
    assert res.verdict is Verdict.SIGNATURE_INVALID, res.message


def test_unprotected_image_is_payload_missing(tmp_path):
    plain = write_cover(tmp_path, name="plain.png")
    res = controller().verify(plain, lsb=1)
    assert res.verdict is Verdict.PAYLOAD_MISSING, res.message


def test_wrong_lsb_at_verify_time_is_payload_missing(tmp_path):
    ctl = controller()
    out = protect_and_save(ctl, tmp_path, lsb=3)
    assert ctl.verify(out, lsb=4).verdict is Verdict.PAYLOAD_MISSING


def test_wrong_key_locator_degrades_to_payload_missing(tmp_path):
    """Same finding as Member 5's section 4: a locator that just re-derives an
    offset cannot tell a wrong key from a right one, so with a real image the
    verdict is Payload Missing, not Wrong Start Location.  Reaching the latter
    needs a self-check in Member 4's recover()."""
    out = protect_and_save(controller(location=PixelGeometryLocator("right")), tmp_path)
    res = controller(location=PixelGeometryLocator("wrong")).verify(out, lsb=1)
    assert res.verdict is Verdict.PAYLOAD_MISSING, res.message


def test_start_derived_from_file_length_breaks_on_reencoded_stego(tmp_path):
    """DEMONSTRATES THE HAZARD: fakes.NaiveStartLocation seeds from
    len(media.data).  Fine for byte-in-place fakes, but a real PNG is re-encoded
    on embed, so recover() lands elsewhere and a genuine stego image reports
    Payload Missing.  Locators must use ImageSteganography.unit_count()."""
    ctl = controller(location=NaiveStartLocation(), crypto=FakeCrypto())
    src = write_cover(tmp_path, smooth=True)
    stego = ctl.protect(src, lsb=1)
    assert len(stego.data) != len(open(src, "rb").read())
    out = str(tmp_path / "stego.png")
    ctl.save(stego, out)
    assert ctl.verify(out, lsb=1).verdict is Verdict.PAYLOAD_MISSING


def test_unsupported_format_is_cannot_verify(tmp_path):
    odd = tmp_path / "cover.jpg"
    odd.write_bytes(make_cover().data)
    assert controller().verify(str(odd), lsb=1).verdict is Verdict.CANNOT_VERIFY


def test_jpeg_content_named_png_is_cannot_verify(tmp_path):
    buf = io.BytesIO()
    Image.fromarray(make_array()).save(buf, format="JPEG")
    sneaky = tmp_path / "sneaky.png"
    sneaky.write_bytes(buf.getvalue())
    res = controller().verify(str(sneaky), lsb=1)
    assert res.verdict is Verdict.CANNOT_VERIFY, res.message
