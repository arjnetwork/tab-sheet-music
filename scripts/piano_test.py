"""Check piano analysis: hand split, fingering, durations, names."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import piano  # noqa: E402

# Left-hand C2 + a right-hand C-major triad, then a RH melodic run.
events = [
    (0.0, 1.0, 36),               # C2 (LH)
    (0.0, 1.0, 60),               # C4
    (0.0, 1.0, 64),               # E4
    (0.0, 1.0, 67),               # G4
    (1.0, 1.5, 43),               # G2 (LH)
    (1.0, 1.5, 72),               # C5 (RH melody)
    (1.5, 2.0, 74),               # D5
    (2.0, 2.5, 76),               # E5
    (2.5, 3.0, 77),               # F5
]
data = piano.build_piano(events, bpm=120.0, beat_origin=0.0)
print("kind:", data["kind"], "| bpm:", data["bpm"], "| notes:", data["num_notes"],
      "| total_slots:", data["total_slots"])
for o in data["onsets"]:
    rh = ", ".join(f"{n['key']} f{n['finger']}" for n in o["treble"])
    lh = ", ".join(f"{n['key']} f{n['finger']}" for n in o["bass"])
    print(f"slot {o['slot']:>2} t={o['t']:<5} {o['dur_token']:<3} RH[{rh}] LH[{lh}]")
print("\n--- ascii ---")
print(data["ascii"])
