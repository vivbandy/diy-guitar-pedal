"""Tone fingerprint: a handful of numbers that describe how a guitar recording sounds.

Built to compare a reference (a guitar stem pulled out of a song) with a render of a candidate
patch, so every feature is chosen to be mostly independent of *which notes* were played:

- band_db / tilt_db_per_oct / centroid_hz: overall frequency balance (EQ, cab, amp voicing).
- crest_db / flatness_db: how distorted it is. Clipping flattens peaks (lower crest) and adds
  harmonics that fill in the spectrum (flatness closer to 0 dB).
- dynamic_range_db: how compressed it is.
- delay_ms / delay_strength: a delay is a linear filter (x + g*x shifted by D), which puts a
  ripple in the log spectrum and a lone peak at quefrency D in the cepstrum. The player's own
  repeated notes aren't sample-exact copies, and a held note's pitch makes a dense comb of small
  peaks rather than one isolated one, so neither passes the isolation test.
- decay_db_per_s: how fast the sound dies away after notes stop (reverb and delay tails).
- mod_rate_hz / mod_depth: slow wobble in brightness, as from chorus, phaser or rotary.

Numbers only, numpy only. Each value carries a rough confidence where one makes sense; features
that couldn't be measured are None rather than a guess.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

BAND_CENTERS_HZ = [80 * 2 ** (i / 3) for i in range(22)]  # 80 Hz .. ~10 kHz, 1/3 octave
FRAME_S = 0.02
DELAY_RANGE_MS = (60.0, 1500.0)
MIN_DELAY_STRENGTH = 4.0  # cepstral peak over the median level; below this, call it "no delay"
MIN_DELAY_ISOLATION = 2.0  # ...and over the next-highest peak within +/-25 ms
MIN_MOD_DEPTH = 8.5  # rough: chorus at 1.5 Hz scores ~10, no modulation ~6-7


@dataclass
class Fingerprint:
    duration_s: float
    band_db: list[float]
    tilt_db_per_oct: float
    centroid_hz: float
    crest_db: float
    flatness_db: float
    dynamic_range_db: float
    delay_ms: float | None
    delay_strength: float
    decay_db_per_s: float | None
    mod_rate_hz: float | None
    mod_depth: float

    def to_dict(self) -> dict:
        return asdict(self)


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Mono float audio from a PCM (16/24/32-bit) or 32-bit float WAV."""
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAV file")
    pos, fmt, audio = 12, None, None
    while pos + 8 <= len(data):
        chunk, size = data[pos : pos + 4], int.from_bytes(data[pos + 4 : pos + 8], "little")
        body = data[pos + 8 : pos + 8 + size]
        if chunk == b"fmt ":
            fmt = body
        elif chunk == b"data":
            audio = body
        pos += 8 + size + (size & 1)
    if fmt is None or audio is None:
        raise ValueError(f"{path}: missing fmt or data chunk")

    tag = int.from_bytes(fmt[0:2], "little")
    channels = int.from_bytes(fmt[2:4], "little")
    rate = int.from_bytes(fmt[4:8], "little")
    bits = int.from_bytes(fmt[14:16], "little")
    if tag == 0xFFFE and len(fmt) >= 26:  # WAVE_FORMAT_EXTENSIBLE: real tag is in the GUID
        tag = int.from_bytes(fmt[24:26], "little")

    if tag == 3 and bits == 32:
        x = np.frombuffer(audio, dtype="<f4").astype(np.float64)
    elif tag == 3 and bits == 64:
        x = np.frombuffer(audio, dtype="<f8").copy()
    elif tag == 1 and bits == 16:
        x = np.frombuffer(audio, dtype="<i2") / 32768.0
    elif tag == 1 and bits == 24:
        raw = np.frombuffer(audio[: len(audio) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        ints = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8)
        ints |= raw[:, 2].astype(np.int32) << 16
        x = np.where(ints >= 1 << 23, ints - (1 << 24), ints) / float(1 << 23)
    elif tag == 1 and bits == 32:
        x = np.frombuffer(audio, dtype="<i4") / float(1 << 31)
    else:
        raise ValueError(f"{path}: unsupported WAV encoding (format {tag}, {bits}-bit)")

    x = x[: len(x) // channels * channels].reshape(-1, channels).mean(axis=1)
    return x, rate


def fingerprint(x: np.ndarray, sr: int) -> Fingerprint:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    peak = np.max(np.abs(x)) if x.size else 0.0
    if peak <= 0:
        raise ValueError("audio is silent")
    x = x / peak

    hop = max(1, int(FRAME_S * sr))
    frames = _frames(x, hop)
    rms_db = 10 * np.log10(np.mean(frames**2, axis=1) + 1e-12)
    active = rms_db > (np.max(rms_db) - 40)  # ignore silence and the noise floor

    band_db, centroid = _spectral_balance(frames[active], sr)
    octaves = np.log2(np.array(BAND_CENTERS_HZ) / 1000.0)
    tilt = float(np.polyfit(octaves, band_db, 1)[0])

    delay_ms, delay_strength = _delay(x, sr)
    mod_rate, mod_depth = _modulation(frames, active, sr, hop)

    return Fingerprint(
        duration_s=round(len(x) / sr, 3),
        band_db=[round(float(v), 2) for v in band_db],
        tilt_db_per_oct=round(tilt, 3),
        centroid_hz=round(float(centroid), 1),
        crest_db=round(_crest(frames[active]), 2),
        flatness_db=round(_flatness_db(frames[active], sr), 2),
        dynamic_range_db=round(
            float(np.percentile(rms_db[active], 95) - np.percentile(rms_db[active], 10)), 2
        ),
        delay_ms=None if delay_ms is None else round(delay_ms, 1),
        delay_strength=round(delay_strength, 2),
        decay_db_per_s=_decay(rms_db, active),
        mod_rate_hz=mod_rate,
        mod_depth=round(mod_depth, 4),
    )


def fingerprint_file(path: str | Path) -> Fingerprint:
    x, sr = read_wav(path)
    return fingerprint(x, sr)


# --- features ---------------------------------------------------------------------------------


def _frames(x: np.ndarray, hop: int) -> np.ndarray:
    n = len(x) // hop
    return x[: n * hop].reshape(n, hop)


def _spectral_balance(frames: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    # Long-term average spectrum over ~85 ms windows: steady enough to describe EQ, short enough
    # that a 20 s clip gives hundreds of averages.
    size = 4096
    signal = frames.reshape(-1)
    window = np.hanning(size)
    starts = range(0, max(1, len(signal) - size), size // 2)
    power = np.zeros(size // 2 + 1)
    for start in starts:
        chunk = signal[start : start + size]
        if len(chunk) < size:
            chunk = np.pad(chunk, (0, size - len(chunk)))
        power += np.abs(np.fft.rfft(chunk * window)) ** 2
    freqs = np.fft.rfftfreq(size, 1 / sr)

    bands = []
    for center in BAND_CENTERS_HZ:
        lo, hi = center * 2 ** (-1 / 6), center * 2 ** (1 / 6)
        mask = (freqs >= lo) & (freqs < hi)
        bands.append(10 * np.log10(np.mean(power[mask]) + 1e-20) if mask.any() else -200.0)
    band_db = np.array(bands)
    band_db -= np.mean(band_db)  # shape only; loudness is not a tone property

    useful = (freqs > 60) & (freqs < 12000)
    centroid = np.sum(freqs[useful] * power[useful]) / (np.sum(power[useful]) + 1e-20)
    return band_db, centroid


def _crest(frames: np.ndarray) -> float:
    # Median per-frame crest factor: clipping caps peaks relative to RMS.
    rms = np.sqrt(np.mean(frames**2, axis=1)) + 1e-12
    return float(np.median(20 * np.log10(np.max(np.abs(frames), axis=1) / rms + 1e-12)))


def _flatness_db(frames: np.ndarray, sr: int) -> float:
    # Spectral flatness (dB) in the 200 Hz - 5 kHz guitar range, per ~85 ms window, median over
    # windows. Clean notes are a few sharp harmonics (very negative); distortion fills the gaps.
    size = 4096
    signal = frames.reshape(-1)
    freqs = np.fft.rfftfreq(size, 1 / sr)
    band = (freqs > 200) & (freqs < 5000)
    window = np.hanning(size)
    values = []
    for start in range(0, max(1, len(signal) - size), size):
        chunk = signal[start : start + size]
        if len(chunk) < size:
            break
        p = np.abs(np.fft.rfft(chunk * window))[band] ** 2 + 1e-20
        values.append(10 * (np.mean(np.log10(p)) - np.log10(np.mean(p))))
    return float(np.median(values)) if values else -100.0


def _delay(x: np.ndarray, sr: int) -> tuple[float | None, float]:
    """Echo time from the real cepstrum. Returns (delay_ms or None, peak strength)."""
    n = 1 << int(math.ceil(math.log2(len(x))))
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
    cepstrum = np.fft.irfft(np.log(spectrum + 1e-9 * np.max(spectrum)))

    lo = int(DELAY_RANGE_MS[0] * sr / 1000)
    hi = min(int(DELAY_RANGE_MS[1] * sr / 1000), len(cepstrum) // 2)
    if hi <= lo:
        return None, 0.0
    region = np.abs(cepstrum[lo:hi])
    best = int(np.argmax(region))
    noise = float(np.median(region)) + 1e-12
    strength = float(region[best]) / noise

    # Feedback makes peaks at D, 2D, 3D...; the strongest can be a multiple. Prefer the shortest
    # lag that is a clear peak and divides the best one.
    best_lag = lo + best
    if _isolation(region, best, sr) < MIN_DELAY_ISOLATION:
        return None, strength
    for divisor in (4, 3, 2):
        lag = best_lag / divisor
        if lag < lo:
            continue
        i = int(round(lag)) - lo
        window = region[max(0, i - 3) : i + 4]
        if window.size and window.max() / noise >= max(MIN_DELAY_STRENGTH, 0.5 * strength):
            j = max(0, i - 3) + int(np.argmax(window))
            if _isolation(region, j, sr) >= MIN_DELAY_ISOLATION:
                best_lag = lo + j
                break

    if strength < MIN_DELAY_STRENGTH:
        return None, strength
    return best_lag * 1000.0 / sr, strength


def _isolation(region: np.ndarray, i: int, sr: int) -> float:
    """Peak height over the highest other peak within +/-25 ms (ignoring its own +/-1.5 ms)."""
    near, own = int(0.025 * sr), int(0.0015 * sr)
    left = region[max(0, i - near) : max(0, i - own)]
    right = region[i + own + 1 : i + near + 1]
    rest = np.concatenate([left, right])
    return float(region[i] / (rest.max() + 1e-12)) if rest.size else float("inf")


def _decay(rms_db: np.ndarray, active: np.ndarray) -> float | None:
    """Median slope (dB/s, negative) of the falls after notes stop."""
    slopes = []
    i, n = 1, len(rms_db)
    min_len = int(0.15 / FRAME_S)
    while i < n - min_len:
        if active[i] and rms_db[i] >= rms_db[i - 1] and rms_db[i] > rms_db[i + 1]:
            j = i
            while j + 1 < n and rms_db[j + 1] <= rms_db[j] + 0.5:
                j += 1
            drop = rms_db[i] - rms_db[j]
            if j - i >= min_len and drop >= 12:
                t = np.arange(j - i + 1) * FRAME_S
                slopes.append(np.polyfit(t, rms_db[i : j + 1], 1)[0])
            i = j + 1
        else:
            i += 1
    return round(float(np.median(slopes)), 1) if slopes else None


def _modulation(
    frames: np.ndarray, active: np.ndarray, sr: int, hop: int
) -> tuple[float | None, float]:
    """Rate of a periodic sweep in the spectrum between 0.3 and 8 Hz (chorus, phaser, rotary).

    Each frequency bin's level over time is high-passed to drop note envelopes; a modulation
    effect makes every bin wobble at the same rate, so the averaged modulation spectrum peaks.
    """
    if active.sum() < int(2.0 / FRAME_S):
        return None, 0.0
    size = 2 * hop
    signal = frames.reshape(-1)
    count = (len(signal) - size) // hop
    if count < int(2.0 / FRAME_S):
        return None, 0.0
    idx = np.arange(size)[None, :] + hop * np.arange(count)[:, None]
    spec = np.abs(np.fft.rfft(signal[idx] * np.hanning(size), axis=1))
    freqs = np.fft.rfftfreq(size, 1 / sr)
    band = (freqs > 300) & (freqs < 3000)
    levels = 20 * np.log10(spec[:, band] + 1e-9)
    keep = active[:count]
    levels = levels[keep]
    # Remove each bin's slow trend and the frame's overall level (note dynamics), keeping shape.
    levels = levels - levels.mean(axis=1, keepdims=True)
    kernel = np.ones(25) / 25
    trend = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), 0, levels)
    wobble = levels - trend
    window = np.hanning(len(wobble))[:, None]
    power = (np.abs(np.fft.rfft(wobble * window, axis=0)) ** 2).mean(axis=1)
    rates = np.fft.rfftfreq(len(wobble), FRAME_S)
    sel = (rates >= 0.3) & (rates <= 8.0)
    if not sel.any():
        return None, 0.0
    k = int(np.argmax(power[sel]))
    depth = float(power[sel][k] / (np.median(power[sel]) + 1e-20))
    if depth < MIN_MOD_DEPTH:
        return None, depth
    return round(float(rates[sel][k]), 2), depth
