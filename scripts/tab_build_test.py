"""Unit-check build_tab: guitar grid w/ tempo, and bass tuning."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import tabify  # noqa: E402

# A simple quarter-note line at 120 BPM (beat = 0.5s) -> 16th slot = 0.125s.
# Notes on beats: t=0,0.5,1.0,1.5,2.0 ...
pitches = [64, 67, 69, 71, 72, 71, 69, 67]
events = [(i * 0.5, i * 0.5 + 0.45, p) for i, p in enumerate(pitches)]

print("=== GUITAR @120BPM (quantized, measure bars) ===")
g = tabify.build_tab(events, "guitar", bpm=120.0, beat_origin=0.0)
print("bpm:", g["bpm"], "labels:", g["labels"], "notes:", g["num_notes"])
print(g["ascii"])
onset = [s for s in g["slots"] if s["frets"]]
print("first onset slots:", [(s["col"], s["t"], s["frets"], s.get("midis")) for s in onset[:3]])

print("\n=== BASS @120BPM ===")
b = tabify.build_tab(events, "bass", bpm=120.0, beat_origin=0.0)
print("labels:", b["labels"], "notes:", b["num_notes"])
print(b["ascii"])

print("\n=== GUITAR no tempo (fallback) ===")
n = tabify.build_tab(events, "guitar", bpm=None)
print(n["ascii"])
print("bars present:", any(s["bar"] for s in n["slots"]))
