"""Fault injection at service boundaries; NOT real cryptographic/media tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from src.controllers import ApplicationController
from src.exceptions import IntegrationError, WrongStartLocation
from src.interfaces import (AudioSteganographyService, CryptoService,
                            ImageSteganographyService, PayloadService, StartLocationService)
from src.models import Payload, Verdict
from src.testing.runner import Scenario


EXPECTED = {
    "unchanged": Verdict.AUTHENTIC,
    "media_tampering": Verdict.TAMPERED,
    "payload_corruption": Verdict.SIGNATURE_INVALID,
    "signature_corruption": Verdict.SIGNATURE_INVALID,
    "wrong_key": Verdict.SIGNATURE_INVALID,
    "wrong_start_location": Verdict.WRONG_START_LOCATION,
    "missing_payload": Verdict.PAYLOAD_MISSING,
    "malformed_payload": Verdict.CANNOT_VERIFY,
}


def execute_mock_case(case_name: str, suffix: str, lsb: int):
    if case_name not in EXPECTED:
        raise ValueError("Unknown mock scenario")
    image = Mock(spec=ImageSteganographyService)
    audio = Mock(spec=AudioSteganographyService)
    crypto = Mock(spec=CryptoService)
    payload = Mock(spec=PayloadService)
    location = Mock(spec=StartLocationService)
    controller = ApplicationController(image, audio, crypto, payload, location)
    stego = audio if suffix == ".wav" else image
    location.generate.return_value = location.recover.return_value = 12
    crypto.hash_media.return_value = b"original digest"
    crypto.sign.return_value = b"signature"
    crypto.verify_signature.side_effect = lambda data, signature: (
        data == b"signed content" and signature == b"signature")
    payload.create.return_value = b"signed content"
    payload.pack.return_value = b"envelope"
    payload.unpack.return_value = Payload(b"signed content", b"original digest", b"signature")
    stego.capacity.return_value = 1024
    stego.embed.return_value = b"mock stego file"
    stego.extract.return_value = b"envelope"
    with TemporaryDirectory() as folder:
        original = Path(folder) / f"original{suffix}"
        protected = Path(folder) / f"protected{suffix}"
        original.write_bytes(b"mock original file")
        controller.save(controller.protect(str(original), lsb), str(protected))
        # Party B faults are injected only after Party A protects and saves.
        if case_name == "media_tampering":
            crypto.hash_media.return_value = b"changed digest"
        elif case_name == "payload_corruption":
            payload.unpack.return_value = Payload(b"corrupt content", b"original digest", b"signature")
        elif case_name == "signature_corruption":
            payload.unpack.return_value = Payload(b"signed content", b"original digest", b"corrupt signature")
        elif case_name == "wrong_key":
            crypto.verify_signature.side_effect = None
            crypto.verify_signature.return_value = False
        elif case_name == "wrong_start_location":
            location.recover.side_effect = WrongStartLocation("Mock wrong recovery context")
        elif case_name == "missing_payload":
            stego.extract.return_value = b""
        elif case_name == "malformed_payload":
            payload.unpack.side_effect = IntegrationError("Mock malformed envelope")
        return controller.verify(str(protected), lsb)


def build_mock_scenarios() -> list[Scenario]:
    return [Scenario(f"{kind}/lsb-{lsb}/{case_name}", expected,
                     lambda a=case_name, s=suffix, bits=lsb: execute_mock_case(a, s, bits),
                     kind, lsb)
            for kind, suffix in (("image", ".png"), ("audio", ".wav"))
            for lsb in range(1, 9) for case_name, expected in EXPECTED.items()]
