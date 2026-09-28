"""The attack lab's envelope locator must find where a payload really sits."""
from pathlib import Path

import pytest

from src.controllers import ApplicationController
from src.gui.diagnostics import find_envelopes
from src.services.audio_steganography import WavSteganographyService
from src.services.crypto_adapter import SignatureCrypto
from src.services.image_steganography import ImageSteganography
from src.services.payload_service import EnvelopePayloadService
from src.services.start_location import KeyedStartLocation

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def make(tmp_path, position):
    location = KeyedStartLocation()
    location.manual_start = position
    return ApplicationController(
        image=ImageSteganography(), audio=WavSteganographyService(),
        crypto=SignatureCrypto(tmp_path / "keys"), payload=EnvelopePayloadService(), location=location)


@pytest.mark.parametrize("cover", [SAMPLES / "lambda-icon.png", SAMPLES / "audio" / "original.wav"], ids=lambda p: p.suffix)
@pytest.mark.parametrize("lsb,position", [(1, 100), (3, 2000)])
def test_finds_the_embedded_envelope(tmp_path, cover, lsb, position):
    controller = make(tmp_path, position)
    stego = tmp_path / f"stego{cover.suffix}"
    controller.save(controller.protect(str(cover), lsb, "where am I"), str(stego))
    media = ApplicationController.load(str(stego))
    found = find_envelopes(media, lsb)
    assert [start for start, _ in found] == [position]
    assert find_envelopes(ApplicationController.load(str(cover)), lsb) == []
