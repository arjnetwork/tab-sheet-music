"""Convert transcribed note events into guitar/bass tablature.

Pipeline:
  events -> group near-simultaneous onsets into columns
         -> assign playable string/fret positions (Viterbi over the neck)
         -> (optional) quantize onsets to a tempo grid with measure bars
         -> render ASCII tab + structured "slots" for the interactive UI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Iterable, Sequence

from . import chords


# --------------------------------------------------------------------------- #
# Tunings
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Tuning:
    # Open-string MIDI notes ordered from the top tab line to the bottom.
    open_midi: tuple[int, ...]
    labels: tuple[str, ...]

    @property
    def n(self) -> int:
        return len(self.open_midi)

    @property
    def lowest(self) -> int:
        return min(self.open_midi)


TUNINGS: dict[str, Tuning] = {
    # Standard 6-string guitar, high-e to low-E.
    "guitar": Tuning((64, 59, 55, 50, 45, 40), ("e", "B", "G", "D", "A", "E")),
    # Standard 4-string bass, G to E (E1=28).
    "bass": Tuning((43, 38, 33, 28), ("G", "D", "A", "E")),
}


def get_tuning(name: str) -> Tuning:
    return TUNINGS.get(name, TUNINGS["guitar"])


# Backwards-compatible module constants (default guitar) used by helper scripts.
OPEN_MIDI = list(TUNINGS["guitar"].open_midi)
STRING_LABELS = list(TUNINGS["guitar"].labels)
NUM_STRINGS = len(OPEN_MIDI)


# --------------------------------------------------------------------------- #
# Fingering search (Viterbi over the fretboard)
# --------------------------------------------------------------------------- #
MAX_REACH = 5          # comfortable hand span (frets) within one position
W_MOVE = 1.0           # cost of moving the hand between notes (dominant)
W_SPAN = 6.0           # cost of stretch inside a chord
W_HEIGHT = 0.05        # gentle preference for lower neck
W_HIGH = 0.4           # extra penalty per fret above the comfortable region
COMFORT_FRET = 12
MAX_VOICINGS = 48


@dataclass
class NoteEvent:
    start: float
    end: float
    pitch: int


def _coerce_events(events: Iterable[Sequence]) -> list[NoteEvent]:
    out: list[NoteEvent] = []
    for ev in events:
        out.append(NoteEvent(float(ev[0]), float(ev[1]), int(ev[2])))
    return out


def raw_playback(events: Iterable[Sequence], min_dur: float = 0.05) -> list[dict]:
    """Faithful, un-quantized playback: every transcribed note at its exact
    time. Used for audio so fast runs aren't merged/rushed by the grid that the
    notation/tab uses."""
    notes = sorted(_coerce_events(events), key=lambda n: (n.start, n.pitch))
    return [
        {
            "t": round(max(0.0, n.start), 4),
            "d": round(max(min_dur, n.end - n.start), 4),
            "midis": [n.pitch],
        }
        for n in notes
    ]


def _fit_to_range(pitch: int, tuning: Tuning, max_fret: int) -> int | None:
    highest = max(tuning.open_midi) + max_fret
    p = pitch
    while p < tuning.lowest:
        p += 12
    while p > highest:
        p -= 12
    return p if tuning.lowest <= p <= highest else None


def _candidate_positions(pitch: int, tuning: Tuning, max_fret: int) -> list[tuple[int, int]]:
    out = []
    for s, om in enumerate(tuning.open_midi):
        fret = pitch - om
        if 0 <= fret <= max_fret:
            out.append((s, fret))
    return out


class _Voicing:
    __slots__ = ("frets", "position", "emission")

    def __init__(self, frets: dict[int, int]):
        self.frets = frets
        all_frets = list(frets.values())
        fretted = [f for f in all_frets if f > 0]
        self.position = sum(all_frets) / len(all_frets) if all_frets else 0.0
        span = (max(fretted) - min(fretted)) if fretted else 0
        height = (sum(fretted) / len(fretted)) if fretted else 0
        high = max(0.0, height - COMFORT_FRET)
        self.emission = span * W_SPAN + height * W_HEIGHT + high * W_HIGH


def _product_size(options: list[list]) -> int:
    n = 1
    for o in options:
        n *= len(o)
        if n > 1_000_000:
            break
    return n


def _column_voicings(pitches: list[int], tuning: Tuning, max_fret: int) -> list[_Voicing]:
    uniq: list[int] = []
    for p in pitches:
        if p not in uniq:
            uniq.append(p)
    uniq = uniq[: tuning.n]

    options = [_candidate_positions(p, tuning, max_fret) for p in uniq]
    options = [o for o in options if o]
    if not options:
        return []

    while _product_size(options) > 4096:
        options = [o[: max(1, len(o) - 1)] for o in options]

    voicings: list[_Voicing] = []
    for combo in product(*options):
        strings = [s for s, _ in combo]
        if len(set(strings)) != len(strings):
            continue
        fretted = [f for _, f in combo if f > 0]
        if fretted and (max(fretted) - min(fretted)) > MAX_REACH:
            continue
        voicings.append(_Voicing({s: f for s, f in combo}))

    if not voicings:
        for combo in product(*options):
            strings = [s for s, _ in combo]
            if len(set(strings)) == len(strings):
                voicings.append(_Voicing({s: f for s, f in combo}))

    voicings.sort(key=lambda v: v.emission)
    return voicings[:MAX_VOICINGS]


def _move_cost(prev: _Voicing, cur: _Voicing) -> float:
    return abs(cur.position - prev.position) * W_MOVE


def _assign_voicings(columns: list[list[_Voicing]]) -> list[_Voicing]:
    if not columns:
        return []
    prev_costs = [v.emission for v in columns[0]]
    backptrs: list[list[int]] = [[-1] * len(columns[0])]
    for i in range(1, len(columns)):
        cur = columns[i]
        costs = [0.0] * len(cur)
        back = [0] * len(cur)
        for j, v in enumerate(cur):
            best_k, best_c = 0, float("inf")
            for k, pv in enumerate(columns[i - 1]):
                c = prev_costs[k] + _move_cost(pv, v)
                if c < best_c:
                    best_c, best_k = c, k
            costs[j] = best_c + v.emission
            back[j] = best_k
        prev_costs = costs
        backptrs.append(back)

    j = min(range(len(prev_costs)), key=lambda x: prev_costs[x])
    chosen_idx = [0] * len(columns)
    for i in range(len(columns) - 1, -1, -1):
        chosen_idx[i] = j
        j = backptrs[i][j]
    return [columns[i][chosen_idx[i]] for i in range(len(columns))]


# --------------------------------------------------------------------------- #
# Grouping + solving
# --------------------------------------------------------------------------- #
def _group_events(events, tuning: Tuning, chord_window: float, max_fret: int) -> list[dict]:
    notes = _coerce_events(events)
    notes.sort(key=lambda n: (n.start, n.pitch))
    groups: list[dict] = []
    current: dict | None = None
    for n in notes:
        fitted = _fit_to_range(n.pitch, tuning, max_fret)
        if fitted is None:
            continue
        if current is None or n.start - current["start"] > chord_window:
            current = {"start": n.start, "end": n.end, "pitches": [fitted]}
            groups.append(current)
        else:
            current["pitches"].append(fitted)
            current["end"] = max(current["end"], n.end)
    return groups


def _solve(events, tuning: Tuning, chord_window: float, max_fret: int) -> list[dict]:
    groups = _group_events(events, tuning, chord_window, max_fret)
    indexed = [(g, _column_voicings(g["pitches"], tuning, max_fret)) for g in groups]
    indexed = [(g, v) for g, v in indexed if v]
    if not indexed:
        return []
    chosen = _assign_voicings([v for _, v in indexed])
    return [
        {"start": g["start"], "end": g["end"], "frets": voicing.frets}
        for (g, _), voicing in zip(indexed, chosen)
    ]


def _midis(frets: dict[int, int], tuning: Tuning) -> list[int]:
    return sorted(tuning.open_midi[s] + f for s, f in frets.items())


# --------------------------------------------------------------------------- #
# Slots (tempo-quantized or raw) + rendering
# --------------------------------------------------------------------------- #
def _build_slots(
    solved: list[dict],
    tuning: Tuning,
    bpm: float | None,
    beat_origin: float,
    subdivision: int,
    beats_per_measure: int,
    min_duration: float,
) -> list[dict]:
    if not solved:
        return []

    if bpm and bpm > 0:
        slot_dur = 60.0 / bpm / subdivision
        measure_len = subdivision * beats_per_measure
        measure_dur = measure_len * slot_dur

        # Anchor the grid to absolute t=0 while keeping the detected downbeat
        # phase. This preserves any lead-in silence (e.g. a guitar that doesn't
        # enter until 0:60) so separately transcribed parts line up in time.
        origin = (
            beat_origin - math.floor(beat_origin / measure_dur) * measure_dur
            if measure_dur > 0
            else 0.0
        )

        # Map each column to the nearest grid slot, merging collisions.
        merged: dict[int, dict[int, int]] = {}
        for col in solved:
            s = max(0, round((col["start"] - origin) / slot_dur))
            merged.setdefault(s, {}).update(col["frets"])

        onset_slots = sorted(merged)
        max_s = onset_slots[-1]
        slots: list[dict] = []
        for s in range(max_s + 1):
            frets = merged.get(s, {})
            slot = {
                "col": s,
                "t": round(origin + s * slot_dur, 4),
                "frets": {int(k): int(v) for k, v in frets.items()},
                "bar": (s % measure_len == 0),
            }
            if frets:
                slot["midis"] = _midis(frets, tuning)
            slots.append(slot)

        # Each onset rings until the next onset (legato), bounded sensibly.
        for i, s in enumerate(onset_slots):
            nxt = onset_slots[i + 1] if i + 1 < len(onset_slots) else max_s + 1
            slots[s]["dur"] = round(max((nxt - s) * slot_dur, slot_dur), 4)
        return slots

    # No tempo: one slot per detected column. Keep absolute onset times so a
    # lead-in is preserved on playback even without a rhythmic grid.
    slots = []
    for i, col in enumerate(solved):
        t = col["start"]
        nxt = solved[i + 1]["start"] if i + 1 < len(solved) else None
        dur = col["end"] - col["start"]
        if nxt is not None:
            dur = min(max(dur, min_duration), nxt - t)
        dur = max(dur, min_duration)
        slots.append({
            "col": i,
            "t": round(t, 4),
            "frets": {int(k): int(v) for k, v in col["frets"].items()},
            "midis": _midis(col["frets"], tuning),
            "bar": False,
            "dur": round(dur, 4),
        })
    return slots


def render_ascii_slots(
    slots: list[dict],
    tuning: Tuning,
    measures_per_line: int = 4,
    subdivision: int = 4,
    beats_per_measure: int = 4,
) -> str:
    if not slots:
        return "(no notes detected)"

    gridded = any(s.get("bar") for s in slots)
    measure_len = subdivision * beats_per_measure
    line_len = measures_per_line * measure_len if gridded else 32

    lines_out: list[str] = []
    for start in range(0, len(slots), line_len):
        block = slots[start : start + line_len]
        widths = [
            max((len(str(f)) for f in s["frets"].values()), default=1) for s in block
        ]
        rows = []
        for si in range(tuning.n):
            line = tuning.labels[si] + "|"
            for idx, (s, w) in enumerate(zip(block, widths)):
                if gridded and s.get("bar") and idx != 0:
                    line += "|"
                cell = str(s["frets"][si]).ljust(w, "-") if si in s["frets"] else "-" * w
                line += "-" + cell
            line += "-|"
            rows.append(line)
        lines_out.append("\n".join(rows))
    return "\n\n".join(lines_out)


def build_tab(
    events: Iterable[Sequence],
    instrument: str = "guitar",
    bpm: float | None = None,
    beat_origin: float = 0.0,
    subdivision: int = 4,
    beats_per_measure: int = 4,
    chord_window: float = 0.07,
    max_fret: int = 22,
    min_duration: float = 0.12,
) -> dict:
    """Full build: returns ascii, structured slots, and metadata."""
    tuning = get_tuning(instrument)
    solved = _solve(events, tuning, chord_window, max_fret)
    slots = _build_slots(
        solved, tuning, bpm, beat_origin, subdivision, beats_per_measure, min_duration
    )
    for slot in slots:
        if slot.get("midis"):
            slot["chord"] = chords.name_chord(slot["midis"])
    ascii_tab = render_ascii_slots(slots, tuning, 4, subdivision, beats_per_measure)
    num_notes = sum(1 for s in slots if s["frets"])
    return {
        "kind": "tab",
        "ascii": ascii_tab,
        "slots": slots,
        "playback": raw_playback(events),
        "labels": list(tuning.labels),
        "bpm": round(bpm, 1) if bpm else None,
        "subdivision": subdivision,
        "beats_per_measure": beats_per_measure,
        "instrument": instrument,
        "num_notes": num_notes,
    }


# --------------------------------------------------------------------------- #
# Backwards-compatible helpers (guitar default, no quantization)
# --------------------------------------------------------------------------- #
def build_columns(events, chord_window: float = 0.07, max_fret: int = 22):
    tuning = get_tuning("guitar")
    return [c["frets"] for c in _solve(events, tuning, chord_window, max_fret)]


def render_ascii(columns: list[dict[int, int]], columns_per_line: int = 16) -> str:
    slots = [{"col": i, "frets": c, "bar": False} for i, c in enumerate(columns)]
    return render_ascii_slots(slots, get_tuning("guitar"))


def events_to_tab(events, chord_window: float = 0.07, max_fret: int = 22, columns_per_line: int = 16):
    cols = build_columns(events, chord_window, max_fret)
    return render_ascii(cols), len(cols)


def build_playback(events, chord_window: float = 0.07, max_fret: int = 22, min_duration: float = 0.12):
    data = build_tab(events, "guitar", chord_window=chord_window, max_fret=max_fret, min_duration=min_duration)
    return [
        {"t": s["t"], "d": s.get("dur", min_duration), "midis": s["midis"]}
        for s in data["slots"]
        if s["frets"]
    ]
