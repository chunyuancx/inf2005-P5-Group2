from __future__ import annotations

from array import array
import io
import sys
import wave

from src.exceptions import IntegrationError
from src.models import Media, MediaType


class WavSteganographyService:
    """LSB steganography for uncompressed 16-bit PCM WAV audio."""

    def _read_wav(self, media: Media):
        if media.kind != MediaType.AUDIO:
            raise IntegrationError(
                "Media is not an audio file."
            )

        if media.suffix.lower() != ".wav":
            raise IntegrationError(
                "Only WAV audio is supported."
            )

        try:
            buffer = io.BytesIO(media.data)

            with wave.open(buffer, "rb") as wav_file:

                if wav_file.getcomptype() != "NONE":
                    raise IntegrationError(
                        "Only uncompressed PCM WAV files are supported."
                    )

                if wav_file.getsampwidth() != 2:
                    raise IntegrationError(
                        "Only 16-bit PCM WAV files are currently supported."
                    )

                params = wav_file.getparams()

                frames = wav_file.readframes(
                    wav_file.getnframes()
                )

        except wave.Error as exc:
            raise IntegrationError(
                "Invalid or unsupported WAV file."
            ) from exc

        samples = array("h")
        samples.frombytes(frames)

        if sys.byteorder != "little":
            samples.byteswap()


        return params, samples

    def _write_wav(
        self,
        params,
        samples: array
    ) -> bytes:

        output_samples = array(
            "h",
            samples
        )

        if sys.byteorder != "little":
            output_samples.byteswap()

        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav_file:
            wav_file.setparams(params)
            wav_file.writeframes(
                output_samples.tobytes()
            )

        return buffer.getvalue()

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