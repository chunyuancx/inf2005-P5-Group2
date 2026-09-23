"""PayloadService built on Member 3's Payload model.

Envelope layout: ``>2sHH`` = magic ``b"P1"`` | signed_data length |
signature length, followed by signed_data then signature. The steganography
services already frame the whole envelope, so this layer only has to split
it. The media digest lives inside signed_data, so the signature covers it.
"""
import json
import struct

from src.exceptions import PayloadMissing
from src.models import Media, Payload
from src.models.payload import Payload as PayloadContent

MAGIC = b"P1"
HEADER = struct.Struct(">2sHH")


class EnvelopePayloadService:
    def create(self, media: Media, digest: bytes) -> bytes:
        content = PayloadContent(metadata={
            "kind": media.kind.value,
            "format": media.suffix,
            "digest": digest.hex(),
        })
        return content.get_serializable_data()

    def pack(self, signed_data: bytes, signature: bytes) -> bytes:
        return HEADER.pack(MAGIC, len(signed_data), len(signature)) + signed_data + signature

    def unpack(self, encoded: bytes) -> Payload:
        # A malformed envelope means no usable payload, so it reads as
        # PayloadMissing; edits inside a well-formed one fail the signature.
        if len(encoded) < HEADER.size:
            raise PayloadMissing("Embedded payload is too short.")
        magic, data_len, sig_len = HEADER.unpack_from(encoded)
        if magic != MAGIC or len(encoded) != HEADER.size + data_len + sig_len:
            raise PayloadMissing("Embedded payload is not in the expected format.")
        signed_data = encoded[HEADER.size:HEADER.size + data_len]
        signature = encoded[HEADER.size + data_len:]
        try:
            digest = bytes.fromhex(json.loads(signed_data)["metadata"]["digest"])
        except (ValueError, KeyError, TypeError) as exc:
            raise PayloadMissing("Embedded payload content is unreadable.") from exc
        return Payload(signed_data=signed_data, digest=digest, signature=signature)
