"""Quick end-to-end check without needing a real song.

1. Renders a short synthetic melody (sine tones at guitar pitches) to WAV.
2. Runs basic-pitch transcription on it (no separation).
3. Converts the notes to ASCII tab.
Also unit-checks the tab renderer on hand-built note events.
"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import tabify, transcribe  # noqa: E402


def midi_to_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def test_tabify_direct():
    # E4(64), then a C major-ish chord, then G3(55).
    events = [
        (0.0, 0.4, 64),
        (0.5, 0.9, 60),
        (0.5, 0.9, 64),
        (0.5, 0.9, 67),
        (1.0, 1.4, 55),
        (1.5, 1.9, 40),
    ]
    tab, n = tabify.events_to_tab(events)
    print(f"[direct] {n} columns")
    print(tab)
    assert n >= 4, "expected several columns"
    print("[direct] OK\n")


def render_melody(path: Path):
    sr = 22050
    melody = [64, 67, 69, 71, 72, 71, 69, 67]  # simple line on the high strings
    note_dur = 0.45
    gap = 0.08
    audio = []
    for m in melody:
        t = np.linspace(0, note_dur, int(sr * note_dur), endpoint=False)
        wave = 0.5 * np.sin(2 * np.pi * midi_to_hz(m) * t)
        # add a couple harmonics so it reads as a plucked tone
        wave += 0.2 * np.sin(2 * np.pi * 2 * midi_to_hz(m) * t)
        wave += 0.1 * np.sin(2 * np.pi * 3 * midi_to_hz(m) * t)
        env = np.minimum(1, np.linspace(1, 0.2, len(t)) * 3)
        audio.append(wave * env)
        audio.append(np.zeros(int(sr * gap)))
    sig = np.concatenate(audio).astype(np.float32)
    sf.write(str(path), sig, sr)


def test_pipeline(tmp: Path):
    wav = tmp / "melody.wav"
    render_melody(wav)
    print(f"[pipeline] wrote {wav} ({wav.stat().st_size} bytes)")
    events = transcribe.transcribe(wav, midi_out=tmp / "melody.mid")
    print(f"[pipeline] transcribed {len(events)} notes")
    tab, n = tabify.events_to_tab(events)
    print(f"[pipeline] {n} columns")
    print(tab)
    assert len(events) > 0, "expected to detect at least one note"
    print("[pipeline] OK")


if __name__ == "__main__":
    test_tabify_direct()
    tmp = Path(__file__).resolve().parent.parent / "outputs" / "_smoke"
    tmp.mkdir(parents=True, exist_ok=True)
    test_pipeline(tmp)
    print("\nALL SMOKE TESTS PASSED")
