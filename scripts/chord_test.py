import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.chords import name_chord  # noqa: E402

cases = {
    "C major": [60, 64, 67],
    "C/E (inv)": [64, 60, 67],
    "A minor": [57, 60, 64],
    "G7": [55, 59, 62, 65],
    "Cmaj7": [60, 64, 67, 71],
    "Dm7": [62, 65, 69, 72],
    "E5 power": [52, 59],
    "Dsus4": [62, 67, 69],
    "F#dim": [54, 57, 60],
    "Cmaj7+9 (subset)": [60, 64, 67, 71, 62],
    "single note": [60],
    "noise pair (m2)": [60, 61],
    "C9": [60, 64, 67, 70, 62],
}
for label, midis in cases.items():
    print(f"{label:<22} {midis} -> {name_chord(midis)}")
