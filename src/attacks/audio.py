"""Audio attacks for 16-bit PCM WAV: sample edits, noise, truncation and gain."""
import io
import wave

import numpy as np

from src.attacks import AUDIO, AttackContext, register
from src.exceptions import IntegrationError
from src.models import Media, MediaType


def load(media: Media) -> tuple[tuple, np.ndarray]:
    """Decode to (wave params, int16 samples with channels interleaved)."""
    try:
        with wave.open(io.BytesIO(media.data), "rb") as reader:
            params = reader.getparams()
            frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as exc:
        raise IntegrationError("The selected file is not a readable PCM WAV.") from exc
    if params.sampwidth != 2:
        raise IntegrationError("Audio attacks support 16-bit PCM WAV files.")
    return params, np.frombuffer(frames, dtype="<i2").copy()


def save(params, samples: np.ndarray) -> Media:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(params.nchannels)
        writer.setsampwidth(params.sampwidth)
        writer.setframerate(params.framerate)
        writer.writeframes(samples.astype("<i2").tobytes())
    return Media(buffer.getvalue(), ".wav", MediaType.AUDIO)


@register("sample_edit", "Edit one sample",
          "Flips a high-order bit of one sample in the middle of the clip: a single click, inaudible in most material.", AUDIO)
def sample_edit(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    samples[len(samples) // 2] ^= 0x4000
    return save(params, samples)


@register("silence_tail", "Silence the tail",
          "Zeroes the last twentieth of the samples, like trimming or muting the end of a clip.", AUDIO)
def silence_tail(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    samples[len(samples) - max(1, len(samples) // 20):] = 0
    return save(params, samples)


@register("lsb_noise", "Randomise low bits",
          "Randomises the lowest bit of every sample: inaudible, but it scrambles any embedded payload.", AUDIO)
def lsb_noise(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    noise = np.random.default_rng(ctx.seed).integers(0, 2, samples.shape, dtype=np.int16)
    return save(params, samples ^ noise)


@register("lsb_strip", "Clear low bits",
          "Clears the lowest bits of every sample at the chosen LSB depth, wiping the payload without audible change.", AUDIO)
def lsb_strip(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    mask = np.int16(-(1 << ctx.lsb))
    return save(params, samples & mask)


@register("truncate", "Truncate the end",
          "Drops the last tenth of the samples. Earlier samples, and a payload stored there, stay intact.", AUDIO)
def truncate(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    keep = max(params.nchannels, len(samples) - max(1, len(samples) // 10))
    keep -= keep % params.nchannels
    return save(params, samples[:keep])


@register("gain", "Change volume",
          "Scales every sample to 80% volume, so every value is recomputed.", AUDIO)
def gain(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    return save(params, np.clip(np.round(samples * 0.8), -32768, 32767).astype("<i2"))


@register("reencode_lossless", "Re-write the WAV",
          "Reads and rewrites the WAV with identical samples. Protection should survive.", AUDIO)
def reencode_lossless(media: Media, ctx: AttackContext) -> Media:
    params, samples = load(media)
    return save(params, samples)
