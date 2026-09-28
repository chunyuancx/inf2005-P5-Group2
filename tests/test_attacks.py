"""Attack simulation module (Member 6): every attack changes what it claims to."""
import io
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.attacks import ATTACKS, AttackContext, apply_attack, attacks_for, describe
from src.controllers import ApplicationController
from src.exceptions import IntegrationError
from src.models import Media, MediaType, Verdict
from src.services.audio_steganography import WavSteganographyService
from src.services.crypto_adapter import SignatureCrypto
from src.services.image_steganography import ImageSteganography
from src.services.payload_service import EnvelopePayloadService
from src.services.start_location import KeyedStartLocation

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
IMAGE_COVER = SAMPLES / "lambda-icon.png"
AUDIO_COVER = SAMPLES / "audio" / "original.wav"


def load(path: Path) -> Media:
    return ApplicationController.load(str(path))


def pixels(media: Media) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(media.data)))


def samples(media: Media) -> np.ndarray:
    with wave.open(io.BytesIO(media.data), "rb") as reader:
        return np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2")


def media_attacks(kind):
    return [a for a in attacks_for(kind) if not a.targets_payload]


@pytest.mark.parametrize("attack", media_attacks(MediaType.IMAGE), ids=lambda a: a.id)
def test_image_attacks_produce_decodable_images(attack):
    cover = load(IMAGE_COVER)
    attacked = apply_attack(attack.id, cover, AttackContext(lsb=1))
    assert attacked.kind is MediaType.IMAGE
    before, after = pixels(cover), pixels(attacked)
    if attack.id == "reencode_lossless":
        assert np.array_equal(before, after) and attacked.data != cover.data
    elif attack.id == "convert_container":
        assert attacked.suffix == ".bmp" and after.shape[:2] == before.shape[:2]
    elif attack.id in {"crop_bottom", "resize"}:
        assert after.shape[0] < before.shape[0]
    else:
        assert after.shape == before.shape and not np.array_equal(before, after)


@pytest.mark.parametrize("attack", media_attacks(MediaType.AUDIO), ids=lambda a: a.id)
def test_audio_attacks_produce_decodable_wavs(attack):
    cover = load(AUDIO_COVER)
    attacked = apply_attack(attack.id, cover, AttackContext(lsb=1))
    assert attacked.kind is MediaType.AUDIO and attacked.suffix == ".wav"
    before, after = samples(cover), samples(attacked)
    if attack.id == "reencode_lossless":
        assert np.array_equal(before, after)
    elif attack.id == "truncate":
        assert len(after) < len(before)
    else:
        assert len(after) == len(before) and not np.array_equal(before, after)


def test_lsb_attacks_touch_only_low_bits():
    cover = load(IMAGE_COVER)
    for attack_id, depth in (("lsb_noise", 1), ("lsb_strip", 3)):
        attacked = apply_attack(attack_id, cover, AttackContext(lsb=depth))
        assert np.array_equal(pixels(cover) >> depth, pixels(attacked) >> depth)


def test_registry_and_errors():
    listing = describe()
    assert {row["id"] for row in listing} >= {"pixel_edit", "sample_edit", "lsb_noise", "edit_payload"}
    assert sorted(ATTACKS["lsb_noise"].kinds) == [MediaType.AUDIO, MediaType.IMAGE]
    # Shared attack ids are worded for the file type they are listed for.
    by_id = lambda kind: {row["id"]: row for row in describe(kind)}
    assert by_id(MediaType.IMAGE)["reencode_lossless"]["label"] == "Re-save losslessly"
    assert by_id(MediaType.AUDIO)["reencode_lossless"]["label"] == "Re-write the WAV"
    assert "channel" in by_id(MediaType.IMAGE)["lsb_noise"]["description"]
    assert "sample" in by_id(MediaType.AUDIO)["lsb_noise"]["description"]
    assert "sample_edit" not in by_id(MediaType.IMAGE) and "pixel_edit" not in by_id(MediaType.AUDIO)
    assert all(row["targets_payload"] for row in describe() if row["id"] in {"edit_payload", "corrupt_signature", "wipe_payload"})
    with pytest.raises(IntegrationError):
        apply_attack("no_such_attack", load(IMAGE_COVER))
    with pytest.raises(IntegrationError):
        apply_attack("sample_edit", load(IMAGE_COVER))
    with pytest.raises(IntegrationError):
        apply_attack("edit_payload", load(IMAGE_COVER), AttackContext(lsb=1))


@pytest.fixture
def controller(tmp_path):
    location = KeyedStartLocation()
    location.manual_start = 100
    return ApplicationController(
        image=ImageSteganography(), audio=WavSteganographyService(),
        crypto=SignatureCrypto(tmp_path / "keys"), payload=EnvelopePayloadService(),
        location=location)


@pytest.mark.parametrize("cover", [IMAGE_COVER, AUDIO_COVER], ids=lambda p: p.suffix)
@pytest.mark.parametrize("attack_id,expected", [
    ("edit_payload", Verdict.SIGNATURE_INVALID),
    ("forge_message", Verdict.SIGNATURE_INVALID),
    ("corrupt_signature", Verdict.SIGNATURE_INVALID),
    ("wipe_payload", Verdict.PAYLOAD_MISSING),
])
def test_payload_attacks_reach_the_expected_verdict(controller, tmp_path, cover, attack_id, expected):
    stego = tmp_path / f"stego{cover.suffix}"
    controller.save(controller.protect(str(cover), 1, "hello party B"), str(stego))
    media = load(stego)
    context = AttackContext(lsb=1, start=100, service=controller.service_for(media))
    attacked = tmp_path / f"attacked{cover.suffix}"
    attacked.write_bytes(apply_attack(attack_id, media, context).data)
    assert controller.verify(str(attacked), 1).verdict is expected
    intact = controller.verify(str(stego), 1)
    assert intact.verdict is Verdict.AUTHENTIC and intact.decoded_payload == "hello party B"
