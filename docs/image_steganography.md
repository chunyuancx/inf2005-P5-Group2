# Image Steganography

Hides and recovers byte payloads in PNG and BMP images using LSB replacement.

Member 2: Nathan
**Files:** `src/services/image_steganography.py` (core service), `src/attacks/image.py` (attack simulations), `tests/test_image_service.py` (150 tests), `samples/lambda-icon.png` (sample cover)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Dependencies: `numpy`, `pillow`, `cryptography`, `pytest`. The GUI also needs Tkinter (`python3-tk` on Debian/Ubuntu; bundled on Windows/macOS).

## Supported Formats

PNG and BMP only — lossless formats that preserve low bits. Grayscale, RGB, RGBA and palette images are accepted. JPEG, animated and 16-bit images are rejected.

## How It Works

Each colour sample (R, G, B per pixel, row-major order) is one **unit**. Alpha is skipped. The payload is preceded by a 10-byte header (`b"IS"` + length + CRC-32), then written MSB-first into the lowest `lsb` bits of consecutive units starting at `start`.

Capacity formula: `((units - start) × lsb - 80) ÷ 8` bytes. For `lambda-icon.png` (512×512 RGBA = 786,432 units) at depth 1, start 100: **98,281 bytes**.

The stego image is re-saved in the same container, so file bytes differ from the cover. Use `unit_count()` for offsets and `canonical_bytes()` for hashing — never raw file bytes.

## Usage

### Direct API

```python
from pathlib import Path
from src.models import Media, MediaType
from src.services.image_steganography import ImageSteganography

svc = ImageSteganography()
cover = Media(Path("samples/lambda-icon.png").read_bytes(), ".png", MediaType.IMAGE)

print("Capacity:", svc.capacity(cover, lsb=1, start=100), "bytes")

stego_bytes = svc.embed(cover, b"hello, steganography", lsb=1, start=100)
stego = Media(stego_bytes, ".png", MediaType.IMAGE)
print("Recovered:", svc.extract(stego, lsb=1, start=100))
```

```
Capacity: 98281 bytes
Recovered: b'hello, steganography'
```

### GUI Application

```bash
python -m src              # browser window (Edge/Chrome)
python -m src --native     # Tkinter window
python -m src --no-open    # print URL only
```

**Protect:** choose a PNG/BMP → set LSB depth → enter passphrase (or manual start) → Protect → Save.
**Verify:** choose the saved stego file → same depth and passphrase → Verify → expect **Authentic**.

### Tests

```bash
python -m pytest tests/test_image_service.py -v    # 150 passed, 1 skipped
```

### Attack Suite

```bash
python -m src.testing --cover samples/lambda-icon.png
```

```
Attack suite: 35/35 passed; evidence: test-evidence/run-<timestamp>
```

Options: `--lsb N`, `--mode manual|auto|both`, `--message TEXT`, `--output-dir DIR`.

## Attack Results

| Attack | What it does | Manual | Passphrase |
|---|---|---|---|
| `reencode_lossless` | Re-save same format | Authentic | Authentic |
| `convert_container` | PNG↔BMP | Authentic* | Authentic* |
| `pixel_edit` | Flip one pixel's top bit | Tampered | Payload Missing |
| `region_edit` | Paint bottom-right tenth | Tampered | Payload Missing |
| `crop_bottom` | Remove bottom tenth | Tampered | Payload Missing |
| `lsb_noise` | Randomise lowest bits | Payload Missing | Payload Missing |
| `lsb_strip` | Clear low bits | Payload Missing | Payload Missing |
| `resize` | Scale to 90% | Payload Missing | Payload Missing |
| `jpeg_roundtrip` | JPEG quality 90 and back | Payload Missing | Payload Missing |

\*RGBA PNG → BMP drops alpha: Tampered (manual) / Payload Missing (passphrase).

Passphrase mode derives the start from content, so any visible edit shifts the expected position.

## Error Messages

| Situation | Error |
|---|---|
| LSB not 1–8 | `LSB must be an integer from 1 to 8.` |
| Payload too large | `Payload exceeds the available media capacity.` |
| Not PNG/BMP | `Image covers must be PNG or BMP.` |
| Wrong start or depth | `No valid envelope at this location.` |
| Animated image | `Animated images are not supported.` |

## Troubleshooting

- **Stego file doesn't verify:** select the saved stego file (not the original), and match LSB depth and passphrase exactly.
- **Shared image fails:** messaging apps recompress to JPEG. Share the file as-is (e.g. zipped).
- **`ModuleNotFoundError`:** activate the virtual environment and run `pip install -r requirements-dev.txt`.