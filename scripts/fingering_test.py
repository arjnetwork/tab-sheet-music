"""Check that the fingering stays in a playable hand position."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import tabify  # noqa: E402

OPEN = tabify.OPEN_MIDI


def analyze(name, pitches):
    events = [(i * 0.5, i * 0.5 + 0.4, p) for i, p in enumerate(pitches)]
    cols = tabify.build_columns(events)
    tab = tabify.render_ascii(cols)
    print(f"=== {name} ===")
    print(tab)
    # Report the largest fret jump between consecutive single notes.
    seq = []
    for c in cols:
        allf = list(c.values())
        if allf:
            seq.append(sum(allf) / len(allf))
    jumps = [abs(b - a) for a, b in zip(seq, seq[1:])]
    print(f"max hand jump between columns: {max(jumps):.1f} frets" if jumps else "n/a")
    print()


# A line centred high on the neck (around C5/D5) with a low E4 dropped in.
# Old behaviour: E4 -> open high-e (fret 0), an ~11-fret jump.
analyze("high line + low note", [72, 74, 76, 64, 76, 74, 72])

# Pure descending scale.
analyze("descending scale", [76, 74, 72, 71, 69, 67, 65, 64])

# A C major chord then an E note.
analyze("chord then note", [60, 64, 67] + [None] if False else [60, 64, 67])
