"""Proves KeyedStartLocation drops into the real application pipeline.

Everything here is real code -- ApplicationController, VerificationEngine,
ImageSteganography, WavSteganographyService and KeyedStartLocation.  Only the
crypto and payload services are doubled, because they do not exist yet.

The crypto double hashes CANONICAL bytes rather than raw file bytes.  That is
what the real CryptoService must also do: embedding rewrites the file, so
hashing media.data would make every protected file report Tampered.
"""
from __future__ import annotations

import hashlib
import os
import sys
import wave
from array import array

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers import ApplicationController  # noqa: E402
from src.models import MediaType, Verdict  # noqa: E402
from src.services.audio_steganography import WavSteganographyService  # noqa: E402
from src.services.image_steganography import ImageSteganography  # noqa: E402
from src.services.start_location import KeyedStartLocation  # noqa: E402
from tests.fakes import FakeCrypto, FakePayloadService  # noqa: E402

PASSPHRASE = "party-A-passphrase"


class CanonicalCrypto(FakeCrypto):
    """Hashes the canonical form, as the real CryptoService will have to."""

    def hash_media(self, media, lsb: int) -> bytes:
        if media.kind == MediaType.IMAGE:
            canonical = ImageSteganography.canonical_bytes(media, lsb)
        else:
            canonical = WavSteganographyService().canonical_bytes(media, lsb)
        return hashlib.sha256(canonical).digest()


def build(passphrase: str = PASSPHRASE, verify_key: str = "team-key"):
    """The wiring the application uses, with crypto and payload doubled."""
    return ApplicationController(
        image=ImageSteganography(),
        audio=WavSteganographyService(),
        crypto=CanonicalCrypto(verify_key=verify_key),
        payload=FakePayloadService(),
        location=KeyedStartLocation(passphrase),
    )


def write_png(tmp_path, name="cover.png", seed=0):
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, size=(96, 96, 3), dtype=np.uint8)
    path = tmp_path / name
    Image.fromarray(pixels).save(path, format="PNG")
    return str(path)


def write_wav(tmp_path, name="cover.wav", seed=0):
    rng = np.random.default_rng(seed)
    samples = array("h", rng.integers(-20_000, 20_000, size=12_000,
                                      dtype=np.int16).tolist())
    path = tmp_path / name
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(samples.tobytes())
    return str(path)


WRITERS = {"image": write_png, "audio": write_wav}


def protect_to_disk(controller, tmp_path, cover_path, lsb, out_name):
    stego = controller.protect(cover_path, lsb)
    out = str(tmp_path / out_name)
    controller.save(stego, out)
    return out


# ------------------------------------------------------------- positive cases

@pytest.mark.parametrize("kind", ["image", "audio"])
def test_protect_then_verify_is_authentic(tmp_path, kind):
    """LOAD BEARING. The whole pipeline through the real VerificationEngine."""
    cover = WRITERS[kind](tmp_path)
    suffix = os.path.splitext(cover)[1]
    for lsb in (1, 2, 4):
        controller = build()
        out = protect_to_disk(controller, tmp_path, cover, lsb, f"stego{lsb}{suffix}")
        result = controller.verify(out, lsb)
        assert result.verdict is Verdict.AUTHENTIC, f"lsb={lsb}: {result.message}"


def test_every_lsb_depth_round_trips(tmp_path):
    """All eight depths must work end to end."""
    cover = write_png(tmp_path)
    for lsb in range(1, 9):
        controller = build()
        out = protect_to_disk(controller, tmp_path, cover, lsb, f"d{lsb}.png")
        assert controller.verify(out, lsb).verdict is Verdict.AUTHENTIC, lsb


def test_verifier_is_a_separate_process_with_only_the_passphrase(tmp_path):
    """A brand-new controller, sharing nothing but the passphrase."""
    out = protect_to_disk(build(), tmp_path, write_png(tmp_path), 2, "stego.png")
    assert build().verify(out, 2).verdict is Verdict.AUTHENTIC


def test_statuses_are_reported_for_the_gui(tmp_path):
    """result.statuses drives the results table; every stage must be filled."""
    controller = build()
    out = protect_to_disk(controller, tmp_path, write_png(tmp_path), 2, "stego.png")
    statuses = controller.verify(out, 2).statuses
    assert statuses["location"] == "Computed"
    assert statuses["payload"] == "Parsed"
    assert statuses["signature"] == "Valid"
    assert statuses["hash"] == "Match"


def test_passphrase_can_change_between_operations(tmp_path):
    """One long-lived controller with the key set per operation."""
    controller = build()
    locator = controller.location

    locator.key = "first-passphrase"
    a = protect_to_disk(controller, tmp_path, write_png(tmp_path, "a.png"), 2, "a_s.png")
    locator.key = "second-passphrase"
    b = protect_to_disk(controller, tmp_path, write_png(tmp_path, "b.png", seed=1),
                        2, "b_s.png")

    assert controller.verify(b, 2).verdict is Verdict.AUTHENTIC
    locator.key = "first-passphrase"
    assert controller.verify(a, 2).verdict is Verdict.AUTHENTIC


def test_manual_start_round_trips_through_the_controller(tmp_path):
    """A pinned position, end to end."""
    controller = build()
    controller.location.manual_start = 4_000
    out = protect_to_disk(controller, tmp_path, write_png(tmp_path), 2, "manual.png")
    assert controller.verify(out, 2).verdict is Verdict.AUTHENTIC


# ------------------------------------------------------------- negative cases

@pytest.mark.parametrize("kind", ["image", "audio"])
def test_wrong_passphrase_does_not_verify(tmp_path, kind):
    cover = WRITERS[kind](tmp_path)
    suffix = os.path.splitext(cover)[1]
    out = protect_to_disk(build(), tmp_path, cover, 2, f"stego{suffix}")
    result = build(passphrase="wrong-passphrase").verify(out, 2)
    assert result.verdict is Verdict.PAYLOAD_MISSING, result.message


def test_missing_passphrase_is_reported_not_crashed(tmp_path):
    """An empty passphrase must produce a verdict, never a traceback."""
    out = protect_to_disk(build(), tmp_path, write_png(tmp_path), 2, "stego.png")
    controller = build()
    controller.location = KeyedStartLocation()      # nothing typed
    controller.engine.location = controller.location
    result = controller.verify(out, 2)
    assert result.verdict is Verdict.CANNOT_VERIFY
    assert "passphrase" in result.message.lower(), result.message


def test_unprotected_file_is_payload_missing(tmp_path):
    controller = build()
    assert controller.verify(write_png(tmp_path), 2).verdict is Verdict.PAYLOAD_MISSING


def test_bad_signature_is_signature_invalid(tmp_path):
    """Right passphrase, wrong verifying key -- start recovery still works."""
    out = protect_to_disk(build(), tmp_path, write_png(tmp_path), 2, "stego.png")
    result = build(verify_key="attacker-key").verify(out, 2)
    assert result.verdict is Verdict.SIGNATURE_INVALID, result.message
