from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class MediaType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"


class Verdict(str, Enum):
    AUTHENTIC = "Authentic"
    TAMPERED = "Tampered"
    SIGNATURE_INVALID = "Signature Invalid"
    PAYLOAD_MISSING = "Payload Missing"
    WRONG_START_LOCATION = "Wrong Start Location"
    CANNOT_VERIFY = "Cannot Verify"


@dataclass(frozen=True)
class Media:
    data: bytes
    suffix: str
    kind: MediaType


@dataclass(frozen=True)
class Payload:
    """Parsed envelope; signature must bind signed_data, including digest."""

    signed_data: bytes
    digest: bytes
    signature: bytes


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    message: str
    statuses: Mapping[str, str] = field(default_factory=dict)
