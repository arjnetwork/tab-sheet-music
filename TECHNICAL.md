# Technical Reference — Tab & Sheet Music Generator

Architecture and implementation details for the Tab & Sheet Music Generator. For setup and usage, see [README.md](README.md).

---

## Architecture overview

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Frontend | Vanilla HTML / CSS / JavaScript (SPA) |
| Job execution | `ThreadPoolExecutor` (1 worker) — one heavy ML job at a time |
| Storage | In-memory job map + disk under `uploads/` and `outputs/` |
| ML inference | PyTorch CPU (Demucs), ONNX (basic-pitch) |

```
┌─────────────┐     POST /api/upload      ┌──────────────┐
│   Browser   │ ─────────────────────────►│   FastAPI    │
│  (app.js)   │◄── poll /api/status ──────│   main.py    │
└─────────────┘     GET /api/tabdata      └──────┬───────┘
                                                 │
                                          ┌──────▼───────┐
                                          │   jobs.py    │
                                          │  (pipeline)  │
                                          └──────┬───────┘
                     ┌───────────────────────────┼───────────────────────────┐
                     ▼                           ▼                           ▼
              separate.py                 transcribe.py                  tempo.py
              (Demucs)                    (basic-pitch)                  (librosa)
                     │                           │
                     └─────────────┬─────────────┘
                                   ▼
                          tabify.py  OR  piano.py
                          (+ chords.py)
                                   │
                                   ▼
                            tabdata.json
```

---

## Processing pipeline

### 1. Upload (`main.py` → `jobs.py`)

`POST /api/upload` accepts multipart form data:

| Field | Values | Default |
|-------|--------|---------|
| `file` | Audio (mp3, wav, flac, m4a, ogg, aac, wma) | required |
| `separate_mode` | `auto`, `separate`, `none` | `auto` |
| `quality` | `fast`, `high` | `fast` |
| `instrument` | `guitar`, `bass`, `piano` | `guitar` |
| `bpm` | 30–300 or empty | auto-detect |

A background thread runs `_run()` per job.

### 2. Source separation (`separate.py`)

- **Model:** Demucs `htdemucs_6s` (6 stems: drums, bass, other, vocals, guitar, piano)
- **API:** Python API (not CLI) — loads audio via librosa, writes via soundfile
- **Target:** Maps instrument to stem name + band-limiting frequency range
- **Quality:**
  - `fast`: 1 shift, overlap 0.25
  - `high`: 2 shifts, overlap 0.35, scipy band-limit filter

Skipped when `separate_mode` is `none`.

### 3. Tempo detection (`tempo.py`)

- `librosa.load` + `librosa.beat.beat_track`
- Returns `(bpm, beat_origin)` or `(None, 0.0)` on failure
- Manual BPM override stored on job; detected value preserved as `detected_bpm` in tabdata

### 4. Transcription (`transcribe.py`)

- **Model:** Spotify basic-pitch (ICASSP 2022 ONNX)
- **Output:** List of `(start, end, pitch, amplitude, bends)` note events + optional MIDI file
- **Frequency ranges** (Hz):

| Instrument | Min | Max |
|------------|-----|-----|
| Guitar | 75 | 1400 |
| Bass | 30 | 420 |
| Piano | 27 | 4300 |

### 5. Notation build

**Guitar / bass → `tabify.build_tab()`**

**Piano → `piano.build_piano()`**

Both attach chord names via `chords.name_chord()` and emit a `playback` array (faithful raw note times).

---

## `tabify.py` — guitar/bass engine

> **Note:** `tabify` is an internal module name only. It is not a dependency on or affiliation with any third-party product named Tabify or Tabtify.

### Pipeline stages

1. **`_solve()`** — MIDI pitches → string/fret assignments
2. **`_build_slots()`** — quantize to tempo grid (or keep absolute times)
3. **`chords.name_chord()`** — label each onset
4. **`render_ascii_slots()`** — classic 6-line (or 4-line bass) ASCII tab
5. **`raw_playback()`** — un-quantized note list for audio

### Tunings

```python
"guitar": open MIDI (64, 59, 55, 50, 45, 40)  →  e B G D A E
"bass":   open MIDI (43, 38, 33, 28)          →  G D A E
```

### Fingering (Viterbi dynamic programming)

For each time column (chord group):

1. **`_group_events`** — merge notes within `chord_window` (default 70 ms)
2. **`_column_voicings`** — enumerate valid (string, fret) combinations per pitch
3. **`_Voicing`** — emission cost: stretch span, neck height, frets above comfort zone (12)
4. **`_assign_voicings`** — Viterbi minimizes hand movement (`W_MOVE`) between columns

Constraints: one note per string, max comfortable reach (`MAX_REACH = 5` frets), open strings included in hand position (prevents unrealistic jumps to open strings).

### Tempo grid

When BPM is available:

- 16th-note subdivision (`subdivision = 4`, `beats_per_measure = 4`)
- Grid anchored to **absolute t = 0** with downbeat phase from `beat_origin`
- Empty slots preserve lead-in silence (multi-part alignment)
- Measure bars every 4 beats

Without BPM: one slot per solved column at absolute `start` time.

### `build_tab()` return shape

```json
{
  "kind": "tab",
  "ascii": "...",
  "slots": [
    {
      "col": 0,
      "t": 0.0,
      "frets": { "0": 5, "1": 7 },
      "midis": [69, 64],
      "chord": "A",
      "bar": true,
      "dur": 0.5
    }
  ],
  "playback": [
    { "t": 0.15, "d": 0.32, "midis": [69] }
  ],
  "labels": ["e", "B", "G", "D", "A", "E"],
  "bpm": 120.0,
  "detected_bpm": 136.0,
  "subdivision": 4,
  "beats_per_measure": 4,
  "instrument": "guitar",
  "num_notes": 42
}
```

