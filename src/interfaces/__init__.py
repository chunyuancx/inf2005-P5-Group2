"""Contracts only: teammates provide concrete adapters."""
from typing import Protocol

from src.models import Media, Payload


class SteganographyService(Protocol):
    def capacity(self, media: Media, lsb: int, start: int) -> int:
        """Return available payload BYTES after framing and start offset."""
        ...

    def embed(self, media: Media, payload: bytes, lsb: int, start: int) -> bytes: ...

    def extract(self, media: Media, lsb: int, start: int) -> bytes:
        """Raise PayloadMissing when no envelope is present."""
        ...


class ImageSteganographyService(SteganographyService, Protocol):
    pass


class AudioSteganographyService(SteganographyService, Protocol):
    pass


class CryptoService(Protocol):
    def hash_media(self, media: Media, lsb: int) -> bytes:
        """Hash agreed canonical media excluding reserved embedding bits.

        Raw file hashing is NOT suitable: embedding changes file bytes.
        The canonicalization policy must also cover recovery headers.
        """
        ...

    def sign(self, data: bytes) -> bytes:
        """Use configured signing key; key handling belongs to Member 3."""
        ...

    def verify_signature(self, data: bytes, signature: bytes) -> bool: ...


class StartLocationService(Protocol):
    def generate(self, media: Media, lsb: int) -> int: ...

    def recover(self, media: Media, lsb: int) -> int:
        """Recover independently of the embedded payload (avoid circularity)."""
        ...


class PayloadService(Protocol):
    def create(self, media: Media, digest: bytes) -> bytes:
        """Build canonical signed content with ID, timestamp, nonce, metadata."""
        ...

    def pack(self, signed_data: bytes, signature: bytes) -> bytes: ...

    def unpack(self, encoded: bytes) -> Payload:
        """Validate schema; derive digest from signed_data, never unsigned fields."""
        ...
