"""Preview helpers for the glass desktop: show what protection changed.

A stego file is meant to look and sound identical to its cover, so the GUI
renders the difference instead. The payload occupies a small contiguous run
of units, so a whole-image view shrinks the change to nothing. The image
difference therefore zooms into the region that changed, paints every changed
pixel in a highlight colour over a dimmed copy of the protected image, and
thickens the marks when the region still has to be scaled down. For audio the
number of changed samples is reported.
"""
import io
import math
import wave
from dataclasses import dataclass

import numpy as np
from PIL import Image

HIGHLIGHT = (255, 214, 120)
ZOOM_TO = (360, 270)  # target size of the zoomed crop, 4:3


@dataclass(frozen=True)
class ImageDifference:
    png: bytes
    changed: int
    total: int
    box: tuple[int, int, int, int] | None  # x0, y0, x1, y1 of the zoomed crop
    scale: float  # zoom factor applied to the crop (>1 enlarges)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Grow True pixels by ``radius`` in every direction (max filter)."""
    grown = mask.copy()
    for _ in range(radius):
        padded = np.pad(grown, 1)
        grown = (padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]
                 | padded[:-2, :-2] | padded[:-2, 2:] | padded[2:, :-2] | padded[2:, 2:] | grown)
    return grown


def _crop_box(changed: np.ndarray) -> tuple[int, int, int, int]:
    """A window around the changed pixels, clipped to the image."""
    height, width = changed.shape
    ys, xs = np.nonzero(changed)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    box_w, box_h = max(x1 - x0 + 1, 48), max(y1 - y0 + 1, 24)
    box_w, box_h = min(math.ceil(box_w * 1.3), width), min(math.ceil(box_h * 1.3), height)  # margin
    # The payload run usually spans a few full rows, so allow a wide strip
    # (up to 4:1) rather than padding it out into a near-complete image.
    if box_w > 4 * box_h:
        box_h = min(math.ceil(box_w / 4), height)
    elif box_h > 2 * box_w:
        box_w = min(math.ceil(box_h / 2), width)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left = int(min(max(cx - box_w / 2, 0), width - box_w))
    top = int(min(max(cy - box_h / 2, 0), height - box_h))
    return left, top, left + box_w, top + box_h


def image_difference(original: bytes, protected: bytes) -> ImageDifference:
    before = np.asarray(Image.open(io.BytesIO(original)).convert("RGBA"), dtype=np.int16)
    after = np.asarray(Image.open(io.BytesIO(protected)).convert("RGBA"), dtype=np.int16)
    if before.shape != after.shape:
        raise ValueError("The original and protected images differ in size.")
    changed = np.any(before != after, axis=-1)
    count, total = int(changed.sum()), int(changed.size)
    dimmed = (after[..., :3] // 4).astype(np.uint8)
    if count == 0:
        canvas = Image.fromarray(dimmed, "RGB")
        canvas.thumbnail(ZOOM_TO)
        return ImageDifference(_png(canvas), 0, total, None, 1.0)
    x0, y0, x1, y1 = _crop_box(changed)
    crop_w, crop_h = x1 - x0, y1 - y0
    scale = min(ZOOM_TO[0] / crop_w, ZOOM_TO[1] / crop_h)
    mask = changed[y0:y1, x0:x1]
    if scale < 1:  # the crop will shrink: thicken marks so they stay visible
        mask = _dilate(mask, math.ceil(1 / scale))
    region = dimmed[y0:y1, x0:x1].copy()
    region[mask] = HIGHLIGHT
    canvas = Image.fromarray(region, "RGB")
    size = (max(1, round(crop_w * scale)), max(1, round(crop_h * scale)))
    canvas = canvas.resize(size, Image.NEAREST if scale >= 1 else Image.LANCZOS)
    return ImageDifference(_png(canvas), count, total, (x0, y0, x1, y1), scale)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _samples(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data), "rb") as reader:
        width = reader.getsampwidth()
        frames = reader.readframes(reader.getnframes())
    if width == 2:
        return np.frombuffer(frames, dtype="<i2")
    return np.frombuffer(frames, dtype=np.uint8)


def audio_difference(original: bytes, protected: bytes) -> tuple[int, int]:
    """Return (changed sample count, total sample count)."""
    before, after = _samples(original), _samples(protected)
    if before.shape != after.shape:
        raise ValueError("The original and protected audio differ in length.")
    return int(np.count_nonzero(before != after)), int(before.size)
