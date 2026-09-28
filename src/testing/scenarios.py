"""Real attack scenarios: protect a cover, attack the stego copy, verify it.

Each scenario runs the group's real services end to end and states the
verdict the system is expected to give today. Two start-location modes are
covered because they behave differently: with a manual position the payload
stays where it is after a content edit, so the engine reaches Tampered; with a
passphrase the position is derived from the content, so the same edit moves
the payload and the engine reports Payload Missing. The notes record that
this is the known degradation described in docs/verification_integration.md
sections 4 and 7, so the evidence stays honest when Member 4 changes it.
"""
import shutil
from datetime import datetime
from pathlib import Path

from src.attacks import ATTACKS, AttackContext, apply_attack
from src.controllers import ApplicationController
from src.models import Media, MediaType, Verdict, VerificationResult
from src.services.audio_steganography import WavSteganographyService
from src.services.crypto_adapter import SignatureCrypto
from src.services.image_steganography import ImageSteganography
from src.services.payload_service import EnvelopePayloadService
from src.services.start_location import KeyedStartLocation
from src.testing.runner import Scenario

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
DEFAULT_COVERS = (SAMPLES / "lambda-icon.png", SAMPLES / "audio" / "original.wav")
PASSPHRASE = "group2 attack suite"
MESSAGE = "INF2005 P5 Group 2 attack suite: hidden message"
MANUAL_START = 100
DEGRADED = "Passphrase mode derives the start from the content, so an edit moves the payload (docs section 7)."
NO_SELF_CHECK = "Start recovery has no self-check, so a wrong location reads as Payload Missing (docs section 4)."

# Expected verdict per attack: (manual mode, passphrase mode).
EXPECTED = {
    "reencode_lossless": (Verdict.AUTHENTIC, Verdict.AUTHENTIC),
    "convert_container": (Verdict.AUTHENTIC, Verdict.AUTHENTIC),  # RGBA PNG covers: see _conversion_case
    "pixel_edit": (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING),
    "region_edit": (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING),
    "crop_bottom": (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING),
    "sample_edit": (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING),
    "silence_tail": (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING),
    "truncate": (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING),
    "lsb_noise": (Verdict.PAYLOAD_MISSING, Verdict.PAYLOAD_MISSING),
    "lsb_strip": (Verdict.PAYLOAD_MISSING, Verdict.PAYLOAD_MISSING),
    "resize": (Verdict.PAYLOAD_MISSING, Verdict.PAYLOAD_MISSING),
    "jpeg_roundtrip": (Verdict.PAYLOAD_MISSING, Verdict.PAYLOAD_MISSING),
    "gain": (Verdict.PAYLOAD_MISSING, Verdict.PAYLOAD_MISSING),
    "edit_payload": (Verdict.SIGNATURE_INVALID, Verdict.SIGNATURE_INVALID),
    "forge_message": (Verdict.SIGNATURE_INVALID, Verdict.SIGNATURE_INVALID),
    "corrupt_signature": (Verdict.SIGNATURE_INVALID, Verdict.SIGNATURE_INVALID),
    "wipe_payload": (Verdict.PAYLOAD_MISSING, Verdict.PAYLOAD_MISSING),
}


class Bench:
    """Builds controllers that share one work folder and one signing key pair."""

    def __init__(self, work_dir: Path, message: str = MESSAGE):
        self.work_dir = Path(work_dir)
        self.message = message
        self.keys = self.work_dir / "keys"
        self.other_keys = self.work_dir / "keys-other"
        # Saving never overwrites, so each run gets its own files folder.
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.files, counter = self.work_dir / f"files-{stamp}", 1
        while self.files.exists():
            counter += 1
            self.files = self.work_dir / f"files-{stamp}-{counter}"
        self.files.mkdir(parents=True)
        self.counter = 0

    def controller(self, mode: str, key_dir: Path | None = None,
                   passphrase: str = PASSPHRASE, start: int = MANUAL_START) -> ApplicationController:
        location = KeyedStartLocation()
        if mode == "manual":
            location.manual_start = start
        else:
            location.key = passphrase
        return ApplicationController(
            image=ImageSteganography(), audio=WavSteganographyService(),
            crypto=SignatureCrypto(key_dir or self.keys), payload=EnvelopePayloadService(),
            location=location)

    def path(self, label: str, suffix: str) -> Path:
        self.counter += 1
        return self.files / f"{self.counter:03d}-{label}{suffix}"

    def protect(self, controller: ApplicationController, cover: Path, lsb: int, label: str) -> Path:
        stego = self.path(label, cover.suffix)
        controller.save(controller.protect(str(cover), lsb, self.message), str(stego))
        return stego

    @staticmethod
    def service_for(controller: ApplicationController, media: Media):
        return controller.service_for(media)


def _load(path: Path) -> Media:
    return ApplicationController.load(str(path))


def _kind(cover: Path) -> str:
    return "audio" if cover.suffix.lower() == ".wav" else "image"


ALPHA_LOST = "BMP has no alpha channel, so converting this RGBA PNG discards signed content."


def _expected_for(attack_id: str, cover: Path) -> tuple[tuple[Verdict, Verdict], str]:
    """Expected (manual, passphrase) verdicts for an attack on this cover."""
    if attack_id == "convert_container" and cover.suffix.lower() == ".png":
        from PIL import Image
        with Image.open(cover) as image:
            has_alpha = image.mode in {"RGBA", "LA", "PA"} or (image.mode == "P" and "transparency" in image.info)
        if has_alpha:
            return (Verdict.TAMPERED, Verdict.PAYLOAD_MISSING), ALPHA_LOST
    return EXPECTED[attack_id], ""


