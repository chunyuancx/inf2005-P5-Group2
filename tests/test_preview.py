"""Preview difference rendering used by the glass desktop's media preview."""
import io
import wave

import numpy as np
from PIL import Image

from src.gui.preview import HIGHLIGHT, audio_difference, image_difference


def png(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def test_small_change_in_large_image_is_zoomed_and_visible():
    rng = np.random.default_rng(3)
    cover = rng.integers(0, 256, (1400, 2400, 3), dtype=np.uint8)
    stego = cover.copy()
    stego[700, 1000:1274, 0] ^= 1  # 274 pixels change by one bit
    result = image_difference(png(cover), png(stego))
    assert (result.changed, result.total) == (274, 1400 * 2400)
    x0, y0, x1, y1 = result.box
    assert x0 <= 1000 and x1 >= 1274 and y0 <= 700 <= y1
    image = np.asarray(Image.open(io.BytesIO(result.png)).convert("RGB"))
    highlighted = np.all(image == HIGHLIGHT, axis=-1).sum()
    assert highlighted >= 100, "the changed run must be visible in the rendered crop"
    assert image.shape[1] <= 360 and image.shape[0] <= 270


def test_tiny_image_is_enlarged_with_crisp_pixels():
    cover = np.zeros((20, 30, 3), dtype=np.uint8)
    stego = cover.copy()
    stego[10, 5:9, 1] = 1
    result = image_difference(png(cover), png(stego))
    assert result.changed == 4 and result.scale > 1
    image = np.asarray(Image.open(io.BytesIO(result.png)).convert("RGB"))
    assert np.all(image == HIGHLIGHT, axis=-1).sum() >= 4 * result.scale ** 2 * 0.9


def test_identical_images_report_no_change():
    cover = np.full((64, 64, 3), 90, dtype=np.uint8)
    result = image_difference(png(cover), png(cover))
    assert (result.changed, result.box) == (0, None)


def test_audio_difference_counts_changed_samples():
    samples = (np.sin(np.linspace(0, 200, 4000)) * 10000).astype("<i2")
    original, protected = io.BytesIO(), io.BytesIO()
    for target, data in ((original, samples), (protected, samples ^ np.arange(4000).astype("<i2") % 2)):
        with wave.open(target, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(data.tobytes())
    assert audio_difference(original.getvalue(), protected.getvalue()) == (2000, 4000)
