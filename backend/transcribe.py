"""Transcribe audio into note events using Spotify's basic-pitch model."""

from __future__ import annotations

from pathlib import Path

# Per-instrument pitch ranges (Hz) used to constrain the transcription.
FREQ_RANGES = {
    "guitar": (75.0, 1400.0),   # ~low E up to a bit above the high frets
    "bass": (30.0, 420.0),      # low B/E up to upper bass register
    "piano": (27.0, 4300.0),    # A0 up to ~C8
}


class TranscriptionError(RuntimeError):
    pass


def transcribe(
    audio_path: Path,
    instrument: str = "guitar",
    midi_out: Path | None = None,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_length_ms: float = 80.0,
    log=print,
):
    """Return a list of note events ``(start, end, pitch, amplitude, bends)``.

    Optionally writes the predicted MIDI to ``midi_out``.
    """
    try:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except Exception as exc:  # pragma: no cover - import-time environment issue
        raise TranscriptionError(f"basic-pitch is not available: {exc}") from exc

    audio_path = Path(audio_path)
    min_hz, max_hz = FREQ_RANGES.get(instrument, FREQ_RANGES["guitar"])
    log(f"Transcribing {audio_path.name} with basic-pitch ({instrument})...")

    try:
        model_output, midi_data, note_events = predict(
            str(audio_path),
            model_or_model_path=ICASSP_2022_MODEL_PATH,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_length_ms,
            minimum_frequency=min_hz,
            maximum_frequency=max_hz,
        )
    except TypeError:
        # Older basic-pitch signatures don't accept model_or_model_path.
        model_output, midi_data, note_events = predict(str(audio_path))

    if midi_out is not None and midi_data is not None:
        midi_out = Path(midi_out)
        midi_out.parent.mkdir(parents=True, exist_ok=True)
        midi_data.write(str(midi_out))
        log(f"Wrote MIDI to {midi_out}")

    log(f"Detected {len(note_events)} notes")
    return note_events