def _prefix(cover: Path, lsb: int, mode: str) -> str:
    """Scenario name prefix; the cover name keeps runs with several covers apart."""
    return f"{cover.stem}/{_kind(cover)}/{mode}/lsb{lsb}"


def attack_scenarios(bench: Bench, cover: Path, lsb: int, mode: str) -> list[Scenario]:
    kind = _kind(cover)
    media_kind = MediaType.AUDIO if kind == "audio" else MediaType.IMAGE
    cases = []

    def run_attack(attack_id):
        def execute() -> VerificationResult:
            controller = bench.controller(mode)
            stego = bench.protect(controller, cover, lsb, f"{kind}-{mode}-lsb{lsb}-{attack_id}")
            media = _load(stego)
            if attack_id == "clean":
                attacked = media
            else:
                context = AttackContext(lsb=lsb, start=controller.location.recover(media, lsb),
                                        service=controller.service_for(media), seed=lsb)
                attacked = apply_attack(attack_id, media, context)
            attacked_path = bench.path(f"{kind}-{mode}-lsb{lsb}-{attack_id}-attacked", attacked.suffix)
            attacked_path.write_bytes(attacked.data)
            return controller.verify(str(attacked_path), lsb)
        return execute

    # The clean case must also give back the hidden message it was protected with.
    cases.append(Scenario(f"{_prefix(cover, lsb, mode)}/clean", Verdict.AUTHENTIC, run_attack("clean"),
                          kind, lsb, mode=mode, attack="none", expected_payload=bench.message))
    for attack in ATTACKS.values():
        if media_kind not in attack.kinds:
            continue
        (manual_expected, auto_expected), note = _expected_for(attack.id, cover)
        expected = manual_expected if mode == "manual" else auto_expected
        if mode == "auto" and manual_expected != auto_expected:
            note = f"{note} {DEGRADED}".strip()
        cases.append(Scenario(f"{_prefix(cover, lsb, mode)}/{attack.id}", expected, run_attack(attack.id),
                              kind, lsb, mode=mode, attack=attack.id, note=note))
    return cases


def verifier_scenarios(bench: Bench, cover: Path, lsb: int, clean: bool = True) -> list[Scenario]:
    """Cases where the file is intact but the verifier is misconfigured.

    ``clean`` says the cover is known to carry no payload; only then is the
    unprotected-cover case meaningful (a user-chosen file may be a stego file).
    """
    kind = _kind(cover)
    cases = []

    def stego_for(mode):
        return bench.protect(bench.controller(mode), cover, lsb, f"{kind}-{mode}-lsb{lsb}-verifier")

    def unprotected():
        return bench.controller("manual").verify(str(cover), lsb)

    def wrong_public_key():
        stego = stego_for("manual")
        other = bench.controller("manual", key_dir=bench.other_keys)
        other.crypto.sign(b"create the other key pair")
        return other.verify(str(stego), lsb)

    def wrong_passphrase():
        stego = stego_for("auto")
        return bench.controller("auto", passphrase="not the passphrase").verify(str(stego), lsb)

    def wrong_start():
        stego = stego_for("manual")
        return bench.controller("manual", start=MANUAL_START + 7).verify(str(stego), lsb)

    def wrong_lsb():
        stego = stego_for("manual")
        return bench.controller("manual").verify(str(stego), lsb % 8 + 1)

    def missing_public_key():
        stego = stego_for("manual")
        return bench.controller("manual", key_dir=bench.work_dir / "keys-empty").verify(str(stego), lsb)

    def unsupported_format():
        target = bench.path(f"{kind}-unsupported", ".jpg")
        shutil.copy(cover, target)
        return bench.controller("manual").verify(str(target), lsb)

    def wrong_lsb_note():
        return "Reading at another depth finds no envelope, so the verdict is Payload Missing."

    for name, expected, execute, mode, note in (
            ("unprotected_cover", Verdict.PAYLOAD_MISSING, unprotected, "manual", ""),
            ("wrong_public_key", Verdict.SIGNATURE_INVALID, wrong_public_key, "manual", ""),
            ("wrong_passphrase", Verdict.PAYLOAD_MISSING, wrong_passphrase, "auto", NO_SELF_CHECK),
            ("wrong_start_position", Verdict.PAYLOAD_MISSING, wrong_start, "manual", NO_SELF_CHECK),
            ("wrong_lsb_depth", Verdict.PAYLOAD_MISSING, wrong_lsb, "manual", wrong_lsb_note()),
            ("missing_public_key", Verdict.CANNOT_VERIFY, missing_public_key, "manual", ""),
            ("unsupported_format", Verdict.CANNOT_VERIFY, unsupported_format, "manual", "")):
        if name == "unprotected_cover" and not clean:
            continue
        cases.append(Scenario(f"{_prefix(cover, lsb, mode)}/verifier/{name}", expected, execute,
                              kind, lsb, mode=mode, attack=name, note=note))
    return cases


def build_real_scenarios(work_dir, covers=DEFAULT_COVERS, lsbs=(1,), modes=("manual", "auto"),
                         clean_covers=None, message=MESSAGE) -> list[Scenario]:
    """The full suite: every attack and verifier case for each cover, depth and mode.

    ``clean_covers`` lists the covers known to be unprotected originals; it
    defaults to all of ``covers``.
    """
    bench = Bench(Path(work_dir) / "attack-suite-work", message=message)
    clean = {Path(c).resolve() for c in (covers if clean_covers is None else clean_covers)}
    cases = []
    for cover in covers:
        cover = Path(cover)
        for lsb in lsbs:
            for mode in modes:
                cases.extend(attack_scenarios(bench, cover, lsb, mode))
            cases.extend(verifier_scenarios(bench, cover, lsb, clean=cover.resolve() in clean))
    return cases
