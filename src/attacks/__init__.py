"""Attack simulation for protected media (Member 6).

Every attack takes a :class:`~src.models.Media` and returns a modified copy in
the same container format. Media-level attacks (edits, noise, crops, format
round trips) need nothing else. Payload-level attacks rewrite the embedded
envelope in place, so they need the LSB depth, the start unit and the
steganography service that framed it; see :class:`AttackContext`.

The registry is what the GUI attack lab, the automated scenario suite and the
unit tests share, so an attack added here appears everywhere.
"""
from dataclasses import dataclass
from typing import Callable

from src.exceptions import IntegrationError
from src.models import Media, MediaType


@dataclass(frozen=True)
class AttackContext:
    """What a payload-level attack needs to find the envelope it corrupts."""

    lsb: int = 1
    start: int | None = None
    service: object = None
    seed: int = 0


@dataclass(frozen=True)
class Attack:
    id: str
    label: str
    description: str
    kinds: frozenset
    targets_payload: bool
    run: Callable[[Media, AttackContext], Media]

    def applies_to(self, kind: MediaType | None) -> bool:
        return kind is not None and kind in self.kinds

    def __call__(self, media: Media, context: AttackContext | None = None) -> Media:
        return apply_attack(self.id, media, context)


ATTACKS: dict[str, Attack] = {}

IMAGE = frozenset({MediaType.IMAGE})
AUDIO = frozenset({MediaType.AUDIO})
BOTH = IMAGE | AUDIO


def register(attack_id: str, label: str, description: str, kinds: frozenset,
             targets_payload: bool = False):
    def wrap(function):
        existing = ATTACKS.get(attack_id)
        if existing is None:
            ATTACKS[attack_id] = Attack(attack_id, label, description, kinds, targets_payload, function)
            return function
        # The same attack name for another media type: dispatch on the kind.
        if existing.kinds & kinds or existing.targets_payload != targets_payload:
            raise ValueError(f"Attack '{attack_id}' is registered twice for the same media type.")
        previous = existing.run

        def dispatch(media, context, _new_kinds=kinds):
            return function(media, context) if media.kind in _new_kinds else previous(media, context)
        ATTACKS[attack_id] = Attack(attack_id, existing.label, existing.description,
                                    existing.kinds | kinds, targets_payload, dispatch)
        return function
    return wrap


def attacks_for(kind: MediaType | None) -> list[Attack]:
    """Attacks applicable to one media type, in registration order."""
    return [attack for attack in ATTACKS.values() if attack.applies_to(kind)]


def apply_attack(attack_id: str, media: Media, context: AttackContext | None = None) -> Media:
    attack = ATTACKS.get(attack_id)
    if attack is None:
        raise IntegrationError(f"Unknown attack '{attack_id}'.")
    if not attack.applies_to(media.kind):
        raise IntegrationError(f"Attack '{attack.label}' does not apply to {media.kind.value} files.")
    context = context or AttackContext()
    if attack.targets_payload and (context.service is None or context.start is None):
        raise IntegrationError(
            f"Attack '{attack.label}' rewrites the embedded payload, so it needs the "
            "LSB depth, the start location and the steganography service.")
    attacked = attack.run(media, context)
    if not isinstance(attacked, Media):
        raise IntegrationError(f"Attack '{attack.label}' did not produce media.")
    return attacked


def describe(kind: MediaType | None = None) -> list[dict]:
    """JSON-friendly listing for front ends."""
    return [{"id": attack.id, "label": attack.label, "description": attack.description,
             "kinds": sorted(k.value for k in attack.kinds), "targets_payload": attack.targets_payload}
            for attack in (attacks_for(kind) if kind else ATTACKS.values())]


# Registering the implementations populates ATTACKS.
from src.attacks import audio as _audio  # noqa: E402,F401
from src.attacks import image as _image  # noqa: E402,F401
from src.attacks import payload as _payload  # noqa: E402,F401

__all__ = ["Attack", "AttackContext", "ATTACKS", "apply_attack", "attacks_for", "describe", "register"]
