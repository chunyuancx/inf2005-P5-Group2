"""Adapts Member 3's CryptoService to the src.interfaces.CryptoService contract.

Member 3's class works on raw bytes with explicit keys. The controller needs
``hash_media(media, lsb)``, ``sign(data)`` and ``verify_signature(data, sig)``,
so this adapter supplies the canonical media bytes and holds a persistent key
pair. Keys must outlive the session, otherwise a file protected today could
never be verified tomorrow.
"""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from src.exceptions import IntegrationError, ServiceUnavailable
from src.models import Media, MediaType
from src.services.audio_steganography import WavSteganographyService
from src.services.crypto_service import CryptoService
from src.services.image_steganography import ImageSteganography

DEFAULT_KEY_DIR = Path.home() / ".inf2005-stego" / "keys"
PRIVATE_KEY_FILE = "private_key.pem"
PUBLIC_KEY_FILE = "public_key.pem"


class SignatureCrypto:
    def __init__(self, key_dir: str | Path = DEFAULT_KEY_DIR):
        self.key_dir = Path(key_dir)
        self._private_key = None
        self._public_key = None

    @property
    def private_path(self) -> Path:
        return self.key_dir / PRIVATE_KEY_FILE

    @property
    def public_path(self) -> Path:
        return self.key_dir / PUBLIC_KEY_FILE

    def hash_media(self, media: Media, lsb: int) -> bytes:
        if media.kind == MediaType.IMAGE:
            canonical = ImageSteganography.canonical_bytes(media, lsb)
        elif media.kind == MediaType.AUDIO:
            canonical = WavSteganographyService().canonical_bytes(media, lsb)
        else:
            raise IntegrationError("Unsupported media type for hashing.")
        return CryptoService.generate_hash(canonical)

    def sign(self, data: bytes) -> bytes:
        return CryptoService.sign_payload(self._load_private_key(), data)

    def verify_signature(self, data: bytes, signature: bytes) -> bool:
        return CryptoService.verify_signature(self._load_public_key(), signature, data)

    def _load_private_key(self):
        if self._private_key is None:
            if not self.private_path.exists():
                self._generate_keys()
            try:
                self._private_key = serialization.load_pem_private_key(
                    self.private_path.read_bytes(), password=None)
            except (OSError, ValueError) as exc:
                raise ServiceUnavailable("Cannot load the signing key.") from exc
        return self._private_key

    def _load_public_key(self):
        if self._public_key is None:
            # Verification never creates keys: a fresh pair could only ever
            # report Signature Invalid, which would hide the real problem.
            if not self.public_path.exists():
                raise ServiceUnavailable(
                    f"No public key found at {self.public_path}; "
                    "protect a file first or copy the sender's public key there.")
            try:
                self._public_key = serialization.load_pem_public_key(
                    self.public_path.read_bytes())
            except (OSError, ValueError) as exc:
                raise ServiceUnavailable("Cannot load the verification key.") from exc
        return self._public_key

    def _generate_keys(self) -> None:
        private_key, public_key = CryptoService.generate_key_pair()
        try:
            self.key_dir.mkdir(parents=True, exist_ok=True)
            private_pem = private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())
            # Owner-only permissions; the private key is stored unencrypted.
            fd = os.open(self.private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(private_pem)
            self.public_path.write_bytes(public_key.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo))
        except OSError as exc:
            raise ServiceUnavailable("Cannot create the signing key pair.") from exc
