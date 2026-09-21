"""Image LSB-replacement steganography service (Member 1).

Implements ``src.interfaces.ImageSteganographyService`` for PNG and BMP covers
using Pillow for decoding/encoding and NumPy for the bit manipulation.

Conventions (everything teammates need to agree with)
-----------------------------------------------------
Unit
    One 8-bit colour sample of the *decoded* image, counted in row-major order
    (R, G, B of pixel 0, then R, G, B of pixel 1, ...).  ``start`` and
    ``capacity()`` are measured in units.  Alpha samples are never used, so
    transparency is left untouched.  A grayscale image has one unit per pixel.

Canonical mode
    Decoded images are normalised so the unit count is identical before and
    after embedding:  1-bit/L -> L,  RGB -> RGB,  palette -> RGB (RGBA if it
    has transparency, PNG only),  LA/RGBA -> RGBA (PNG) or RGB (BMP, which
    cannot carry alpha through Pillow).  Anything else (e.g. 16-bit PNG) is
    rejected with ``UnsupportedFileType`` rather than silently degraded.

Bit order
    MSB-first per payload byte, matching ``tests/fakes.py``.  ``lsb`` bits are
    written to the low ``lsb`` bits of each unit, first bit in the highest of
    those positions.  The bit stream is continuous (not byte-aligned per unit);
    only the final unit is zero-padded.

Envelope framing (because ``extract()`` is given no length)
    ``>2sII`` = magic ``b"IS"`` | payload length | CRC-32 of (magic + length),
    followed by the payload.  The CRC covers the *header only*: it makes a
    wrong start / wrong LSB depth read as ``PayloadMissing`` with negligible
    false-positive odds.  The payload itself is deliberately NOT checksummed
    here, so a modified payload reaches the crypto layer and yields
    ``Signature Invalid`` instead of a generic LSB-layer failure.

Output container
    The stego image is re-encoded losslessly in the SAME container as the cover
    (``.png`` -> PNG, ``.bmp`` -> BMP) so it matches the suffix that
    ``ApplicationController`` attaches and ``save()`` enforces.

Rules for teammates (Members 3 and 4)
    The stego file is re-encoded, so its byte length and raw bytes differ from
    the cover's.  Never derive the start location from ``len(media.data)`` and
    never hash raw file bytes.  Use ``ImageSteganography.unit_count(media)``
    (invariant under embedding) for offsets, and hash
    ``ImageSteganography.canonical_bytes(media, lsb)`` in ``hash_media``.
"""
from __future__ import annotations

import io
import operator
import struct
import zlib

import numpy as np
from PIL import Image

from src.exceptions import IntegrationError, PayloadMissing, UnsupportedFileType
from src.models import Media

_CONTAINERS = {".png": "PNG", ".bmp": "BMP"}
# canonical mode -> (embeddable colour samples per pixel, total samples per pixel)
_CHANNELS = {"L": (1, 1), "RGB": (3, 3), "RGBA": (3, 4)}


