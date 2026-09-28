"""Tests for the start-location module.

The payload begins at a derived or pinned position that is never the very
first unit, the reader recovers that same position, and a derived position
depends on the passphrase.

Run:  .venv/Scripts/python.exe -m pytest tests/test_start_location.py -v
"""
from __future__ import annotations

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exceptions import IntegrationError, PayloadMissing  # noqa: E402
from src.models import Media, MediaType  # noqa: E402
from src.services.start_location import (  # noqa: E402
    KeyedStartLocation,
    audio_capacity,
    derive_nonce,
    derive_start,
    image_capacity,
)

KEY = b"group2-acw1-secret"
OTHER_KEY = b"group2-acw1-secreu"  # one bit different from KEY
NONCE = b"\x01\x02\x03\x04"
DEPTHS = range(1, 9)


# --------------------------------------------------------------- cover media

def make_png(width: int = 64, height: int = 64, seed: int = 0) -> Media:
    """Deterministic RGB PNG cover."""
    from PIL import Image
    import numpy as np

    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return Media(buffer.getvalue(), ".png", MediaType.IMAGE)


def make_wav(num_frames: int = 8000, channels: int = 1, seed: int = 0) -> Media:
    """Deterministic 16-bit PCM WAV cover."""
    import wave
    from array import array
    import numpy as np

    rng = np.random.default_rng(seed)
    values = rng.integers(-20_000, 20_000,
                          size=num_frames * channels, dtype=np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(array("h", values.tolist()).tobytes())
    return Media(buffer.getvalue(), ".wav", MediaType.AUDIO)


# ------------------------------------------------------------------ capacity

def test_capacity_helpers_report_bit_capacity():
    assert image_capacity(10, 10, 3, 2) == 600
    assert audio_capacity(1000, 3) == 3000
    for lsb in DEPTHS:
        assert image_capacity(8, 8, 3, lsb) == 8 * 8 * 3 * lsb
        assert audio_capacity(512, lsb) == 512 * lsb


# --------------------------------------------------------------------- nonce

def test_derive_nonce_is_four_deterministic_bytes():
    first = derive_nonce(KEY, b"canonical-media-bytes", 1)
    assert isinstance(first, bytes) and len(first) == 4
    assert first == derive_nonce(KEY, b"canonical-media-bytes", 1)


def test_derive_nonce_binds_key_media_and_lsb():
    base = derive_nonce(KEY, b"canonical-media-bytes", 1)
    assert base != derive_nonce(KEY, b"different-media-bytes", 1)
    assert base != derive_nonce(OTHER_KEY, b"canonical-media-bytes", 1)
    # A different depth masks different bits, so it must change the nonce.
    assert base != derive_nonce(KEY, b"canonical-media-bytes", 4)


# ------------------------------------------------------- core derivation

def test_derive_start_is_idempotent():
    first = derive_start(10_000, KEY, NONCE, 500)
    for _ in range(100):
        assert derive_start(10_000, KEY, NONCE, 500) == first


def test_derive_start_returns_plain_int():
    """WavSteganographyService._validate_start uses `type(start) is not int`,
    which rejects numpy integers outright."""
    assert type(derive_start(10_000, KEY, NONCE, 500)) is int


def test_derive_start_is_never_the_top_left_corner():
    """A payload must never begin at the very first unit."""
    for seed in range(200):
        assert derive_start(10_000, KEY, seed.to_bytes(4, "big"), 500) >= 1


def test_derive_start_always_leaves_room_for_the_payload():
    for seed in range(100):
        start = derive_start(5_000, KEY, seed.to_bytes(4, "big"), 1_000)
        assert 1 <= start <= 5_000 - 1_000, seed
    for lsb in DEPTHS:
        start = derive_start(64 * 64 * 3, KEY, NONCE, 200)
        assert 1 <= start and start + 200 <= 64 * 64 * 3, lsb


def test_derive_start_changes_with_key_and_nonce():
    base = derive_start(100_000, KEY, NONCE, 500)
    assert base != derive_start(100_000, OTHER_KEY, NONCE, 500)
    assert base != derive_start(100_000, KEY, b"\x01\x02\x03\x05", 500)


def test_start_is_distributed_not_clustered():
    """A keyed PRF should spread starts across the range, not favour one spot."""
    starts = {derive_start(100_000, KEY, i.to_bytes(4, "big"), 500)
              for i in range(200)}
    assert len(starts) > 150
    assert max(starts) - min(starts) > 10_000


def test_derive_start_refuses_a_payload_that_does_not_fit():
    with pytest.raises(IntegrationError):
        derive_start(1_000, KEY, NONCE, 5_000)
    # Exactly filling the cover leaves no room for a non-zero start.
    with pytest.raises(IntegrationError):
        derive_start(1_000, KEY, NONCE, 1_000)


# ====================================== PER-OPERATION PASSPHRASE (GUI seam) ==

def test_locator_can_be_built_without_a_key():
    """The app builds the locator at startup, before the user has typed."""
    KeyedStartLocation()


def test_deriving_without_a_passphrase_raises_clearly():
    with pytest.raises(IntegrationError, match="passphrase"):
        KeyedStartLocation().generate(make_png(), 1)


def test_key_can_be_set_after_construction_and_accepts_text():
    """The GUI field hands over a str, not bytes."""
    late = KeyedStartLocation()
    late.key = KEY
    assert late.generate(make_png(), 1) == KeyedStartLocation(KEY).generate(make_png(), 1)
    assert (KeyedStartLocation("group2-acw1-secret").generate(make_png(), 1)
            == KeyedStartLocation(b"group2-acw1-secret").generate(make_png(), 1))
    # Non-ASCII must survive the setter's UTF-8 encoding.
    assert KeyedStartLocation("passphrase-with-ümlaut").generate(make_png(), 1) >= 1


def test_changing_the_key_changes_the_derived_start():
    """One locator instance reused across operations, as the GUI does."""
    media = make_png()
    loc = KeyedStartLocation(KEY)
    first = loc.generate(media, 1)
    loc.key = OTHER_KEY
    assert loc.generate(media, 1) != first


def test_invalid_passphrases_are_rejected():
    loc = KeyedStartLocation(KEY)
    for bad in (b"", "", 12345):
        with pytest.raises(IntegrationError):
            loc.key = bad


def test_repr_does_not_leak_the_passphrase():
    """A traceback or log line must not disclose the secret."""
    assert "super-secret" not in repr(KeyedStartLocation("super-secret-passphrase"))


def test_party_a_to_party_b_handoff():
    """One party protects a file; another recovers it with the same passphrase."""
    from src.services.image_steganography import ImageSteganography

    service = ImageSteganography()
    cover = make_png()
    payload = b"payload from party A"
    start = KeyedStartLocation("shared-passphrase").generate(cover, 2)
    stego = Media(service.embed(cover, payload, 2, start), ".png", MediaType.IMAGE)

    party_b = KeyedStartLocation()          # B's app, freshly launched
    party_b.key = "wrong-guess"
    assert party_b.recover(stego, 2) != start
    party_b.key = "shared-passphrase"
    assert party_b.recover(stego, 2) == start
    assert service.extract(stego, 2, party_b.recover(stego, 2)) == payload


# ============================================ MANUAL START LOCATION MODE ===

def test_manual_start_is_used_verbatim_without_a_passphrase():
    """A pinned position is used as given, with no key involved."""
    loc = KeyedStartLocation()
    loc.manual_start = 5_000
    assert loc.generate(make_png(), 1) == 5_000
    assert loc.recover(make_png(), 1) == 5_000


def test_manual_start_ignores_the_passphrase():
    """A pinned position is not protected by the passphrase."""
    a, b = KeyedStartLocation(KEY), KeyedStartLocation(OTHER_KEY)
    a.manual_start = b.manual_start = 5_000
    assert a.generate(make_png(), 1) == b.generate(make_png(), 1)


def test_manual_start_rejects_zero_and_malformed_values():
    """The very first unit is rejected even when chosen by hand."""
    loc = KeyedStartLocation(KEY)
    for bad in (0, -1, "5000", 5.5):
        with pytest.raises(IntegrationError):
            loc.manual_start = bad


def test_manual_start_beyond_the_cover_is_rejected():
    loc = KeyedStartLocation(KEY)
    loc.manual_start = 10_000_000
    with pytest.raises(IntegrationError, match="outside"):
        loc.generate(make_png(), 1)


def test_clearing_manual_start_restores_keyed_derivation():
    media = make_png()
    loc = KeyedStartLocation(KEY)
    derived = loc.generate(media, 1)
    loc.manual_start = 5_000
    assert loc.generate(media, 1) == 5_000
    loc.manual_start = None
    assert loc.generate(media, 1) == derived


def test_manual_start_round_trips_through_real_embed():
    from src.services.image_steganography import ImageSteganography

    service = ImageSteganography()
    cover = make_png()
    loc = KeyedStartLocation()
    loc.manual_start = 3_000
    payload = b"manually positioned payload"
    start = loc.generate(cover, 2)
    stego = Media(service.embed(cover, payload, 2, start), ".png", MediaType.IMAGE)
    assert service.extract(stego, 2, loc.recover(stego, 2)) == payload


# ======================================================= IMAGE INTEGRATION ===

def test_image_start_is_in_bounds_at_every_depth():
    from src.services.image_steganography import ImageSteganography

    media = make_png()
    for lsb in DEPTHS:
        start = KeyedStartLocation(KEY).generate(media, lsb)
        assert type(start) is int
        assert 1 <= start < ImageSteganography.unit_count(media), lsb


def test_image_start_changes_with_cover_and_key():
    loc = KeyedStartLocation(KEY)
    assert loc.generate(make_png(seed=0), 1) != loc.generate(make_png(seed=1), 1)
    assert (KeyedStartLocation(OTHER_KEY).generate(make_png(), 1)
            != loc.generate(make_png(), 1))


def test_start_is_stable_across_embedding():
    """LOAD BEARING. Cover and stego must derive the SAME start.

    canonical_bytes() masks off the low `lsb` bits, which are exactly the bits
    embedding overwrites.  If this breaks, the whole design breaks.
    """
    from src.services.image_steganography import ImageSteganography

    service = ImageSteganography()
    cover = make_png()
    loc = KeyedStartLocation(KEY)
    for lsb in (1, 2, 4, 8):
        start = loc.generate(cover, lsb)
        stego = Media(service.embed(cover, b"verification-payload", lsb, start),
                      ".png", MediaType.IMAGE)
        assert loc.recover(stego, lsb) == start, lsb


def test_round_trip_extracts_payload_at_derived_start():
    """LOAD BEARING. End-to-end against the real embed/extract."""
    from src.services.image_steganography import ImageSteganography

    service = ImageSteganography()
    cover = make_png()
    loc = KeyedStartLocation(KEY)
    payload = b"INF2005 P5 Group 2 signed payload"
    start = loc.generate(cover, 2)
    stego = Media(service.embed(cover, payload, 2, start), ".png", MediaType.IMAGE)
    assert service.extract(stego, 2, loc.recover(stego, 2)) == payload


def test_wrong_key_does_not_find_payload():
    """A wrong key must fail to extract rather than silently succeed."""
    from src.services.image_steganography import ImageSteganography

    service = ImageSteganography()
    cover = make_png()
    start = KeyedStartLocation(KEY).generate(cover, 2)
    stego = Media(service.embed(cover, b"secret payload", 2, start),
                  ".png", MediaType.IMAGE)
    wrong = KeyedStartLocation(OTHER_KEY).recover(stego, 2)
    assert wrong != start
    with pytest.raises(PayloadMissing):
        service.extract(stego, 2, wrong)


def test_known_limitation_lsb_8_ignores_cover_content():
    """Documents the limitation stated in the module docstring.

    At 8 LSBs the canonical mask clears every colour sample, so no cover
    content survives to bind into the nonce and two different images of the
    same mode and size derive the same start.  Inherent, not a defect: at 8
    LSBs there is no cover content left to bind to.  Below 8 it binds.
    """
    loc = KeyedStartLocation(KEY)
    for lsb in range(1, 8):
        assert loc.generate(make_png(seed=0), lsb) != loc.generate(make_png(seed=1), lsb)
    assert loc.generate(make_png(seed=0), 8) == loc.generate(make_png(seed=1), 8)
    # The key still governs the location, so it stays unguessable.
    assert (KeyedStartLocation(OTHER_KEY).generate(make_png(seed=0), 8)
            != loc.generate(make_png(seed=0), 8))


# ======================================================= AUDIO INTEGRATION ===

def test_audio_start_is_in_bounds_at_every_depth():
    from src.services.audio_steganography import WavSteganographyService

    media = make_wav()
    for lsb in DEPTHS:
        start = KeyedStartLocation(KEY).generate(media, lsb)
        assert type(start) is int
        assert 1 <= start < WavSteganographyService().sample_count(media), lsb


def test_audio_start_changes_with_cover_and_supports_stereo():
    loc = KeyedStartLocation(KEY)
    assert loc.generate(make_wav(seed=0), 1) != loc.generate(make_wav(seed=1), 1)
    assert loc.generate(make_wav(channels=2), 1) >= 1


def test_start_is_stable_across_audio_embedding():
    """LOAD BEARING. The audio half of the design's core property."""
    from src.services.audio_steganography import WavSteganographyService

    service = WavSteganographyService()
    cover = make_wav()
    loc = KeyedStartLocation(KEY)
    for lsb in (1, 2, 4, 8):
        start = loc.generate(cover, lsb)
        stego = Media(service.embed(cover, b"verification-payload", lsb, start),
                      ".wav", MediaType.AUDIO)
        assert loc.recover(stego, lsb) == start, lsb


def test_audio_round_trip_and_wrong_key():
    """LOAD BEARING. Real audio embed/extract, plus the negative case."""
    from src.services.audio_steganography import WavSteganographyService

    service = WavSteganographyService()
    cover = make_wav()
    loc = KeyedStartLocation(KEY)
    payload = b"INF2005 P5 Group 2 signed payload"
    start = loc.generate(cover, 2)
    stego = Media(service.embed(cover, payload, 2, start), ".wav", MediaType.AUDIO)
    assert service.extract(stego, 2, loc.recover(stego, 2)) == payload

    wrong = KeyedStartLocation(OTHER_KEY).recover(stego, 2)
    assert wrong != start
    with pytest.raises(PayloadMissing):
        service.extract(stego, 2, wrong)


def test_audio_canonical_bytes_survive_embedding():
    """The property the audio nonce depends on, asserted directly."""
    from src.services.audio_steganography import WavSteganographyService

    service = WavSteganographyService()
    cover = make_wav()
    start = KeyedStartLocation(KEY).generate(cover, 3)
    stego = Media(service.embed(cover, b"payload", 3, start), ".wav", MediaType.AUDIO)
    assert service.canonical_bytes(cover, 3) == service.canonical_bytes(stego, 3)
