"""Manual end-to-end test for the keyed start-location module.

Runs a real file all the way through: derive start -> embed -> save to disk ->
reload from disk -> re-derive start -> extract -> compare.  Then repeats with a
wrong passphrase, and with a tampered stego file.

    python manual_start_location_test.py
    python manual_start_location_test.py samples/audio/original.wav
    python manual_start_location_test.py C:/path/to/photo.png --lsb 3
    python manual_start_location_test.py photo.png --key "my passphrase"

Defaults to the sample WAV under samples/.  Pass any PNG, BMP or PCM WAV.
Writes <name>_stego and <name>_tampered next to the file it was given.
"""
import argparse
import sys
from pathlib import Path

from src.exceptions import IntegrationError, PayloadMissing
from src.models import Media, MediaType
from src.services.audio_steganography import WavSteganographyService
from src.services.image_steganography import ImageSteganography
from src.services.start_location import KeyedStartLocation, derive_nonce

DEFAULT_COVER = Path("samples/audio/original.wav")
DEFAULT_KEY = b"group2-acw1-secret"
DEFAULT_PAYLOAD = (
    b"INF2005 ACW1 P5 Group 2 :: verification payload :: "
    b"media-id=demo-001 :: this stands in for the signed payload."
)

IMAGE_SUFFIXES = {".png", ".bmp"}
AUDIO_SUFFIXES = {".wav"}

PASS, FAIL, INFO = "  [PASS]", "  [FAIL]", "       "
_failures = 0


def check(condition: bool, message: str) -> bool:
    global _failures
    print(f"{PASS if condition else FAIL} {message}")
    if not condition:
        _failures += 1
    return condition


def load(path: Path) -> Media:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        kind = MediaType.IMAGE
    elif suffix in AUDIO_SUFFIXES:
        kind = MediaType.AUDIO
    else:
        sys.exit(f"Unsupported file type '{suffix}'. Use .png, .bmp or .wav.")
    if not path.is_file():
        sys.exit(f"No such file: {path}")
    return Media(path.read_bytes(), suffix, kind)


def describe(media: Media, lsb: int):
    """Return (service, unit_count, canonical_bytes) for either media type."""
    if media.kind == MediaType.IMAGE:
        service = ImageSteganography()
        return (service,
                ImageSteganography.unit_count(media),
                ImageSteganography.canonical_bytes(media, lsb))
    service = WavSteganographyService()
    return service, service.sample_count(media), service.canonical_bytes(media, lsb)


