"""Decides where a payload begins inside an image or audio cover.

Two modes:

*Keyed* derives the position from a passphrase and the cover itself:

    key + canonical cover  --HMAC-SHA256-->  nonce (4 bytes)
    key + nonce + bounds   --HMAC-SHA256-->  start unit index

The nonce comes from the cover rather than a random source, so nothing has to
be stored in the file for the reader to recover it.  That works because
canonicalisation masks off the low ``lsb`` bits of every sample -- exactly the
bits embedding overwrites -- so a cover and its stego output canonicalise to
identical bytes and therefore produce an identical position.  Determinism is
the requirement, not a weakness: a position that changed per run could not be
found again at extraction time.

*Manual* uses a caller-supplied position verbatim.  No passphrase is involved,
and equally none protects it.

Positions are flat unit indices, where a unit is one colour sample or one
audio sample.  The functions below never touch a pixel, a sample, a hash or a
signature; only ``KeyedStartLocation`` knows about concrete media services.
Unit 0 is never produced, so a payload never begins at the very first unit.

Limitations
-----------
* The same cover under the same passphrase always yields the same position.
* At ``lsb == 8`` the mask clears every sample, so no cover content survives
  canonicalisation and the position depends only on the passphrase and the
  cover's format and dimensions.  This is inherent: at 8 bits there is no
  cover content left to bind to.
* Secrecy of the position rests entirely on secrecy of the passphrase.
* The derivation reads decoded samples, so it does not survive re-encoding,
  resampling or format conversion.
"""
from __future__ import annotations

import hashlib
import hmac

from src.exceptions import IntegrationError
from src.models import Media, MediaType

NONCE_BYTES = 4

# Domain separators keep the two HMAC stages from ever producing the same
# digest for the same inputs.
_NONCE_INFO = b"acw1-start-nonce-v1"
_START_INFO = b"acw1-start-offset-v1"


# ----------------------------------------------------------------- capacity