class ImageSteganography:
    MAGIC = b"IS"
    HEADER = struct.Struct(">2sII")  # magic, payload length, CRC-32(magic + length)

    # ------------------------------------------------------------ public API

    def capacity(self, media: Media, lsb: int, start: int) -> int:
        """Payload BYTES that fit after the framing header, from ``start``."""
        self._check_lsb(lsb)
        start = self._check_start(start)
        if start < 0:
            return 0
        remaining_units = max(0, self.unit_count(media) - start)
        remaining_bits = remaining_units * lsb
        return max(0, (remaining_bits - self.HEADER.size * 8) // 8)

    def embed(self, media: Media, payload: bytes, lsb: int, start: int) -> bytes:
        self._check_lsb(lsb)
        start = self._check_start(start)
        if not payload:
            raise IntegrationError("Payload is empty.")
        container = self._container(media)

        pixels, mode = self._decode(media)
        n_color, n_total = _CHANNELS[mode]
        total_units = pixels.shape[0] * pixels.shape[1] * n_color

        framed = self._frame(payload)
        needed_units = -(-len(framed) * 8 // lsb)
        if start < 0 or start + needed_units > total_units:
            raise IntegrationError("Payload exceeds the available media capacity.")

        bits = np.unpackbits(np.frombuffer(framed, dtype=np.uint8))  # MSB-first
        values = self._bits_to_units(bits, lsb)
        flat = pixels.reshape(-1)
        idx = self._unit_indices(start, needed_units, n_color, n_total)
        keep_mask = np.uint8((0xFF << lsb) & 0xFF)
        flat[idx] = (flat[idx] & keep_mask) | values

        buffer = io.BytesIO()
        Image.fromarray(flat.reshape(pixels.shape)).save(buffer, format=container)
        return buffer.getvalue()

    def extract(self, media: Media, lsb: int, start: int) -> bytes:
        """Return the embedded payload. Raises PayloadMissing if no envelope."""
        self._check_lsb(lsb)
        start = self._check_start(start)

        pixels, mode = self._decode(media)
        n_color, n_total = _CHANNELS[mode]
        total_units = pixels.shape[0] * pixels.shape[1] * n_color
        flat = pixels.reshape(-1)

        header_units = -(-self.HEADER.size * 8 // lsb)
        if start < 0 or start + header_units > total_units:
            raise PayloadMissing("Start location is outside the cover image.")

        header = self._read_bytes(flat, start, self.HEADER.size, lsb, n_color, n_total)
        magic, length, check = self.HEADER.unpack(header)
        if magic != self.MAGIC or check != zlib.crc32(header[:6]) or length <= 0:
            raise PayloadMissing("No valid envelope at this location.")

        available_bits = (total_units - start) * lsb
        if (self.HEADER.size + length) * 8 > available_bits:
            raise PayloadMissing("Envelope declares more data than the image holds.")

        framed = self._read_bytes(
            flat, start, self.HEADER.size + length, lsb, n_color, n_total
        )
        return framed[self.HEADER.size:]

    # ------------------------------------------- helpers for other members

    @classmethod
    def unit_count(cls, media: Media) -> int:
        """Embeddable units in the image. Unchanged by embedding, unlike
        ``len(media.data)``; use this (not the file length) to derive starts."""
        width, height, mode = cls._probe(media)
        return width * height * _CHANNELS[mode][0]

    @classmethod
    def canonical_bytes(cls, media: Media, lsb: int) -> bytes:
        """Canonical representation for ``CryptoService.hash_media``.

        Mode + dimensions + every colour sample with its low ``lsb`` bits
        cleared.  Identical for the cover and its stego image (at the same
        ``lsb``) whatever the start location, because the start is not known
        to hash_media.  Alpha samples are included unmasked.  Hash the return
        value with SHA-256.  Not covered (by design): file metadata, and
        changes confined to the low ``lsb`` bits.
        """
        cls._check_lsb(lsb)
        pixels, mode = cls._decode(media)
        n_color, n_total = _CHANNELS[mode]
        keep_mask = (0xFF << lsb) & 0xFF
        masked = pixels.copy()
        if n_total == n_color:
            masked &= keep_mask
        else:
            masked[..., :n_color] &= keep_mask
        height, width = pixels.shape[:2]
        return f"{mode}|{width}x{height}|".encode() + masked.tobytes()

    # ------------------------------------------------------------ validation

    @staticmethod
    def _check_lsb(lsb: int) -> None:
        if type(lsb) is not int or not 1 <= lsb <= 8:
            raise IntegrationError("LSB must be an integer from 1 to 8.")

    @staticmethod
    def _check_start(start: int) -> int:
        try:
            return operator.index(start)  # also accepts NumPy integers
        except TypeError as exc:
            raise IntegrationError("Start location must be an integer.") from exc

    @staticmethod
    def _container(media: Media) -> str:
        try:
            return _CONTAINERS[media.suffix.lower()]
        except KeyError:
            raise UnsupportedFileType("Image covers must be PNG or BMP.") from None

    # ----------------------------------------------------------- image I/O

    @classmethod
    def _open(cls, media: Media) -> tuple[Image.Image, str]:
        container = cls._container(media)
        try:
            img = Image.open(io.BytesIO(media.data))
        except Exception as exc:  # unidentified, truncated, decompression bomb...
            raise IntegrationError("The file is not a readable PNG or BMP image.") from exc
        if img.format not in _CONTAINERS.values():
            raise UnsupportedFileType(
                "Only lossless PNG and BMP covers are supported "
                f"(this file is {img.format})."
            )
        if getattr(img, "n_frames", 1) > 1:
            raise UnsupportedFileType("Animated images are not supported.")
        return img, container

    @staticmethod
    def _canonical_mode(img: Image.Image, container: str) -> str:
        mode = img.mode
        if mode in ("1", "L"):
            return "L"
        if mode == "RGB":
            return "RGB"
        if mode in ("RGBA", "LA", "PA"):
            has_alpha = True
        elif mode == "P":
            has_alpha = "transparency" in img.info
        else:
            raise UnsupportedFileType(
                f"Unsupported image mode '{mode}' "
                "(8-bit grayscale, palette, RGB and RGBA only)."
            )
        return "RGBA" if has_alpha and container == "PNG" else "RGB"

    @classmethod
    def _probe(cls, media: Media) -> tuple[int, int, str]:
        """Dimensions and canonical mode from the header only (no pixel decode)."""
        img, container = cls._open(media)
        width, height = img.size
        return width, height, cls._canonical_mode(img, container)

    @classmethod
    def _decode(cls, media: Media) -> tuple[np.ndarray, str]:
        """Writable uint8 array in canonical mode: (h, w) for L, else (h, w, c)."""
        img, container = cls._open(media)
        mode = cls._canonical_mode(img, container)
        try:
            img.load()
            if img.mode != mode:
                img = img.convert(mode)
            return np.array(img, dtype=np.uint8), mode
        except Exception as exc:
            raise IntegrationError("Could not decode the image data.") from exc

    # ------------------------------------------------------- bit twiddling

    @classmethod
    def _frame(cls, payload: bytes) -> bytes:
        head = cls.MAGIC + struct.pack(">I", len(payload))
        return head + struct.pack(">I", zlib.crc32(head)) + payload

    @staticmethod
    def _unit_indices(start: int, count: int, n_color: int, n_total: int) -> np.ndarray:
        """Map unit numbers to positions in the flattened array, skipping alpha."""
        units = np.arange(start, start + count, dtype=np.int64)
        if n_color == n_total:
            return units
        return (units // n_color) * n_total + (units % n_color)

    @staticmethod
    def _bits_to_units(bits: np.ndarray, lsb: int) -> np.ndarray:
        """Group MSB-first bits into ``lsb``-bit values (zero-padding the tail)."""
        pad = (-len(bits)) % lsb
        if pad:
            bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
        weights = (1 << np.arange(lsb - 1, -1, -1)).astype(np.uint16)
        groups = bits.reshape(-1, lsb).astype(np.uint16)
        return (groups * weights).sum(axis=1).astype(np.uint8)

    @classmethod
    def _read_bytes(cls, flat: np.ndarray, start: int, n_bytes: int, lsb: int,
                    n_color: int, n_total: int) -> bytes:
        units_needed = -(-n_bytes * 8 // lsb)
        idx = cls._unit_indices(start, units_needed, n_color, n_total)
        low = flat[idx] & np.uint8((1 << lsb) - 1)
        shifts = np.arange(lsb - 1, -1, -1, dtype=np.uint8)
        bits = ((low[:, None] >> shifts) & 1).astype(np.uint8).reshape(-1)
        return np.packbits(bits[: n_bytes * 8]).tobytes()