def section(title: str):
    print(f"\n{'-' * 70}\n{title}\n{'-' * 70}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cover", nargs="?", default=str(DEFAULT_COVER),
                        help="real .png, .bmp or .wav cover file")
    parser.add_argument("--lsb", type=int, default=2, help="LSB depth 1-8")
    parser.add_argument("--key", default=DEFAULT_KEY.decode(),
                        help="start-location passphrase")
    parser.add_argument("--payload", default=None, help="payload text")
    args = parser.parse_args()

    cover_path = Path(args.cover)
    key = args.key.encode()
    payload = (args.payload.encode() if args.payload else DEFAULT_PAYLOAD)
    lsb = args.lsb

    print("=" * 70)
    print("Keyed start-location end-to-end test")
    print("=" * 70)

    # ---------------------------------------------------------- 1. the cover
    section("1. COVER")
    cover = load(cover_path)
    service, units, canonical = describe(cover, lsb)
    print(f"{INFO} file          : {cover_path}")
    print(f"{INFO} type          : {cover.kind.value}  ({cover.suffix})")
    print(f"{INFO} size on disk  : {len(cover.data):,} bytes")
    print(f"{INFO} embeddable    : {units:,} units")
    print(f"{INFO} lsb depth     : {lsb}")
    print(f"{INFO} payload       : {len(payload):,} bytes")

    room = service.capacity(cover, lsb, 1)
    check(len(payload) <= room,
          f"payload fits (needs {len(payload):,} B, room {room:,} B from unit 1)")

    # ------------------------------------------------------- 2. derive start
    section("2. DERIVE START LOCATION (from the COVER)")
    locator = KeyedStartLocation(key)
    nonce = derive_nonce(key, canonical, lsb)
    start = locator.generate(cover, lsb)
    print(f"{INFO} passphrase    : {args.key!r}")
    print(f"{INFO} nonce         : {nonce.hex()}   (derived, never stored)")
    print(f"{INFO} start         : {start:,} of {units:,}")
    check(start >= 1, "start is not unit 0, the very first unit of the cover")
    check(start + len(payload) * 8 // lsb <= units, "payload fits from start")

    # ------------------------------------------------------------- 3. embed
    section("3. EMBED AND SAVE TO DISK")
    stego_path = cover_path.with_name(f"{cover_path.stem}_stego{cover_path.suffix}")
    stego_bytes = service.embed(cover, payload, lsb, start)
    stego_path.write_bytes(stego_bytes)
    print(f"{INFO} written       : {stego_path}")
    print(f"{INFO} size on disk  : {len(stego_bytes):,} bytes")

    # --------------------------------------------- 4. reload and re-derive
    section("4. RELOAD FROM DISK AND RE-DERIVE (the verifier's view)")
    reloaded = load(stego_path)
    _, units2, canonical2 = describe(reloaded, lsb)
    nonce2 = derive_nonce(key, canonical2, lsb)
    recovered = locator.recover(reloaded, lsb)
    print(f"{INFO} nonce         : {nonce2.hex()}")
    print(f"{INFO} start         : {recovered:,}")
    check(canonical2 == canonical, "canonical bytes UNCHANGED by embedding")
    check(nonce2 == nonce, "same nonce derived from the stego file")
    check(recovered == start, f"same start recovered ({recovered:,} == {start:,})")

    # ----------------------------------------------------------- 5. extract
    section("5. EXTRACT")
    try:
        out = service.extract(reloaded, lsb, recovered)
        check(out == payload, f"payload recovered intact ({len(out):,} bytes)")
        print(f"{INFO} first 60 B    : {out[:60]!r}")
    except (PayloadMissing, IntegrationError) as exc:
        check(False, f"extraction failed: {exc}")

    # ------------------------------------------------- 6. wrong passphrase
    section("6. NEGATIVE CASE :: WRONG PASSPHRASE")
    wrong_key = b"wrong-passphrase"
    wrong_start = KeyedStartLocation(wrong_key).recover(reloaded, lsb)
    print(f"{INFO} passphrase    : {wrong_key.decode()!r}")
    print(f"{INFO} start         : {wrong_start:,}  (true start {start:,})")
    check(wrong_start != start, "wrong passphrase derives a DIFFERENT location")
    try:
        service.extract(reloaded, lsb, wrong_start)
        check(False, "wrong passphrase LEAKED the payload")
    except (PayloadMissing, IntegrationError) as exc:
        check(True, f"wrong passphrase cannot extract ({type(exc).__name__})")

    # --------------------------------------------------- 7. tampered stego
    section("7. NEGATIVE CASE :: TAMPERED STEGO FILE")
    tampered_path = cover_path.with_name(
        f"{cover_path.stem}_tampered{cover_path.suffix}")
    tampered = tamper(reloaded, lsb, tampered_path)
    if tampered is None:
        print(f"{INFO} skipped (could not build a tampered variant)")
    else:
        _, _, canonical3 = describe(tampered, lsb)
        moved = locator.recover(tampered, lsb)
        print(f"{INFO} written       : {tampered_path}")
        print(f"{INFO} start         : {moved:,}  (true start {start:,})")
        if canonical3 != canonical:
            check(True, "visible tampering CHANGES the canonical bytes")
            print(f"{INFO} NOTE: the derived start moves, so a tampered file")
            print(f"{INFO}       reports Payload Missing rather than Tampered.")
        try:
            service.extract(tampered, lsb, moved)
            print(f"{INFO} tampered file still extracted at its derived start")
        except (PayloadMissing, IntegrationError) as exc:
            check(True, f"tampered file cannot be extracted ({type(exc).__name__})")

    # ------------------------------------------------------------- summary
    print(f"\n{'=' * 70}")
    if _failures:
        print(f"RESULT: {_failures} CHECK(S) FAILED")
    else:
        print("RESULT: ALL CHECKS PASSED")
    print("=" * 70)
    print(f"\nArtifacts written next to the cover:\n  {stego_path}\n  {tampered_path}")
    return 1 if _failures else 0


def tamper(media: Media, lsb: int, path: Path):
    """Produce a visibly-altered copy: flips a HIGH bit the mask preserves."""
    try:
        if media.kind == MediaType.IMAGE:
            import io

            import numpy as np
            from PIL import Image

            image = Image.open(io.BytesIO(media.data))
            pixels = np.array(image)
            # Flip the top bit of a block of samples -> a visible change that
            # survives canonicalisation.
            pixels[:8, :8] ^= 0x80
            buffer = io.BytesIO()
            Image.fromarray(pixels).save(
                buffer, format="PNG" if media.suffix == ".png" else "BMP")
            data = buffer.getvalue()
        else:
            import wave
            from array import array
            import io

            with wave.open(io.BytesIO(media.data), "rb") as handle:
                params = handle.getparams()
                frames = handle.readframes(handle.getnframes())
            samples = array("h")
            samples.frombytes(frames)
            for index in range(min(64, len(samples))):
                samples[index] = max(-32768, min(32767, samples[index] // 2))
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as handle:
                handle.setparams(params)
                handle.writeframes(samples.tobytes())
            data = buffer.getvalue()
        path.write_bytes(data)
        return Media(data, media.suffix, media.kind)
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
