"""Image attacks: pixel edits, noise, geometry changes and format round trips."""
import io

import numpy as np
from PIL import Image

from src.attacks import IMAGE, AttackContext, register
from src.exceptions import IntegrationError
from src.models import Media, MediaType

CONTAINERS = {".png": "PNG", ".bmp": "BMP"}


def load(media: Media) -> tuple[np.ndarray, str]:
    """Decode to an array (L, RGB or RGBA) plus the PIL container name."""
    container = CONTAINERS.get(media.suffix.lower())
    if container is None:
        raise IntegrationError("Image attacks support PNG and BMP files.")
    try:
        image = Image.open(io.BytesIO(media.data))
        image.load()
    except Exception as exc:
        raise IntegrationError("The selected file is not a readable image.") from exc
    if image.mode not in {"L", "RGB", "RGBA"}:
        image = image.convert("RGB")
    return np.array(image), container


def save(pixels: np.ndarray, suffix: str) -> Media:
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format=CONTAINERS[suffix.lower()])
    return Media(buffer.getvalue(), suffix.lower(), MediaType.IMAGE)


@register("pixel_edit", "Edit one pixel",
          "Flips the top bit of one channel of the centre pixel: the smallest visible edit.", IMAGE)
def pixel_edit(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    y, x = pixels.shape[0] // 2, pixels.shape[1] // 2
    if pixels.ndim == 2:
        pixels[y, x] ^= 0x80
    else:
        pixels[y, x, 0] ^= 0x80
    return save(pixels, media.suffix)


@register("region_edit", "Paint a block",
          "Paints a solid block over the bottom-right tenth of the image, like a stamp or watermark.", IMAGE)
def region_edit(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    h, w = pixels.shape[:2]
    y0, x0 = max(0, h - max(1, h // 10)), max(0, w - max(1, w // 10))
    pixels[y0:, x0:] = 255 if pixels.ndim == 2 else np.array([255, 0, 96, 255][:pixels.shape[2]], dtype=np.uint8)
    return save(pixels, media.suffix)


@register("lsb_noise", "Randomise low bits",
          "Randomises the lowest bit of every channel: invisible, but it scrambles any embedded payload.", IMAGE)
def lsb_noise(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    noise = np.random.default_rng(ctx.seed).integers(0, 2, pixels.shape, dtype=np.uint8)
    return save(pixels ^ noise, media.suffix)


@register("lsb_strip", "Clear low bits",
          "Clears the lowest bits of every channel at the chosen LSB depth, wiping the payload without visible change.", IMAGE)
def lsb_strip(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    mask = np.uint8((0xFF << ctx.lsb) & 0xFF)
    return save(pixels & mask, media.suffix)


@register("crop_bottom", "Crop the bottom",
          "Removes the bottom tenth of the image. Earlier pixels, and a payload stored there, stay intact.", IMAGE)
def crop_bottom(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    keep = max(1, pixels.shape[0] - max(1, pixels.shape[0] // 10))
    return save(np.ascontiguousarray(pixels[:keep]), media.suffix)


@register("resize", "Resize to 90%",
          "Scales the image to 90% with resampling, so every pixel value is recomputed.", IMAGE)
def resize(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    image = Image.fromarray(pixels)
    smaller = image.resize((max(1, int(image.width * 0.9)), max(1, int(image.height * 0.9))), Image.LANCZOS)
    return save(np.array(smaller), media.suffix)


@register("reencode_lossless", "Re-save losslessly",
          "Decodes and re-saves the file in the same lossless format. Pixels are unchanged, so protection should survive.", IMAGE)
def reencode_lossless(media: Media, ctx: AttackContext) -> Media:
    pixels, container = load(media)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format=container, compress_level=1 if container == "PNG" else None)
    return Media(buffer.getvalue(), media.suffix, MediaType.IMAGE)


@register("convert_container", "Convert PNG to BMP or back",
          "Rewrites the same pixels in the other lossless container (PNG to BMP or BMP to PNG).", IMAGE)
def convert_container(media: Media, ctx: AttackContext) -> Media:
    pixels, container = load(media)
    if pixels.ndim == 3 and pixels.shape[2] == 4 and container == "PNG":
        pixels = pixels[..., :3]  # BMP has no alpha channel
    other = ".bmp" if container == "PNG" else ".png"
    return save(pixels, other)


@register("jpeg_roundtrip", "JPEG round trip",
          "Saves as JPEG at quality 90 and converts back: lossy compression rewrites the low bits everywhere.", IMAGE)
def jpeg_roundtrip(media: Media, ctx: AttackContext) -> Media:
    pixels, _ = load(media)
    image = Image.fromarray(pixels)
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    if alpha is not None:
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    restored = Image.open(io.BytesIO(buffer.getvalue()))
    if alpha is not None:  # JPEG has no alpha; keep the original channel so only colour changes
        restored = restored.convert("RGB")
        restored.putalpha(alpha)
    return save(np.array(restored), media.suffix)
