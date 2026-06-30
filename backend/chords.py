"""Lightweight chord naming from a set of MIDI notes.

Given the notes sounding at an onset, guess a chord symbol (e.g. "Cmaj7",
"Am", "G/B", "D5"). Returns None when nothing convincing matches, so callers
can simply skip labelling rather than show something wrong.
"""

from __future__ import annotations

from typing import Iterable

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Interval set (relative to root, in semitones) -> quality suffix.
# Order matters only for the subset fallback (more specific = more intervals).
_TEMPLATES: dict[frozenset[int], str] = {
    frozenset({0, 7}): "5",
    frozenset({0, 4, 7}): "",
    frozenset({0, 3, 7}): "m",
    frozenset({0, 3, 6}): "dim",
    frozenset({0, 4, 8}): "aug",
    frozenset({0, 2, 7}): "sus2",
    frozenset({0, 5, 7}): "sus4",
    frozenset({0, 4, 7, 9}): "6",
    frozenset({0, 3, 7, 9}): "m6",
    frozenset({0, 4, 7, 10}): "7",
    frozenset({0, 4, 7, 11}): "maj7",
    frozenset({0, 3, 7, 10}): "m7",
    frozenset({0, 3, 6, 10}): "m7b5",
    frozenset({0, 3, 6, 9}): "dim7",
    frozenset({0, 5, 7, 10}): "7sus4",
    frozenset({0, 2, 4, 7}): "add9",
    frozenset({0, 2, 3, 7}): "madd9",
    frozenset({0, 2, 4, 7, 10}): "9",
    frozenset({0, 2, 4, 7, 11}): "maj9",
    frozenset({0, 2, 3, 7, 10}): "m9",
}

# Lower number = preferred when several qualities tie.
_QUALITY_RANK = {
    "": 0, "m": 1, "7": 2, "maj7": 3, "m7": 4, "5": 5, "sus4": 6, "sus2": 7,
    "6": 8, "m6": 9, "dim": 10, "aug": 11, "m7b5": 12, "dim7": 13, "7sus4": 14,
    "add9": 15, "madd9": 16, "9": 17, "maj9": 18, "m9": 19,
}

# Templates sorted most-specific first, for the subset fallback.
_TEMPLATES_BY_SIZE = sorted(_TEMPLATES.items(), key=lambda kv: -len(kv[0]))


def name_chord(midis: Iterable[int]) -> str | None:
    midis = [int(m) for m in midis]
    if len(midis) < 2:
        return None
    pcs = sorted({m % 12 for m in midis})
    if len(pcs) < 2:
        return None
    bass_pc = min(midis) % 12

    # Pass 1: exact interval-set match for some rotation (root).
    best = None  # (priority_tuple, root, quality)
    for root in pcs:
        ivals = frozenset((pc - root) % 12 for pc in pcs)
        quality = _TEMPLATES.get(ivals)
        if quality is None:
            continue
        prio = (0 if root == bass_pc else 1, _QUALITY_RANK.get(quality, 99))
        if best is None or prio < best[0]:
            best = (prio, root, quality)

    if best is None and len(pcs) >= 3:
        # Pass 2: largest template that is a subset of the played notes
        # (tolerates extra tensions / transcription noise).
        for tmpl, quality in _TEMPLATES_BY_SIZE:
            if len(tmpl) < 3:
                break
            for root in pcs:
                ivals = {(pc - root) % 12 for pc in pcs}
                if tmpl <= ivals:
                    prio = (0 if root == bass_pc else 1, _QUALITY_RANK.get(quality, 99))
                    if best is None or prio < best[0]:
                        best = (prio, root, quality)
            if best is not None:
                break

    if best is None:
        return None

    _, root, quality = best
    name = NOTE_NAMES[root] + quality
    if root != bass_pc:
        name += "/" + NOTE_NAMES[bass_pc]
    return name
