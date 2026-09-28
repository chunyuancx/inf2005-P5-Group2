import io
import math
import struct
import unittest
import wave
from src.exceptions import (
    IntegrationError,
    PayloadMissing,
)
from src.models import Media, MediaType
from src.services.audio_steganography import (
    WavSteganographyService
)


def create_test_wav(
    duration_seconds: float = 1.0,
    sample_rate: int = 8000
) -> bytes:

    sample_count = int(
        duration_seconds * sample_rate
    )

    samples = []

    for i in range(sample_count):

        value = int(
            12000
            * math.sin(
                2
                * math.pi
                * 440
                * i
                / sample_rate
            )
        )

        samples.append(value)

    pcm_data = struct.pack(
        f"<{len(samples)}h",
        *samples
    )

    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav_file:

        wav_file.setnchannels(1)

        wav_file.setsampwidth(2)

        wav_file.setframerate(
            sample_rate
        )

        wav_file.writeframes(
            pcm_data
        )

    return buffer.getvalue()


class AudioSteganographyTests(
    unittest.TestCase
):

    def setUp(self):

        self.service = (
            WavSteganographyService()
        )

        self.media = Media(
            data=create_test_wav(),
            suffix=".wav",
            kind=MediaType.AUDIO
        )

    def test_read_wav(self):

        params, samples = (
            self.service._read_wav(
                self.media
            )
        )

        self.assertEqual(
            params.nchannels,
            1
        )

        self.assertEqual(
            params.sampwidth,
            2
        )

        self.assertEqual(
            params.framerate,
            8000
        )

        self.assertGreater(
            len(samples),
            0
        )

    def test_wav_round_trip(self):

        params, samples = (
            self.service._read_wav(
                self.media
            )
        )

        rebuilt = (
            self.service._write_wav(
                params,
                samples
            )
        )

        rebuilt_media = Media(
            data=rebuilt,
            suffix=".wav",
            kind=MediaType.AUDIO
        )

        new_params, new_samples = (
            self.service._read_wav(
                rebuilt_media
            )
        )

        self.assertEqual(
            params.nchannels,
            new_params.nchannels
        )

        self.assertEqual(
            params.framerate,
            new_params.framerate
        )

        self.assertEqual(
            list(samples),
            list(new_samples)
        )

    def test_embed_extract_one_lsb(
        self
    ):

        payload = b"Hello"

        stego_bytes = (
            self.service.embed(
                self.media,
                payload,
                lsb=1,
                start=100
            )
        )

        stego_media = Media(
            data=stego_bytes,
            suffix=".wav",
            kind=MediaType.AUDIO
        )

        extracted = (
            self.service.extract(
                stego_media,
                lsb=1,
                start=100
            )
        )

        self.assertEqual(
            extracted,
            payload
        )

    def test_all_lsb_depths(
        self
    ):

        payload = (
            b"INF2005 Audio Steganography"
        )

        for lsb in range(1, 9):

            with self.subTest(
                lsb=lsb
            ):

                stego_bytes = (
                    self.service.embed(
                        self.media,
                        payload,
                        lsb=lsb,
                        start=100
                    )
                )

                stego_media = Media(
                    data=stego_bytes,
                    suffix=".wav",
                    kind=MediaType.AUDIO
                )

                extracted = (
                    self.service.extract(
                        stego_media,
                        lsb=lsb,
                        start=100
                    )
                )

                self.assertEqual(
                    extracted,
                    payload
                )

    def test_nonzero_start_location(
        self
    ):

        payload = (
            b"Secret audio payload"
        )

        start = 2500

        stego_bytes = (
            self.service.embed(
                self.media,
                payload,
                lsb=2,
                start=start
            )
        )

        stego_media = Media(
            data=stego_bytes,
            suffix=".wav",
            kind=MediaType.AUDIO
        )

        extracted = (
            self.service.extract(
                stego_media,
                lsb=2,
                start=start
            )
        )

        self.assertEqual(
            extracted,
            payload
        )

    def test_payload_too_large(
        self
    ):

        capacity = (
            self.service.capacity(
                self.media,
                lsb=1,
                start=0
            )
        )

        payload = (
            b"A"
            * (capacity + 1)
        )

        with self.assertRaises(
            IntegrationError
        ):

            self.service.embed(
                self.media,
                payload,
                lsb=1,
                start=0
            )

    def test_unprotected_audio_has_no_payload(
        self
    ):

        with self.assertRaises(
            PayloadMissing
        ):

            self.service.extract(
                self.media,
                lsb=1,
                start=100
            )

if __name__ == "__main__":
    unittest.main()