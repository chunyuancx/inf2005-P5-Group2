"""Locate payload envelopes in a file, for the attack lab's error messages.

When a verification says Payload Missing, the commonest cause in the studio
is a wrong LSB depth or manual position. Scanning the file for the framing
header used by the steganography services tells the user where the payload
really is, so the message can say "set the position to 2000" instead of
leaving them guessing. Only used for diagnostics; verification never relies
on it.
"""
import struct
import zlib

import numpy as np

from src.attacks import audio as audio_attacks
from src.attacks import image as image_attacks
from src.models import Media, MediaType

IMAGE_HEADER = struct.Struct(">2sII")  # "IS", payload length, CRC-32 of magic + length
AUDIO_HEADER = struct.Struct(">2sI")   # "E1", payload length
ENVELOPE_MAGIC = b"P1"                # the signed envelope always starts with this
MAX_HITS = 8


def _units(media: Media) -> np.ndarray:
    """The embeddable units in embedding order, as unsigned integers."""
    if media.kind is MediaType.IMAGE:
        pixels, _ = image_attacks.load(media)
        if pixels.ndim == 3:
            colour = 3 if pixels.shape[2] >= 3 else 1
            return pixels.reshape(-1, pixels.shape[2])[:, :colour].reshape(-1).astype(np.uint16)
        return pixels.reshape(-1).astype(np.uint16)
    _, samples = audio_attacks.load(media)
    return samples.astype(np.uint16)


def find_envelopes(media: Media, lsb: int) -> list[tuple[int, int]]:
    """(start unit, payload length) of every plausible envelope at this depth."""
    units = _units(media)
    magic, header = (b"IS", IMAGE_HEADER) if media.kind is MediaType.IMAGE else (b"E1", AUDIO_HEADER)
    low = (units & ((1 << lsb) - 1)).astype(np.uint8)
    bits = np.unpackbits(low[:, None], axis=1)[:, 8 - lsb:].reshape(-1)  # MSB-first within a unit
    hits = []
    for offset in range(8):
        packed = np.packbits(bits[offset:])
        for index in np.flatnonzero((packed[:-1] == magic[0]) & (packed[1:] == magic[1])):
            bit = offset + 8 * int(index)
            if bit % lsb:
                continue
            head = packed[index:index + header.size].tobytes()
            if len(head) < header.size:
                continue
            fields = header.unpack(head)
            length = fields[1]
            if media.kind is MediaType.IMAGE and fields[2] != zlib.crc32(head[:6]):
                continue
            if not 0 < length <= 8 * 1024 * 1024:
                continue
            envelope = packed[index + header.size:index + header.size + 2].tobytes()
            if envelope != ENVELOPE_MAGIC:
                continue
            hits.append((bit // lsb, int(length)))
            if len(hits) >= MAX_HITS:
                return hits
    return hits
