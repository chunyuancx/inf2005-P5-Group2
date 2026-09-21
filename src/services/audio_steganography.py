from __future__ import annotations

from src.models import Media


class WavSteganographyService:
    """LSB steganography for PCM WAV audio."""

    def capacity(
        self,
        media: Media,
        lsb: int,
        start: int
    ) -> int:
        raise NotImplementedError

    def embed(
        self,
        media: Media,
        payload: bytes,
        lsb: int,
        start: int
    ) -> bytes:
        raise NotImplementedError

    def extract(
        self,
        media: Media,
        lsb: int,
        start: int
    ) -> bytes:
        raise NotImplementedError