"""Piano analysis: quantized onsets split across treble/bass staves, with
note names and suggested left/right-hand fingering for sheet-music + keyboard
display. Mirrors the timing/quantization approach used for tab.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from . import chords

PIANO_LO, PIANO_HI = 21, 108           # A0 .. C8
MIDDLE_C = 60                          # split point between hands (C4)
NOTE_NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]
DISPLAY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Finger assignments for an n-note chord (right hand, low->high). Left hand is
# the mirror (reversed), so the lowest note gets the pinky.
_RH_CHORD = {1: [1], 2: [1, 5], 3: [1, 3, 5], 4: [1, 2, 3, 5], 5: [1, 2, 3, 4, 5]}


def midi_to_vexkey(m: int) -> str:
    """MIDI -> VexFlow key, e.g. 60 -> 'c/4'."""
    return f"{NOTE_NAMES[m % 12]}/{m // 12 - 1}"


def midi_to_name(m: int) -> str:
    return f"{DISPLAY_NAMES[m % 12]}{m // 12 - 1}"


def _chord_fingers(n: int, hand: str) -> list[int]:
    base = _RH_CHORD.get(n) or ([1, 2, 3, 4, 5] + [5] * (n - 5))[:n]
    return list(reversed(base)) if hand == "L" else base


def _assign_fingering(onsets: list[dict]) -> None:
    """Fill a 'finger' on every note. Chords use a fixed shape; single notes
    use a light stepwise heuristic so runs walk the fingers sensibly.
    """
    state = {"R": {"f": None, "p": None}, "L": {"f": None, "p": None}}

    for onset in onsets:
        for hand, key in (("R", "treble"), ("L", "bass")):
            notes = onset[key]  # already sorted ascending by midi
            if not notes:
                continue
            if len(notes) > 1:
                fingers = _chord_fingers(len(notes), hand)
                for note, f in zip(notes, fingers):
                    note["finger"] = f
                # Anchor melodic state to the outer voice of the chord.
                top = notes[-1] if hand == "R" else notes[0]
                state[hand]["p"] = top["midi"]
                state[hand]["f"] = top["finger"]
                continue

            note = notes[0]
            st = state[hand]
            p = note["midi"]
            if st["p"] is None:
                f = 1 if hand == "R" else 5
            else:
                d = p - st["p"]
                if abs(d) > 4:  # leap -> reset toward the thumb side of travel
                    f = (1 if d > 0 else 5) if hand == "R" else (5 if d > 0 else 1)
                elif d == 0:
                    f = st["f"]
                else:
                    up = d > 0
                    step = 1 if (up == (hand == "R")) else -1
                    f = st["f"] + step
            f = max(1, min(5, f))
            note["finger"] = f
            st["p"] = p
            st["f"] = f


def _slots_to_duration(nslots: int, subdivision: int) -> str:
    """Map a span in grid-slots to a VexFlow duration token (16th grid)."""
    # nslots is counted in 1/subdivision-of-a-beat units; with subdivision=4
    # one beat = 4 slots (a quarter note).
    table = {
        1: "16", 2: "8", 3: "8d", 4: "q", 6: "qd",
        8: "h", 12: "hd", 16: "w",
    }
    if nslots in table:
        return table[nslots]
    # Fall back to the largest token that fits.
    for n in (16, 12, 8, 6, 4, 3, 2, 1):
        if nslots >= n:
            return table[n]
    return "q"


def build_piano(
    events: Iterable[Sequence],
    bpm: float | None = None,
    beat_origin: float = 0.0,
    subdivision: int = 4,
    beats_per_measure: int = 4,
    chord_window: float = 0.07,
    min_duration: float = 0.12,
) -> dict:
    notes = sorted(
        (
            (float(e[0]), float(e[1]), int(e[2]))
            for e in events
            if PIANO_LO <= int(e[2]) <= PIANO_HI
        ),
        key=lambda x: (x[0], x[2]),
    )

    # Group near-simultaneous onsets.
    groups: list[dict] = []
    cur: dict | None = None
    for start, end, pitch in notes:
        if cur is None or start - cur["start"] > chord_window:
            cur = {"start": start, "end": end, "pitches": [pitch]}
            groups.append(cur)
        else:
            cur["pitches"].append(pitch)
            cur["end"] = max(cur["end"], end)

    measure_len = subdivision * beats_per_measure
    onsets: list[dict] = []

    def make_onset(slot, t, nslots, dur, pitches):
        pitches = sorted(set(pitches))
        treble = [
            {"midi": p, "name": midi_to_name(p), "key": midi_to_vexkey(p), "finger": 0}
            for p in pitches if p >= MIDDLE_C
        ]
        bass = [
            {"midi": p, "name": midi_to_name(p), "key": midi_to_vexkey(p), "finger": 0}
            for p in pitches if p < MIDDLE_C
        ]
        return {
            "slot": slot,
            "t": round(t, 4),
            "nslots": nslots,
            "dur_token": _slots_to_duration(nslots, subdivision),
            "dur": round(dur, 4),
            "treble": treble,
            "bass": bass,
            "midis": pitches,
            "chord": None,  # populated in a later pass / phase
        }

    if bpm and bpm > 0 and groups:
        slot_dur = 60.0 / bpm / subdivision
        measure_dur = measure_len * slot_dur
        # Anchor to absolute t=0 (keeping the downbeat phase) so lead-in
        # silence is preserved and parts line up across instruments.
        origin = (
            beat_origin - math.floor(beat_origin / measure_dur) * measure_dur
            if measure_dur > 0
            else 0.0
        )
        merged: dict[int, dict] = {}
        for g in groups:
            s = max(0, round((g["start"] - origin) / slot_dur))
            m = merged.setdefault(s, {"pitches": set(), "end": g["end"]})
            m["pitches"].update(g["pitches"])
            m["end"] = max(m["end"], g["end"])
        onset_slots = sorted(merged)
        for i, s in enumerate(onset_slots):
            nxt = onset_slots[i + 1] if i + 1 < len(onset_slots) else s + subdivision
            nslots = max(1, nxt - s)
            onsets.append(
                make_onset(s, origin + s * slot_dur, nslots, nslots * slot_dur, merged[s]["pitches"])
            )
        last = onset_slots[-1]
        total_slots = (last // measure_len + 1) * measure_len
    else:
        for i, g in enumerate(groups):
            dur = max(min_duration, g["end"] - g["start"])
            onsets.append(
                make_onset(i * subdivision, g["start"], subdivision, dur, g["pitches"])
            )
        total_slots = len(groups) * subdivision

    for o in onsets:
        o["chord"] = chords.name_chord(o["midis"])

    _assign_fingering(onsets)
    ascii_text = _render_text(onsets, measure_len, subdivision, bpm)

    # Faithful playback: every transcribed note at its real onset/duration,
    # so fast passages aren't merged into chords or rushed by the grid.
    playback = [
        {"t": round(max(0.0, s), 4), "d": round(max(0.05, e - s), 4), "midis": [p]}
        for (s, e, p) in notes
    ]

    return {
        "kind": "piano",
        "instrument": "piano",
        "ascii": ascii_text,
        "onsets": onsets,
        "playback": playback,
        "bpm": round(bpm, 1) if bpm else None,
        "subdivision": subdivision,
        "beats_per_measure": beats_per_measure,
        "total_slots": total_slots,
        "num_notes": len(onsets),
        "labels": [],
    }


def _render_text(onsets, measure_len, subdivision, bpm) -> str:
    """A readable text fallback (used for the .txt download / offline view)."""
    if not onsets:
        return "(no notes detected)"
    header = f"Piano transcription{f' (~{round(bpm,1)} BPM)' if bpm else ''}\n"
    lines = [header]
    cur_measure = -1
    for o in onsets:
        measure = o["slot"] // measure_len + 1
        if measure != cur_measure:
            lines.append(f"\n-- Measure {measure} --")
            cur_measure = measure
        rh = " ".join(f"{n['name']}({n['finger']})" for n in o["treble"]) or "—"
        lh = " ".join(f"{n['name']}({n['finger']})" for n in o["bass"]) or "—"
        chord = f"  [{o['chord']}]" if o.get("chord") else ""
        lines.append(f"  RH: {rh:<28}  LH: {lh}{chord}")
    return "\n".join(lines)
