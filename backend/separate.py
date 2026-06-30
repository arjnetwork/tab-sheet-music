"""Isolate a guitar stem from a full mix using Demucs.

We use the Demucs Python API (``htdemucs_6s``, a 6-source model with a dedicated
``guitar`` stem) and handle audio decoding/encoding ourselves with librosa /
soundfile. This deliberately avoids ``torchaudio.load``/``save``, whose newer
versions require the ``torchcodec`` backend that isn't reliably available on
Windows. Model weights download automatically on first use.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL = "htdemucs_6s"

# Cache the loaded model across jobs (loading weights every time is wasteful).
_MODEL_CACHE = {}


class SeparationError(RuntimeError):
    pass


def _get_model():
    if MODEL not in _MODEL_CACHE:
        from demucs.pretrained import get_model

        model = get_model(MODEL)
        model.cpu()
        model.eval()
        _MODEL_CACHE[MODEL] = model
    return _MODEL_CACHE[MODEL]


def _load_audio(path: Path, samplerate: int, channels: int):
    """Decode any audio file to a float32 tensor shaped [channels, samples]."""
    import librosa
    import torch

    # librosa uses soundfile for wav/flac/ogg and falls back to ffmpeg
    # (audioread) for mp3/m4a/etc., so this handles every format we accept.
    y, _ = librosa.load(str(path), sr=samplerate, mono=False)
    y = np.asarray(y, dtype=np.float32)

    if y.ndim == 1:
        y = np.stack([y] * channels, axis=0)
    elif y.shape[0] == 1:
        y = np.repeat(y, channels, axis=0)
    elif y.shape[0] > channels:
        y = y[:channels]
    elif y.shape[0] < channels:
        y = np.repeat(y[:1], channels, axis=0)

    return torch.from_numpy(np.ascontiguousarray(y))


def _save_wav(tensor, path: Path, samplerate: int) -> None:
    import soundfile as sf

    data = tensor.detach().cpu().numpy().T  # -> [samples, channels]
    sf.write(str(path), data, samplerate)


def _bandlimit(samples, samplerate: int, low: float = 70.0, high: float = 8000.0):
    """Band-pass the stem to the guitar's useful range.

    Removes sub-bass rumble / bass-guitar bleed below ``low`` and cymbal hiss
    above ``high``, both of which otherwise turn into phantom notes during
    transcription. ``samples`` is a numpy array shaped [channels, n].
    """
    from scipy.signal import butter, sosfiltfilt

    nyq = samplerate / 2.0
    high = min(high, nyq - 100.0)
    if not (0 < low < high < nyq):
        return samples
    sos = butter(4, [low, high], btype="band", fs=samplerate, output="sos")
    return sosfiltfilt(sos, samples, axis=-1).astype(samples.dtype)


# Per-instrument band-limit ranges (Hz) used to suppress out-of-range bleed.
_BANDS = {
    "guitar": (70.0, 8000.0),
    "bass": (30.0, 1200.0),
    "piano": (27.0, 6000.0),
}


def isolate_stem(
    input_path: Path,
    work_dir: Path,
    target: str = "guitar",
    quality: str = "fast",
    log=print,
) -> Path:
    """Separate ``input_path`` and return the path to the ``target`` stem (wav).

    ``target`` is "guitar" or "bass". ``quality`` is "fast" (single pass) or
    "high" (multi-shift test-time augmentation, ~3-5x slower but cleaner).
    """
    import numpy as np
    import torch
    from demucs.apply import apply_model

    input_path = Path(input_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    target = target if target in ("guitar", "bass", "piano") else "guitar"
    shifts, overlap = (2, 0.35) if quality == "high" else (1, 0.25)

    try:
        model = _get_model()
        log(f"Loaded Demucs model '{MODEL}' (stems: {', '.join(model.sources)})")
        log(f"Target: {target} | quality: {quality} (shifts={shifts}, overlap={overlap})")

        wav = _load_audio(input_path, model.samplerate, model.audio_channels)
        log(f"Decoded audio: {wav.shape[1]} samples @ {model.samplerate} Hz")

        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        wav = (wav - mean) / std

        with torch.no_grad():
            sources = apply_model(
                model,
                wav[None],
                device="cpu",
                progress=True,
                split=True,
                shifts=shifts,
                overlap=overlap,
            )[0]
        sources = sources * std + mean

        stem_name = target if target in model.sources else "other"
        if stem_name != target:
            log(f"'{target}' stem unavailable; falling back to 'other' stem")
        idx = model.sources.index(stem_name)

        low, high = _BANDS.get(target, _BANDS["guitar"])
        stem = sources[idx].detach().cpu().numpy()
        stem = _bandlimit(stem, model.samplerate, low, high)
        log(f"Band-limited stem to ~{int(low)}-{int(high)} Hz to suppress bleed")

        out_dir = work_dir / MODEL / input_path.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        stem_path = out_dir / f"{stem_name}.wav"
        _save_wav(torch.from_numpy(np.ascontiguousarray(stem)), stem_path, model.samplerate)
        log(f"Saved {stem_name} stem to {stem_path}")
        return stem_path
    except SeparationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SeparationError(f"Demucs separation failed: {exc}") from exc
