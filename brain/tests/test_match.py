"""Tone matching: the fingerprint hears what it should, and the tuner moves toward a target.

Audio is synthesized (Karplus-Strong plucks), and the tuner runs against a numpy stand-in for
tone_render, so these tests need numpy but not the C++ renderer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from tone_architect.match import cli  # noqa: E402
from tone_architect.match.compare import distance, explain  # noqa: E402
from tone_architect.match.fingerprint import fingerprint, read_wav  # noqa: E402
from tone_architect.match.tune import prepare, tune  # noqa: E402

SR = 48000


def _pluck(rng, freq: float, dur: float) -> np.ndarray:
    n, period = int(dur * SR), int(SR / freq)
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = 0.996 * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return out


@pytest.fixture(scope="module")
def phrase() -> np.ndarray:
    rng = np.random.default_rng(1)
    x = np.zeros(int(10 * SR))
    t = 0.2
    for f in [196, 247, 294, 330, 392, 330, 294, 247]:
        d = rng.uniform(0.5, 1.2)
        seg = _pluck(rng, f * rng.uniform(0.995, 1.005), d)
        s = int(t * SR)
        x[s : s + len(seg)] += seg[: len(x) - s]
        t += d + rng.uniform(0, 0.3)
    return x


def _echo(x: np.ndarray, ms: float, feedback: float, mix: float) -> np.ndarray:
    d = int(ms * SR / 1000)
    wet = np.zeros_like(x)
    for k in range(1, 8):
        if k * d >= len(x):
            break
        wet[k * d :] += feedback ** (k - 1) * x[: len(x) - k * d]
    return x + mix * wet


def test_dry_phrase_has_no_delay(phrase):
    assert fingerprint(phrase, SR).delay_ms is None


@pytest.mark.parametrize("ms", [180, 380, 480, 900])
def test_delay_time_is_recovered(phrase, ms):
    fp = fingerprint(_echo(phrase, ms, 0.35, 0.3), SR)
    assert fp.delay_ms == pytest.approx(ms, rel=0.02)


def test_distortion_lowers_crest_and_compresses(phrase):
    clean, dirty = fingerprint(phrase, SR), fingerprint(np.tanh(8 * phrase), SR)
    assert dirty.crest_db < clean.crest_db
    assert dirty.dynamic_range_db < clean.dynamic_range_db


def test_brighter_signal_tilts_up(phrase):
    bright = phrase + 5 * np.concatenate([[0.0], np.diff(phrase)])
    assert fingerprint(bright, SR).tilt_db_per_oct > fingerprint(phrase, SR).tilt_db_per_oct + 1


def test_distance_is_zero_for_identical_and_explains_delay(phrase):
    a = fingerprint(_echo(phrase, 480, 0.35, 0.3), SR)
    b = fingerprint(_echo(phrase, 300, 0.35, 0.3), SR)
    assert distance(a, a)[0] == 0
    total, parts = distance(a, b)
    assert parts["delay"] > 1 and total > 0
    assert any("300 ms" in note and "480 ms" in note for note in explain(a, b))


def test_read_wav_round_trips_pcm16(tmp_path, phrase):
    import wave

    path = tmp_path / "x.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        pcm = (phrase[:SR] * 0.5 * 32767).astype("<i2")
        w.writeframes(np.column_stack([pcm, pcm]).tobytes())
    x, sr = read_wav(path)
    assert sr == SR and len(x) == SR
    assert np.allclose(x, pcm / 32768.0, atol=1e-6)


def _patch(time_ms=300.0, mix=0.1) -> dict:
    return {
        "schema_version": "1.0",
        "name": "t",
        "chain": [
            {"type": "nam_capture", "params": {"capture_id": "amp"}},
            {"type": "eq", "params": {"bands": [{"freq_hz": 3000, "gain_db": 0}]}},
            {"type": "delay", "params": {"time_ms": time_ms, "feedback": 0.3, "mix": mix}},
        ],
    }


def _fake_render(phrase, tmp_path):
    """Stand-in for tone_render: echo by the patch's delay, brightness by its EQ gain."""
    import wave

    counter = iter(range(10_000))

    def render(patch: dict) -> Path:
        delay = next(n for n in patch["chain"] if n["type"] == "delay")["params"]
        eq = next(n for n in patch["chain"] if n["type"] == "eq")["params"]["bands"][0]
        y = phrase + 0.2 * eq["gain_db"] * np.concatenate([[0.0], np.diff(phrase)])
        y = _echo(y, delay["time_ms"], delay["feedback"], delay["mix"])
        y = y / np.abs(y).max() * 0.8
        path = tmp_path / f"r{next(counter)}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((y * 32767).astype("<i2").tobytes())
        return path

    return render


def test_prepare_seeds_measured_delay_and_adds_eq(phrase):
    ref = fingerprint(_echo(phrase, 480, 0.35, 0.3), SR)
    patch = {
        "schema_version": "1.0",
        "name": "t",
        "chain": [{"type": "nam_capture", "params": {"capture_id": "amp"}}],
    }
    prepared = prepare(patch, ref)
    types = [n["type"] for n in prepared["chain"]]
    assert types == ["nam_capture", "eq", "delay"]
    assert prepared["chain"][2]["params"]["time_ms"] == pytest.approx(480, rel=0.02)
    assert patch["chain"] == [{"type": "nam_capture", "params": {"capture_id": "amp"}}]


def test_tune_moves_toward_the_reference(phrase, tmp_path):
    render = _fake_render(phrase, tmp_path)
    target = _patch(time_ms=480, mix=0.3)
    target["chain"][1]["params"]["bands"][0]["gain_db"] = 6
    ref = fingerprint(read_wav(render(target))[0], SR)

    result = tune(_patch(time_ms=300, mix=0.1), ref, render, max_evals=40)

    assert result.score < result.start_score / 2
    delay = result.patch["chain"][2]["params"]
    assert delay["time_ms"] == pytest.approx(480, rel=0.02)
    assert result.patch["chain"][1]["params"]["bands"][0]["gain_db"] > 2
    assert result.evaluations <= 40


def test_cli_compare_prints_distance(phrase, tmp_path, capsys):
    render = _fake_render(phrase, tmp_path)
    a, b = render(_patch(480, 0.3)), render(_patch(300, 0.3))
    assert cli.main(["compare", str(a), str(b)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("distance") and "delay" in out
    assert cli.main(["fingerprint", str(a)]) == 0
    assert json.loads(capsys.readouterr().out)["delay_ms"] == pytest.approx(480, rel=0.02)