- **`slots`** — quantized grid for UI display and highlight
- **`playback`** — every transcribed note at exact time for audio scheduling

---

## `piano.py` — piano engine

### Pipeline

1. Filter notes to piano range (MIDI 21–108, A0–C8)
2. Group near-simultaneous onsets (same 70 ms window)
3. Quantize to tempo grid (or absolute times without BPM)
4. Split at **middle C (MIDI 60)** → treble / bass staves
5. Assign fingering (1–5 per hand): chord shapes for chords, stepwise heuristic for runs
6. Attach chord names and build `playback` from raw events

### Onset shape

```json
{
  "slot": 16,
  "t": 2.0,
  "nslots": 4,
  "dur_token": "q",
  "dur": 0.5,
  "treble": [{ "midi": 60, "name": "C4", "key": "c/4", "finger": 1 }],
  "bass": [],
  "midis": [60],
  "chord": "C"
}
```

---

## `chords.py` — chord detection

Template matching on pitch-class sets:

- Triads, 7ths, sus, dim, aug, 6, 9, power chords
- Slash chords when bass note ≠ root (`C/E`)
- Subset fallback for extra transcription noise
- Returns `null` when no confident match (UI omits label)

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | SPA (`index.html`) |
| `GET` | `/static/*` | CSS, JS, assets |
| `POST` | `/api/upload` | Start job → `{ job_id }` |
| `GET` | `/api/status/{job_id}` | Progress, logs, metadata |
| `GET` | `/api/tab/{job_id}` | Download ASCII `.txt` |
| `GET` | `/api/tabdata/{job_id}` | Structured JSON |
| `GET` | `/api/midi/{job_id}` | Download transcription `.mid` |

### Job status fields

`status`: `queued` → `separating` → `transcribing` → `tabbing` → `done` | `error`

---

## Frontend (`app.js`)

### Rendering

| `kind` | Visual |
|--------|--------|
| `tab` | Flex grid: chord lane, string labels, fret columns, measure bars |
| `piano` | VexFlow 4.2.2 grand staff + custom keyboard diagram |

CDN scripts: VexFlow, soundfont-player. Offline fallbacks: text notation, Karplus-Strong synth.

### Playback architecture

Two timing tracks:

| Track | Source | Purpose |
|-------|--------|---------|
| `audioNotes` | `tabdata.playback` | Sound scheduling at raw transcription times |
| `playbackNotes` | `tabdata.slots` / `onsets` | Visual highlight + seek targets |

**Look-ahead scheduler:** queues ~0.5 s of notes every 25 ms (avoids flooding Web Audio on long tracks).

**Instruments (GM soundfonts):**

| Instrument | Soundfont name |
|------------|----------------|
| Guitar | `acoustic_guitar_steel` |
| Bass | `electric_bass_finger` |
| Piano | `acoustic_grand_piano` |

Loads only note names used in the song (flat naming: `Db4`, etc.).

**BPM playback scaling:** `playbackTempo = detected_bpm / user_bpm` applied to scheduler and progress bar.

**AudioContext:** created on Generate click (user gesture) to satisfy browser autoplay policy.

---

## Persistent logging

Each completed job writes `outputs/<job-id>/`:

```
outputs/<job-id>/
  <original-filename>     # copy of upload
  tab.txt
  tabdata.json
  transcription.mid
  run.json                # settings, logs, file manifest
outputs/runs.jsonl        # one-line index per run
```

---

## Dependencies

| Package | Role |
|---------|------|
| `torch`, `torchaudio` | Demucs inference (CPU wheels) |
| `demucs` | Source separation |
| `basic-pitch`, `onnxruntime` | Audio → MIDI |
| `librosa` | Load, tempo, beat tracking |
| `soundfile` | WAV I/O |
| `pretty_midi` | MIDI read/write |
| `scipy` | Band-limiting filter (separation) |
| `fastapi`, `uvicorn`, `python-multipart` | Web server |
| VexFlow (CDN) | Sheet music rendering |
| soundfont-player (CDN) | Sampled instrument playback |

---

## Test scripts

| Script | Purpose |
|--------|---------|
| `scripts/smoke_test.py` | Quick tabify + transcription check |
| `scripts/fingering_test.py` | Viterbi fingering scenarios |
| `scripts/tab_build_test.py` | `build_tab` for guitar/bass with/without BPM |
| `scripts/piano_test.py` | Piano analysis unit test |
| `scripts/chord_test.py` | Chord detector cases |
| `scripts/e2e_test.py` | HTTP upload + poll against running server |
| `scripts/piano_e2e.py` | Piano pipeline end-to-end |
| `scripts/playback_check.py` | Raw vs quantized note counts |

---

## Known design trade-offs

| Area | Choice | Rationale |
|------|--------|-----------|
| Notation timing | Quantized grid | Readable tab/sheet with measure bars |
| Audio timing | Raw transcription | Avoids merging fast runs into chords |
| Separation | CPU-only default | No GPU requirement; slower but portable |
| Job queue | Single worker | Prevents concurrent Demucs from thrashing CPU |
| CDN assets | VexFlow + soundfonts | Quality notation/audio; synth/text fallback offline |
| Absolute timeline | Grid from t=0 | Align guitar/bass/piano parts from same song |
