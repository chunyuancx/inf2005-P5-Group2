"""Payload-level attacks: rewrite the embedded envelope where it sits.

These simulate an attacker who knows the LSB depth and start location and
tampers with the hidden data itself rather than the visible media. The
envelope layout comes from ``EnvelopePayloadService``: a six-byte header
(magic ``P1``, signed-data length, signature length), the signed JSON, then
the signature.
"""
import json
import struct

from src.attacks import BOTH, AttackContext, register
from src.exceptions import IntegrationError
from src.models import Media

HEADER = struct.Struct(">2sHH")
MAGIC = b"P1"


def _envelope(media: Media, ctx: AttackContext) -> tuple[bytes, bytes, bytes]:
    encoded = ctx.service.extract(media, ctx.lsb, ctx.start)
    if len(encoded) < HEADER.size:
        raise IntegrationError("No payload envelope was found to attack.")
    magic, data_len, sig_len = HEADER.unpack_from(encoded)
    if magic != MAGIC or len(encoded) != HEADER.size + data_len + sig_len:
        raise IntegrationError("The embedded data is not a payload envelope.")
    signed = encoded[HEADER.size:HEADER.size + data_len]
    return signed, encoded[HEADER.size + data_len:], encoded


def _reembed(media: Media, ctx: AttackContext, signed: bytes, signature: bytes) -> Media:
    envelope = HEADER.pack(MAGIC, len(signed), len(signature)) + signed + signature
    return Media(ctx.service.embed(media, envelope, ctx.lsb, ctx.start), media.suffix, media.kind)


@register("edit_payload", "Edit the payload",
          "Changes the media ID inside the signed payload while leaving the signature as it was.", BOTH,
          targets_payload=True)
def edit_payload(media: Media, ctx: AttackContext) -> Media:
    signed, signature, _ = _envelope(media, ctx)
    try:
        content = json.loads(signed)
        content["media_id"] = "forged-" + str(content.get("media_id", ""))[7:]
    except (ValueError, TypeError) as exc:
        raise IntegrationError("The signed payload is not the expected JSON.") from exc
    return _reembed(media, ctx, json.dumps(content, sort_keys=True).encode("utf-8"), signature)


@register("forge_message", "Forge the hidden message",
          "Rewrites the hidden message text inside the signed payload while leaving the signature as it was.", BOTH,
          targets_payload=True)
def forge_message(media: Media, ctx: AttackContext) -> Media:
    signed, signature, _ = _envelope(media, ctx)
    try:
        content = json.loads(signed)
        metadata = content.setdefault("metadata", {})
        metadata["payload"] = "forged: " + str(metadata.get("payload", ""))
    except (ValueError, TypeError, AttributeError) as exc:
        raise IntegrationError("The signed payload is not the expected JSON.") from exc
    return _reembed(media, ctx, json.dumps(content, sort_keys=True).encode("utf-8"), signature)


@register("corrupt_signature", "Corrupt the signature",
          "Flips one bit in the middle of the embedded signature.", BOTH, targets_payload=True)
def corrupt_signature(media: Media, ctx: AttackContext) -> Media:
    signed, signature, _ = _envelope(media, ctx)
    damaged = bytearray(signature)
    damaged[len(damaged) // 2] ^= 0x01
    return _reembed(media, ctx, signed, bytes(damaged))


@register("wipe_payload", "Wipe the payload",
          "Overwrites the whole embedded envelope with zeros, as if the hidden data were scrubbed.", BOTH,
          targets_payload=True)
def wipe_payload(media: Media, ctx: AttackContext) -> Media:
    _, _, encoded = _envelope(media, ctx)
    return Media(ctx.service.embed(media, bytes(len(encoded)), ctx.lsb, ctx.start), media.suffix, media.kind)
