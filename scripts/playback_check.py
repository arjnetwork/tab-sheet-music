import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pretty_midi  # noqa: E402
from backend import piano, tabify  # noqa: E402

pm = pretty_midi.PrettyMIDI("outputs/0b466ba1f190/transcription.mid")
events = [(n.start, n.end, n.pitch) for inst in pm.instruments for n in inst.notes]
d = piano.build_piano(events, bpm=136.0, beat_origin=2.86)
print("piano onsets (visual):", len(d["onsets"]), "| playback (audio):", len(d["playback"]))
print("first 3 playback:", d["playback"][:3])

g = tabify.build_tab(events[:50], "guitar", bpm=120.0)
onset = sum(1 for s in g["slots"] if s.get("midis"))
print("guitar slots-onset:", onset, "| guitar playback:", len(g["playback"]))
