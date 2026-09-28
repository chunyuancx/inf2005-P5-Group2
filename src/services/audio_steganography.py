from __future__ import annotations

from array import array
import io
import sys
import wave
import struct
from src.exceptions import (
    IntegrationError,
    PayloadMissing,
)
from src.exceptions import IntegrationError
from src.models import Media, MediaType



class WavSteganographyService:
    """LSB steganography for uncompressed 16-bit PCM WAV audio."""
    MAGIC = b"E1"

    HEADER = struct.Struct(
        ">2sI"
    )

    MAX_PAYLOAD_SIZE = (
        8 * 1024 * 1024
    )

    @staticmethod
    def _validate_lsb(
        lsb: int
    ) -> None:

        if (
            type(lsb) is not int
            or not 1 <= lsb <= 8
        ):
            raise IntegrationError(
                "LSB must be an integer from 1 to 8."
            )


    @staticmethod
    def _validate_start(
        start: int
    ) -> None:

        if (
            type(start) is not int
            or start < 0
        ):
            raise IntegrationError(
                "Start location must be a non-negative integer."
            )

    @staticmethod
    def _bytes_to_bits(
        data: bytes
    ) -> list[int]:

        return [
            (byte >> bit) & 1
            for byte in data
            for bit in range(
                7,
                -1,
                -1
            )
        ]

    @staticmethod
    def _bits_to_bytes(
        bits: list[int]
    ) -> bytes:

        output = bytearray()

        for offset in range(
            0,
            len(bits),
            8
        ):

            chunk = bits[
                offset:
                offset + 8
            ]

            if len(chunk) < 8:
                break

            value = 0

            for bit in chunk:
                value = (
                    value << 1
                ) | bit

            output.append(value)

        return bytes(output)

    @staticmethod
    def _set_sample_lsb(
        sample: int,
        value: int,
        lsb: int
    ) -> int:

        low_mask = (
            (1 << lsb) - 1
        )

        unsigned = (
            sample & 0xFFFF
        )

        unsigned &= (
            0xFFFF ^ low_mask
        )

        unsigned |= (
            value & low_mask
        )

        if unsigned >= 0x8000:
            unsigned -= 0x10000

        return unsigned

    @staticmethod
    def _read_bits(
        samples,
        lsb: int,
        start: int,
        sample_count: int
    ) -> list[int]:

        low_mask = (
            (1 << lsb) - 1
        )

        bits = []

        for offset in range(
            sample_count
        ):

            sample = samples[
                start + offset
            ]

            unsigned = (
                sample & 0xFFFF
            )

            value = (
                unsigned
                & low_mask
            )

            for bit_position in range(
                lsb - 1,
                -1,
                -1
            ):

                bits.append(
                    (
                        value
                        >> bit_position
                    )
                    & 1
                )

        return bits

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

    # ------------------------------------------- helpers for other members

    def sample_count(
        self,
        media: Media
    ) -> int:
        """Embeddable PCM samples, channels interleaved.

        Unchanged by embedding, unlike ``len(media.data)``; use this (not the
        file length) to derive start locations.  This is the same domain the
        ``start`` argument of ``embed`` and ``extract`` indexes into.
        """

        _, samples = (
            self._read_wav(media)
        )

        return len(samples)

    def canonical_bytes(
        self,
        media: Media,
        lsb: int
    ) -> bytes:
        """Canonical representation for hashing and start-location derivation.

        Format parameters followed by every sample with its low ``lsb`` bits
        cleared, in the same unsigned 16-bit domain ``_set_sample_lsb`` writes
        to.  Identical for the cover and its stego object at the same ``lsb``,
        whatever the start location, because embedding only ever touches the
        bits this clears.  Not covered (by design): WAV metadata chunks, and
        changes confined to the low ``lsb`` bits.
        """

        self._validate_lsb(lsb)

        params, samples = (
            self._read_wav(media)
        )

        keep_mask = (
            0xFFFF ^ ((1 << lsb) - 1)
        )

        masked = bytearray()

        for sample in samples:
            masked += (
                (sample & 0xFFFF) & keep_mask
            ).to_bytes(2, "little")

        header = (
            f"{params.nchannels}|"
            f"{params.sampwidth}|"
            f"{params.framerate}|"
            f"{params.nframes}|"
        ).encode()

        return header + bytes(masked)

    def capacity(
        self,
        media: Media,
        lsb: int,
        start: int
    ) -> int:

        self._validate_lsb(lsb)

        self._validate_start(start)

        _, samples = (
            self._read_wav(media)
        )

        if start >= len(samples):
            return 0

        remaining_samples = (
            len(samples) - start
        )

        available_bits = (
            remaining_samples * lsb
        )

        available_bytes = (
            available_bits // 8
        )

        payload_capacity = (
            available_bytes
            - self.HEADER.size
        )

        return max(
            0,
            payload_capacity
        )

    def embed(
        self,
        media: Media,
        payload: bytes,
        lsb: int,
        start: int
    ) -> bytes:

        self._validate_lsb(lsb)

        self._validate_start(start)

        params, samples = (
            self._read_wav(media)
        )

        if (
            len(payload)
            > self.MAX_PAYLOAD_SIZE
        ):
            raise IntegrationError(
                "Payload exceeds maximum allowed size."
            )

        if (
            len(payload)
            > self.capacity(
                media,
                lsb,
                start
            )
        ):
            raise IntegrationError(
                "Payload exceeds the available audio capacity."
            )

        framed = (
            self.HEADER.pack(
                self.MAGIC,
                len(payload)
            )
            + payload
        )

        bits = self._bytes_to_bits(
            framed
        )

        needed_samples = (
            len(bits) + lsb - 1
        ) // lsb

        if (
            start + needed_samples
            > len(samples)
        ):
            raise IntegrationError(
                "Embedding run exceeds audio capacity."
            )

        total_bits = (
            needed_samples * lsb
        )

        bits.extend(
            [0]
            * (
                total_bits
                - len(bits)
            )
        )

        for group_index in range(
            needed_samples
        ):

            bit_start = (
                group_index * lsb
            )

            chunk = bits[
                bit_start:
                bit_start + lsb
            ]

            value = 0

            for bit in chunk:
                value = (
                    value << 1
                ) | bit

            sample_index = (
                start + group_index
            )

            samples[
                sample_index
            ] = self._set_sample_lsb(
                samples[
                    sample_index
                ],
                value,
                lsb
            )

        return self._write_wav(
            params,
            samples
        )

    def extract(
        self,
        media: Media,
        lsb: int,
        start: int
    ) -> bytes:

        self._validate_lsb(lsb)

        self._validate_start(start)

        _, samples = (
            self._read_wav(media)
        )

        header_bits = (
            self.HEADER.size * 8
        )

        header_samples = (
            header_bits + lsb - 1
        ) // lsb

        if (
            start + header_samples
            > len(samples)
        ):
            raise PayloadMissing(
                "Start location is outside the audio payload area."
            )

        bits = self._read_bits(
            samples,
            lsb,
            start,
            header_samples
        )

        header_bytes = (
            self._bits_to_bytes(
                bits[:header_bits]
            )
        )

        try:
            (
                magic,
                payload_length
            ) = self.HEADER.unpack(
                header_bytes
            )

        except struct.error as exc:

            raise PayloadMissing(
                "Could not read an audio payload header."
            ) from exc

        if magic != self.MAGIC:

            raise PayloadMissing(
                "No valid audio payload was found."
            )

        if (
            payload_length <= 0
            or payload_length
            > self.MAX_PAYLOAD_SIZE
        ):
            raise PayloadMissing(
                "Audio payload length is invalid."
            )

        total_bits = (
            (
                self.HEADER.size
                + payload_length
            )
            * 8
        )

        total_samples = (
            total_bits + lsb - 1
        ) // lsb

        if (
            start + total_samples
            > len(samples)
        ):
            raise PayloadMissing(
                "Embedded audio payload is incomplete."
            )

        all_bits = self._read_bits(
            samples,
            lsb,
            start,
            total_samples
        )

        framed = self._bits_to_bytes(
            all_bits[:total_bits]
        )

        return framed[
            self.HEADER.size:
            self.HEADER.size
            + payload_length
        ]