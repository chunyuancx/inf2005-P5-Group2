import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.controllers import ApplicationController
from src.exceptions import IntegrationError, PayloadMissing, UnsupportedFileType, WrongStartLocation
from src.interfaces import (AudioSteganographyService, CryptoService,
                            ImageSteganographyService, PayloadService, StartLocationService)
from src.models import MediaType, Payload, Verdict
from src.services import UnconfiguredService


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "input.png"
        self.path.write_bytes(b"mock media, not a real image")
        self.image = Mock(spec=ImageSteganographyService)
        self.audio = Mock(spec=AudioSteganographyService)
        self.crypto = Mock(spec=CryptoService)
        self.payload = Mock(spec=PayloadService)
        self.location = Mock(spec=StartLocationService)
        self.controller = ApplicationController(self.image, self.audio, self.crypto, self.payload, self.location)
        self.location.generate.return_value = 10
        self.location.recover.return_value = 10
        self.crypto.hash_media.return_value = b"digest"
        self.crypto.sign.return_value = b"signature"
        self.crypto.verify_signature.return_value = True
        self.payload.create.return_value = b"signed content"
        self.payload.pack.return_value = b"envelope"
        self.payload.unpack.return_value = Payload(b"signed content", b"digest", b"signature")
        for service in (self.image, self.audio):
            service.capacity.return_value = 100
            service.extract.return_value = b"envelope"
            service.embed.return_value = b"mock stego"

    def test_media_type_routing(self):
        for suffix, expected in ((".png", MediaType.IMAGE), (".BMP", MediaType.IMAGE), (".wav", MediaType.AUDIO)):
            with self.subTest(suffix=suffix):
                path = self.path.with_suffix(suffix)
                path.write_bytes(b"mock input")
                self.image.reset_mock()
                self.audio.reset_mock()
                media = self.controller.protect(str(path), 8)
                self.assertEqual(media.kind, expected)
                active, inactive = (self.image, self.audio) if expected == MediaType.IMAGE else (self.audio, self.image)
                active.embed.assert_called_once()
                inactive.embed.assert_not_called()
                self.controller.verify(str(path), 8)
                active.extract.assert_called_once()
                inactive.extract.assert_not_called()

    def test_successful_verification(self):
        result = self.controller.verify(str(self.path), 1)
        self.assertEqual(result.verdict, Verdict.AUTHENTIC)
        self.assertEqual(result.statuses["hash"], "Match")
        self.crypto.verify_signature.assert_called_once_with(b"signed content", b"signature")

    def test_invalid_signature_skips_hash(self):
        self.crypto.verify_signature.return_value = False
        result = self.controller.verify(str(self.path), 1)
        self.assertEqual(result.verdict, Verdict.SIGNATURE_INVALID)
        self.crypto.hash_media.assert_not_called()
        self.assertEqual(result.statuses["hash"], "Not run")

    def test_hash_mismatch(self):
        self.crypto.hash_media.return_value = b"changed"
        self.assertEqual(self.controller.verify(str(self.path), 1).verdict, Verdict.TAMPERED)

    def test_payload_missing(self):
        self.image.extract.side_effect = PayloadMissing("No payload")
        self.assertEqual(self.controller.verify(str(self.path), 1).verdict, Verdict.PAYLOAD_MISSING)
        self.crypto.verify_signature.assert_not_called()

    def test_empty_payload(self):
        self.image.extract.return_value = b""
        self.assertEqual(self.controller.verify(str(self.path), 1).verdict, Verdict.PAYLOAD_MISSING)

    def test_wrong_start_location(self):
        self.location.recover.side_effect = WrongStartLocation("Recovery failed")
        self.assertEqual(self.controller.verify(str(self.path), 1).verdict, Verdict.WRONG_START_LOCATION)
        self.image.extract.assert_not_called()

    def test_unsupported_file_type(self):
        path = str(self.path.with_suffix(".mp3"))
        with self.assertRaises(UnsupportedFileType):
            self.controller.protect(path, 1)
        self.assertEqual(self.controller.verify(path, 1).verdict, Verdict.CANNOT_VERIFY)

    def test_cannot_verify(self):
        self.payload.unpack.side_effect = ValueError("Malformed envelope")
        with self.assertLogs("src.verification.engine", level="ERROR"):
            result = self.controller.verify(str(self.path), 1)
        self.assertEqual(result.verdict, Verdict.CANNOT_VERIFY)
        self.crypto.verify_signature.assert_not_called()

    def test_unconfigured_services_fail_closed(self):
        controller = ApplicationController(*(UnconfiguredService() for _ in range(5)))
        self.assertEqual(controller.verify(str(self.path), 1).verdict, Verdict.CANNOT_VERIFY)
        with self.assertRaises(IntegrationError):
            controller.protect(str(self.path), 1)

    def test_lsb_range(self):
        for lsb in range(1, 9):
            self.controller.validate_lsb(lsb)
        for lsb in (0, 9, True, "1", 1.5):
            with self.subTest(lsb=lsb), self.assertRaises(IntegrationError):
                self.controller.protect(str(self.path), lsb)

    def test_capacity_failure_does_not_embed(self):
        self.image.capacity.return_value = 0
        with self.assertRaises(IntegrationError):
            self.controller.protect(str(self.path), 1)
        self.image.embed.assert_not_called()

    def test_party_a_to_party_b_mock_workflow(self):
        protected = self.controller.protect(str(self.path), 2)
        saved = Path(self.temp.name) / "stego.png"
        self.controller.save(protected, str(saved))
        self.assertEqual(saved.read_bytes(), b"mock stego")
        self.assertEqual(self.controller.verify(str(saved), 2).verdict, Verdict.AUTHENTIC)
        self.payload.create.assert_called_once_with(self.controller.load(str(self.path)), b"digest")
        self.crypto.sign.assert_called_once_with(b"signed content")
        self.payload.pack.assert_called_once_with(b"signed content", b"signature")
        self.image.embed.assert_called_once_with(self.controller.load(str(self.path)), b"envelope", 2, 10)
        self.image.extract.assert_called_once_with(protected, 2, 10)

    def test_save_preserves_existing_files_and_format(self):
        media = self.controller.protect(str(self.path), 1)
        with self.assertRaises(IntegrationError):
            self.controller.save(media, str(self.path))
        self.assertEqual(self.path.read_bytes(), b"mock media, not a real image")
        with self.assertRaises(IntegrationError):
            self.controller.save(media, str(self.path.with_suffix(".jpg")))

    def test_missing_file(self):
        self.path.unlink()
        self.assertEqual(self.controller.verify(str(self.path), 1).verdict, Verdict.CANNOT_VERIFY)


if __name__ == "__main__":
    unittest.main()
