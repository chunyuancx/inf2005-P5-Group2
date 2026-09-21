from pathlib import Path

from src.models import Media, MediaType
from src.services.audio_steganography import WavSteganographyService


INPUT_FILE = Path("samples/audio/original.wav")
OUTPUT_FILE = Path("samples/audio/stego.wav")

LSB = 8
START_LOCATION = 1000

PAYLOAD = b"INF2005 ACW1 real WAV audio steganography test."


def main():
    print("=== INF2005 Audio Steganography Manual Test ===")

    # -------------------------------------------------
    # 1. Load real WAV
    # -------------------------------------------------

    original_bytes = INPUT_FILE.read_bytes()

    original_media = Media(
        data=original_bytes,
        suffix=".wav",
        kind=MediaType.AUDIO,
    )

    service = WavSteganographyService()

    print()
    print("Input file:", INPUT_FILE)
    print("Input size:", len(original_bytes), "bytes")

    # -------------------------------------------------
    # 2. Check capacity
    # -------------------------------------------------

    capacity = service.capacity(
        original_media,
        lsb=LSB,
        start=START_LOCATION,
    )

    print()
    print("LSB depth:", LSB)
    print("Start location:", START_LOCATION)
    print("Available payload capacity:", capacity, "bytes")
    print("Payload size:", len(PAYLOAD), "bytes")

    if len(PAYLOAD) > capacity:
        print()
        print("FAILED: Payload is too large.")
        return

    # -------------------------------------------------
    # 3. Embed payload
    # -------------------------------------------------

    stego_bytes = service.embed(
        original_media,
        payload=PAYLOAD,
        lsb=LSB,
        start=START_LOCATION,
    )

    OUTPUT_FILE.write_bytes(stego_bytes)

    print()
    print("Stego WAV created:")
    print(OUTPUT_FILE)
    print("Stego file size:", len(stego_bytes), "bytes")

    # -------------------------------------------------
    # 4. Reload the SAVED file
    # -------------------------------------------------

    saved_stego_bytes = OUTPUT_FILE.read_bytes()

    stego_media = Media(
        data=saved_stego_bytes,
        suffix=".wav",
        kind=MediaType.AUDIO,
    )

    # -------------------------------------------------
    # 5. Extract payload
    # -------------------------------------------------

    extracted = service.extract(
        stego_media,
        lsb=LSB,
        start=START_LOCATION,
    )

    print()
    print("Original payload:")
    print(PAYLOAD)

    print()
    print("Extracted payload:")
    print(extracted)

    # -------------------------------------------------
    # 6. Verify result
    # -------------------------------------------------

    print()

    if extracted == PAYLOAD:
        print("SUCCESS: Extracted payload matches exactly.")
    else:
        print("FAILED: Extracted payload does not match.")


if __name__ == "__main__":
    main()