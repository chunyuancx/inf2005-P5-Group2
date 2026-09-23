"""End-to-end tests with every real teammate service wired in (no fakes)."""
import io
import shutil
import wave
from pathlib import Path

import pytest
from PIL import Image

from src.controllers import ApplicationController
from src.models import Verdict
from src.services.audio_steganography import WavSteganographyService
from src.services.crypto_adapter import SignatureCrypto
from src.services.image_steganography import ImageSteganography
from src.services.payload_service import EnvelopePayloadService
from src.services.start_location import KeyedStartLocation

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
COVERS = [SAMPLES / "lambda-icon.png", SAMPLES / "audio" / "original.wav"]


def make_controller(key_dir, passphrase="correct horse"):
    location = KeyedStartLocation()
    location.key = passphrase
    return ApplicationController(
        image=ImageSteganography(), audio=WavSteganographyService(),
        crypto=SignatureCrypto(key_dir), payload=EnvelopePayloadService(),
        location=location)


def protect_copy(controller, cover, tmp_path, lsb=1):
    source = tmp_path / cover.name
    shutil.copy(cover, source)
    stego = tmp_path / f"{cover.stem}_stego{cover.suffix}"
    controller.save(controller.protect(str(source), lsb), str(stego))
    return stego


def tamper(path: Path) -> None:
    """Flip a high-order bit that no LSB depth reserves for embedding."""
    if path.suffix == ".png":
        image = Image.open(path)
        image.load()
        pixel = list(image.getpixel((0, 0)))
        pixel[0] ^= 0x80
        image.putpixel((0, 0), tuple(pixel))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        path.write_bytes(buffer.getvalue())
    else:
        with wave.open(str(path), "rb") as reader:
            params, frames = reader.getparams(), bytearray(reader.readframes(reader.getnframes()))
        frames[len(frames) // 2 | 1] ^= 0x40  # high byte of a 16-bit sample
        with wave.open(str(path), "wb") as writer:
            writer.setparams(params)
            writer.writeframes(bytes(frames))


@pytest.mark.parametrize("cover", COVERS, ids=lambda p: p.suffix)
@pytest.mark.parametrize("lsb", [1, 2, 4])
def test_authentic_round_trip(cover, lsb, tmp_path):
    controller = make_controller(tmp_path / "keys")
    stego = protect_copy(controller, cover, tmp_path, lsb)
    result = controller.verify(str(stego), lsb)
    assert result.verdict == Verdict.AUTHENTIC, result.message


def test_keys_persist_across_sessions(tmp_path):
    stego = protect_copy(make_controller(tmp_path / "keys"), COVERS[0], tmp_path)
    fresh = make_controller(tmp_path / "keys")
    assert fresh.verify(str(stego), 1).verdict == Verdict.AUTHENTIC


@pytest.mark.xfail(strict=True, reason=(
    "KeyedStartLocation derives the start from the full canonical media, so "
    "any content edit moves the start and the payload reads as missing."))
@pytest.mark.parametrize("cover", COVERS, ids=lambda p: p.suffix)
def test_tampered(cover, tmp_path):
    controller = make_controller(tmp_path / "keys")
    stego = protect_copy(controller, cover, tmp_path)
    tamper(stego)
    assert controller.verify(str(stego), 1).verdict == Verdict.TAMPERED


@pytest.mark.parametrize("cover", COVERS, ids=lambda p: p.suffix)
def test_tampered_with_manual_start(cover, tmp_path):
    controller = make_controller(tmp_path / "keys")
    controller.location.manual_start = 100
    stego = protect_copy(controller, cover, tmp_path)
    tamper(stego)
    assert controller.verify(str(stego), 1).verdict == Verdict.TAMPERED


@pytest.mark.parametrize("cover", COVERS, ids=lambda p: p.suffix)
def test_signature_invalid_with_other_public_key(cover, tmp_path):
    stego = protect_copy(make_controller(tmp_path / "keys_a"), cover, tmp_path)
    other = make_controller(tmp_path / "keys_b")
    other.crypto.sign(b"create key pair B")
    assert other.verify(str(stego), 1).verdict == Verdict.SIGNATURE_INVALID


@pytest.mark.parametrize("cover", COVERS, ids=lambda p: p.suffix)
def test_payload_missing_on_unprotected_cover(cover, tmp_path):
    controller = make_controller(tmp_path / "keys")
    controller.crypto.sign(b"create key pair")
    assert controller.verify(str(cover), 1).verdict == Verdict.PAYLOAD_MISSING


def test_wrong_passphrase_reports_payload_missing(tmp_path):
    # KeyedStartLocation.recover() has no self-check, so a wrong passphrase
    # cannot be told apart from an absent payload (see docs section 4).
    stego = protect_copy(make_controller(tmp_path / "keys"), COVERS[0], tmp_path)
    wrong = make_controller(tmp_path / "keys", passphrase="wrong passphrase")
    assert wrong.verify(str(stego), 1).verdict == Verdict.PAYLOAD_MISSING


def test_wrong_lsb_depth_is_not_authentic(tmp_path):
    controller = make_controller(tmp_path / "keys")
    stego = protect_copy(controller, COVERS[0], tmp_path, lsb=2)
    assert controller.verify(str(stego), 1).verdict != Verdict.AUTHENTIC


def test_verify_without_public_key_cannot_verify(tmp_path):
    stego = protect_copy(make_controller(tmp_path / "keys"), COVERS[0], tmp_path)
    no_keys = make_controller(tmp_path / "empty")
    result = no_keys.verify(str(stego), 1)
    assert result.verdict == Verdict.CANNOT_VERIFY
    assert "public key" in result.message
