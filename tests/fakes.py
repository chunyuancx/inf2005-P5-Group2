"""Fakes for src.interfaces, matching the group's real signatures exactly."""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import struct

from src.exceptions import PayloadMissing, WrongStartLocation
from src.models import Media, Payload

MAGIC = b"E1"


class FakeSteganography:
    """One byte of media.data = one unit. Frames payload with magic+length so
    extract() can self-delimit, since the real interface gives it no n_bytes.
    """

    HEADER = struct.Struct(">2sI")  # magic, payload length

    def capacity(self, media: Media, lsb: int, start: int) -> int:
        total_units = len(media.data)
        remaining_units = max(0, total_units - start)
        remaining_bits = remaining_units * lsb
        header_bits = self.HEADER.size * 8
        return max(0, (remaining_bits - header_bits) // 8)

    def _write_bits(self, data: bytearray, bits: list[int], lsb: int, start: int) -> None:
        mask = (0xFF << lsb) & 0xFF
        for k in range(0, len(bits), lsb):
            chunk = bits[k : k + lsb]
            value = 0
            for b in chunk:
                value = (value << 1) | b
            idx = start + k // lsb
            data[idx] = (data[idx] & mask) | value

    def _read_bits(self, data: bytes, lsb: int, start: int, n_units: int) -> list[int]:
        low = (1 << lsb) - 1
        bits: list[int] = []
        for k in range(n_units):
            v = data[start + k] & low
            bits.extend((v >> (lsb - 1 - i)) & 1 for i in range(lsb))
        return bits

    def embed(self, media: Media, payload: bytes, lsb: int, start: int) -> bytes:
        framed = self.HEADER.pack(MAGIC, len(payload)) + payload
        out = bytearray(media.data)
        bits = [(byte >> (7 - i)) & 1 for byte in framed for i in range(8)]
        needed_units = -(-len(bits) // lsb)
        if start + needed_units > len(out):
            raise ValueError("Embedding run exceeds cover object.")
        bits += [0] * (needed_units * lsb - len(bits))
        self._write_bits(out, bits, lsb, start)
        return bytes(out)

    def extract(self, media: Media, lsb: int, start: int) -> bytes:
        header_bits = self.HEADER.size * 8
        header_units = -(-header_bits // lsb)
        if start < 0 or start + header_units > len(media.data):
            raise PayloadMissing("Start location is outside the cover object.")

        bits = self._read_bits(media.data, lsb, start, header_units)
        header_bytes = bytearray()
        for i in range(self.HEADER.size):
            byte = 0
            for b in bits[i * 8 : (i + 1) * 8]:
                byte = (byte << 1) | b
            header_bytes.append(byte)

        try:
            magic, length = self.HEADER.unpack(bytes(header_bytes))
        except struct.error as exc:
            raise PayloadMissing("Could not read a header at this location.") from exc
        if magic != MAGIC or length <= 0 or length > 8 * 1024 * 1024:
            raise PayloadMissing("No valid envelope at this location.")

        total_units = header_units + (-(-(length * 8) // lsb))
        if start + total_units > len(media.data):
            raise PayloadMissing("Envelope declares more data than the file holds.")

        all_bits = self._read_bits(media.data, lsb, start, total_units)
        payload_bits = all_bits[header_bits:]
        out = bytearray()
        for i in range(length):
            byte = 0
            for b in payload_bits[i * 8 : (i + 1) * 8]:
                byte = (byte << 1) | b
            out.append(byte)
        return bytes(out)


class FakeCrypto:
    def __init__(self, sign_key: str = "team-key", verify_key: str = "team-key") -> None:
        self.sign_key = sign_key
        self.verify_key = verify_key

    def hash_media(self, media: Media, lsb: int) -> bytes:
        mask = (0xFF << lsb) & 0xFF
        stable = bytes(b & mask for b in media.data)
        return hashlib.sha256(stable).digest()

    def sign(self, data: bytes) -> bytes:
        return hmac_mod.new(self.sign_key.encode(), data, hashlib.sha256).digest()

    def verify_signature(self, data: bytes, signature: bytes) -> bool:
        expected = hmac_mod.new(self.verify_key.encode(), data, hashlib.sha256).digest()
        return hmac_mod.compare_digest(expected, signature)


class FakePayloadService:
    """signed_data carries the digest INSIDE it, per the real Payload.unpack
    contract note: 'derive digest from signed_data, never unsigned fields.'
    """

    def __init__(self) -> None:
        self._counter = 0

    def create(self, media: Media, digest: bytes) -> bytes:
        self._counter += 1
        doc = {
            "media_id": f"{media.kind.value}-{len(media.data)}",
            "kind": media.kind.value,
            "digest": digest.hex(),
            "timestamp": "2026-09-09T00:00:00Z",
            "nonce": f"{self._counter:016x}",
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()

    def pack(self, signed_data: bytes, signature: bytes) -> bytes:
        return struct.pack(">II", len(signed_data), len(signature)) + signed_data + signature

    def unpack(self, encoded: bytes) -> Payload:
        if len(encoded) < 8:
            raise ValueError("Envelope too short to contain a header.")
        n1, n2 = struct.unpack(">II", encoded[:8])
        signed_data = encoded[8 : 8 + n1]
        signature = encoded[8 + n1 : 8 + n1 + n2]
        if len(signed_data) != n1 or len(signature) != n2:
            raise ValueError("Envelope lengths do not match declared sizes.")
        doc = json.loads(signed_data.decode())
        digest = bytes.fromhex(doc["digest"])
        return Payload(signed_data=signed_data, digest=digest, signature=signature)


class NaiveStartLocation:
    """The tempting-but-wrong Member 4 implementation: recover() just
    re-derives the same deterministic offset as generate(), with no
    self-check. It can NEVER raise WrongStartLocation, because it has no way
    to tell a right key from a wrong one on its own.
    """

    def __init__(self, key: str = "team-key", fraction: float = 0.5) -> None:
        self.key = key
        self.fraction = fraction

    def _derive(self, media: Media) -> int:
        window = max(1, int(len(media.data) * self.fraction))
        seed = hashlib.sha256(f"{self.key}|{media.kind.value}|{len(media.data)}".encode()).digest()
        return int.from_bytes(seed[:8], "big") % window

    def generate(self, media: Media, lsb: int) -> int:
        return self._derive(media)

    def recover(self, media: Media, lsb: int) -> int:
        return self._derive(media)


class SelfCheckingStartLocation:
    """A design that CAN raise WrongStartLocation without touching the main
    payload (avoids the circularity the interface warns about): a 4-byte
    keyed marker is embedded at a FIXED, key-independent unit (unit 0) at
    protect time, separate from the variable-position main envelope.
    recover() reads that fixed marker and compares it to what this key would
    produce; only then does it return the derived offset.
    """

    def __init__(self, key: str = "team-key", fraction: float = 0.5) -> None:
        self.key = key
        self.fraction = fraction

    def _derive(self, media: Media) -> int:
        window = max(1, int(len(media.data) * self.fraction))
        seed = hashlib.sha256(f"{self.key}|{media.kind.value}|{len(media.data)}".encode()).digest()
        return int.from_bytes(seed[:8], "big") % window

    def _marker(self, media: Media) -> bytes:
        return hmac_mod.new(self.key.encode(), f"marker|{len(media.data)}".encode(), hashlib.sha256).digest()[:4]

    def generate(self, media: Media, lsb: int) -> int:
        # In a real implementation this would also embed self._marker(media)
        # at unit 0 via the steganography service. Omitted here since this
        # fake only needs to demonstrate the *recover* contract to the engine.
        return self._derive(media)

    def recover(self, media: Media, lsb: int) -> int:
        # Simulates reading the marker back and checking it against this key.
        # stored_marker would come from the stego service in a real system;
        # here we simulate a wrong-key scenario by comparing against what
        # THIS key expects, vs a marker computed with the media's "true" key
        # stashed as an attribute for the test to control.
        expected = self._marker(media)
        stored = getattr(media, "_test_stored_marker", expected)
        if not hmac_mod.compare_digest(expected, stored):
            raise WrongStartLocation(
                "Recovered marker does not match this key; wrong password, "
                "wrong LSB depth, or wrong start-location parameters."
            )
        return self._derive(media)