def _check_positive(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise IntegrationError(f"{label} must be a positive integer.")
    return value


def _check_lsb(num_lsb: int) -> int:
    if type(num_lsb) is not int or not 1 <= num_lsb <= 8:
        raise IntegrationError("LSB must be an integer from 1 to 8.")
    return num_lsb


def image_capacity(width: int, height: int, channels: int, num_lsb: int) -> int:
    """Embeddable BITS in an image cover.

    This is a bit count.  A start index is a *unit* index, which is this value
    divided by ``num_lsb``.
    """
    _check_positive(width, "Width")
    _check_positive(height, "Height")
    _check_positive(channels, "Channel count")
    _check_lsb(num_lsb)
    return width * height * channels * num_lsb


def audio_capacity(num_samples: int, num_lsb: int) -> int:
    """Embeddable BITS in a PCM audio cover."""
    _check_positive(num_samples, "Sample count")
    _check_lsb(num_lsb)
    return num_samples * num_lsb


# -------------------------------------------------------------------- nonce

def derive_nonce(key: bytes, canonical: bytes, lsb: int) -> bytes:
    """Derive a cover's nonce from its canonical (bit-masked) form.

    ``lsb`` is mixed in because a different depth masks different bits and
    would otherwise silently reuse another depth's nonce.
    """
    if not isinstance(key, (bytes, bytearray)) or not key:
        raise IntegrationError("Start-location key must be non-empty bytes.")
    if not isinstance(canonical, (bytes, bytearray)):
        raise IntegrationError("Canonical media must be bytes.")
    _check_lsb(lsb)
    message = b"%s|%d|%s" % (_NONCE_INFO, lsb, bytes(canonical))
    return hmac.new(bytes(key), message, hashlib.sha256).digest()[:NONCE_BYTES]


# -------------------------------------------------------------------- start

def derive_start(unit_count: int, key: bytes, nonce: bytes,
                 payload_units: int) -> int:
    """Return the unit index a payload of ``payload_units`` starts at.

    The result is uniform over ``1 .. unit_count - payload_units``.  Index 0
    is excluded so the payload never begins at the very first unit.

    Raises ``IntegrationError`` when the payload cannot fit while still
    leaving a non-zero start available.
    """
    _check_positive(unit_count, "Unit count")
    if not isinstance(key, (bytes, bytearray)) or not key:
        raise IntegrationError("Start-location key must be non-empty bytes.")
    if not isinstance(nonce, (bytes, bytearray)) or len(nonce) != NONCE_BYTES:
        raise IntegrationError(f"Nonce must be {NONCE_BYTES} bytes.")
    if type(payload_units) is not int or payload_units <= 0:
        raise IntegrationError("Payload unit count must be a positive integer.")

    # Starts run 1..span inclusive; span == 0 means the payload fills the
    # cover and no non-zero start is available.
    span = unit_count - payload_units
    if span < 1:
        raise IntegrationError(
            "Payload exceeds the available media capacity; no start location "
            "leaves room for it."
        )

    message = b"%s|%d|%d|%s" % (_START_INFO, unit_count, payload_units,
                                bytes(nonce))
    digest = hmac.new(bytes(key), message, hashlib.sha256).digest()
    # 256 bits reduced into a span of ~2**20 leaves modulo bias below 2**-230.
    return int(int.from_bytes(digest, "big") % span) + 1


# ------------------------------------------------------------------ adapter

class KeyedStartLocation:
    """Supplies a start position for a given cover and LSB depth.

    ``generate`` and ``recover`` run the same derivation -- there is no stored
    state, which is what makes recovery possible.
    """

    def __init__(self, key: bytes | str = b""):
        self._key = b""
        self._manual_start = None
        if key:
            self.key = key

    @property
    def manual_start(self) -> int | None:
        """A hand-picked start unit, or ``None`` to derive one from the key."""
        return self._manual_start

    @manual_start.setter
    def manual_start(self, value: int | None) -> None:
        """Pin the start position, bypassing the keyed derivation.

        No passphrase is required while a position is pinned, and equally none
        protects it.  Set to ``None`` to return to keyed derivation.
        """
        if value is None:
            self._manual_start = None
            return
        if type(value) is not int:
            raise IntegrationError("Start position must be a whole number.")
        if value < 1:
            raise IntegrationError(
                "Start position must be 1 or greater; position 0 is the very "
                "first unit of the cover."
            )
        self._manual_start = value

    @property
    def key(self) -> bytes:
        """The passphrase the keyed derivation uses, as bytes."""
        return self._key

    @key.setter
    def key(self, value: bytes | str) -> None:
        """Set the passphrase used by subsequent operations.

        One instance is built at startup and assigned a passphrase before each
        operation, because whoever verifies a file may supply a different one
        than whoever protected it.  Accepts ``str`` and encodes it as UTF-8.
        """
        if isinstance(value, str):
            value = value.encode("utf-8")
        elif isinstance(value, (bytes, bytearray)):
            value = bytes(value)
        else:
            raise IntegrationError(
                "Start-location passphrase must be text or bytes."
            )
        if not value:
            raise IntegrationError("Start-location passphrase must not be empty.")
        self._key = value

    def generate(self, media: Media, lsb: int) -> int:
        return self._derive(media, lsb)

    def recover(self, media: Media, lsb: int) -> int:
        return self._derive(media, lsb)

    def __repr__(self) -> str:
        # Never disclose the passphrase; this object reaches logs and tracebacks.
        mode = "manual" if self._manual_start is not None else "keyed"
        state = "set" if self._key else "unset"
        return f"<{type(self).__name__} mode={mode} passphrase={state}>"

    # -------------------------------------------------------------- internal

    @staticmethod
    def _reserve_units(unit_count: int) -> int:
        """Units held back so the payload is guaranteed to fit.

        ``generate()`` is called before the payload exists, so the position
        must be chosen without knowing its length.  Reserving half the cover
        guarantees room for any payload that will subsequently be accepted,
        and costs one bit of search space.  Being a pure function of
        ``unit_count``, ``recover()`` recomputes the identical reserve.
        """
        return max(1, unit_count // 2)

    def _derive(self, media: Media, lsb: int) -> int:
        _check_lsb(lsb)
        if self._manual_start is not None:
            unit_count, _ = self._describe(media, lsb)
            if self._manual_start >= unit_count:
                raise IntegrationError(
                    f"Start position {self._manual_start:,} is outside this "
                    f"cover, which holds {unit_count:,} units."
                )
            return self._manual_start
        if not self._key:
            raise IntegrationError(
                "No start-location passphrase set; enter one before "
                "protecting or verifying."
            )
        unit_count, canonical = self._describe(media, lsb)
        nonce = derive_nonce(self._key, canonical, lsb)
        return derive_start(unit_count, self._key, nonce,
                            self._reserve_units(unit_count))

    @staticmethod
    def _describe(media: Media, lsb: int) -> tuple[int, bytes]:
        """Return (embeddable unit count, canonical bytes) for the cover."""
        if media.kind == MediaType.IMAGE:
            from src.services.image_steganography import ImageSteganography
            return (ImageSteganography.unit_count(media),
                    ImageSteganography.canonical_bytes(media, lsb))
        if media.kind == MediaType.AUDIO:
            from src.services.audio_steganography import WavSteganographyService
            service = WavSteganographyService()
            return (service.sample_count(media),
                    service.canonical_bytes(media, lsb))
        raise IntegrationError("Unsupported media type for start location.")
