"""Tempo / beat detection used to quantize the tab to a rhythmic grid."""

from __future__ import annotations

from pathlib import Path


def detect_tempo(audio_path: Path, log=print) -> tuple[float | None, float]:
    """Estimate (bpm, first_beat_time_seconds) for ``audio_path``.

    Returns ``(None, 0.0)`` if estimation fails so callers can fall back to
    un-quantized timing.
    """
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        if y.size < sr:  # less than ~1s of audio
            return None, 0.0
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        bpm = float(np.atleast_1d(tempo)[0])
        beat_origin = float(beats[0]) if len(beats) else 0.0
        if not (30.0 <= bpm <= 300.0):
            return None, 0.0
        log(f"Detected tempo ~{bpm:.1f} BPM (first beat at {beat_origin:.2f}s)")
        return bpm, beat_origin
    except Exception as exc:  # noqa: BLE001
        log(f"Tempo detection failed ({exc}); using un-quantized timing")
        return None, 0.0
