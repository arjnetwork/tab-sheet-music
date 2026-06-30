# Tab & Sheet Music Generator

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A **local-first** web app that turns audio into playable notation: guitar/bass tablature or piano sheet music. Upload a song (or an isolated stem), and get interactive notation with chord labels, tempo-aware playback, and downloadable MIDI — all running on your machine. No audio is sent to a cloud service.

> **Suggested GitHub repo name:** `tab-sheet-music`  
> **Suggested description:** *Local audio-to-tab and sheet music generator for guitar, bass, and piano (Demucs + basic-pitch).*

## Features

- **Guitar, bass, and piano** — instrument-specific transcription ranges, tunings, and notation
- **Source separation** — optional Demucs isolation from full mixes (`htdemucs_6s` stems)
- **Stem-friendly workflow** — upload pre-separated tracks with **Use as-is** for cleaner results
- **Interactive tab** — tempo-quantized grid, measure bars, chord names, click-to-seek
- **Piano sheet music** — grand staff (treble + bass), keyboard diagram, suggested fingering
- **Playback** — sampled instruments via Web Audio (soundfont-player), with synth fallback offline
- **Manual BPM** — override auto-detected tempo for grid layout and playback speed
- **Absolute timeline** — lead-in silence preserved so guitar/bass/piano parts from the same song align
- **Run logging** — each job saved under `outputs/<job-id>/` for review and feedback

## How it works

```
audio file
   │
   ├─ (optional) Demucs        →  isolate target instrument stem
   │
   ├─ librosa                  →  detect tempo + beat origin
   │
   ├─ basic-pitch (Spotify)    →  transcribe to note events / MIDI
   │
   └─ tabify / piano           →  fretboard or staff notation + structured tabdata
```

See **[TECHNICAL.md](TECHNICAL.md)** for architecture, algorithms, API details, and data formats.

## Requirements

- **Python 3.11** (3.10–3.12 likely work)
- **FFmpeg** on your `PATH` (decodes mp3, m4a, etc.)
- **Internet** on first run (model downloads; notation fonts and soundfonts load from CDN with offline fallbacks)

## Quick start

### Windows

**Easiest (no PowerShell script policy issues):**

```cmd
cd tab-sheet-music
run.bat
```

Or double-click `run.bat` in File Explorer.

**PowerShell** (`run.ps1` may be blocked by execution policy on some PCs):

```powershell
git clone https://github.com/arjnetwork/tab-sheet-music.git
cd tab-sheet-music

# One-time setup (or let run.bat / run.ps1 create the venv)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# If .\run.ps1 fails with "running scripts is disabled", use run.bat instead, or:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\run.ps1
```

Open **http://127.0.0.1:8000**, drop in an audio file, choose options, and click **Generate Tab**.

### Manual start

```powershell
cd tab-sheet-music
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Stop with **Ctrl+C** in the terminal.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Usage

### Instrument

| Instrument | Output |
|------------|--------|
| **Guitar** | 6-string standard tuning, interactive ASCII tab |
| **Bass** | 4-string standard tuning, interactive ASCII tab |
| **Piano** | Grand-staff sheet music + keyboard diagram |

### Isolation

| Mode | When to use |
|------|-------------|
| **Auto** | Full song — separate then transcribe the target instrument |
| **Isolate** | Same as Auto (always runs separation) |
| **Use as-is** | Pre-separated stem or solo recording — skips Demucs |

### Separation quality

| Mode | Trade-off |
|------|-----------|
| **Fast** | Single Demucs pass — quicker |
| **High** | Multi-shift + band-limiting — cleaner stem, slower |

Quality only applies when separating.

### Tempo

- Leave **BPM** blank to auto-detect from the upload.
- Set a manual BPM before generate if detection feels off (e.g. double-time).
- After generate, adjust the **BPM** control in the player to fine-tune playback speed vs. detected tempo.

### Tips for better tabs

- Upload **isolated stems** when you have them (guitar, bass, keys) and choose **Use as-is**.
- Acoustic / clean sources transcribe more reliably than heavily distorted or dense mixes.
- Transcribe guitar and bass from the **same song** separately — grids align on absolute time so parts line up.
- Check `outputs/<job-id>/` for logs, MIDI, and `tabdata.json` when sharing feedback.

## Outputs

Each run writes to `outputs/<job-id>/`:

| File | Description |
|------|-------------|
| `tab.txt` | ASCII tab or piano text fallback |
| `tabdata.json` | Structured notation + playback data for the UI |
| `transcription.mid` | Raw basic-pitch MIDI |
| `run.json` | Settings, logs, metadata |
| Source audio copy | Original upload |

An index is appended to `outputs/runs.jsonl`.

## Project layout

```
backend/
  main.py         FastAPI routes + static frontend
  jobs.py         Job queue and pipeline orchestration
  separate.py     Demucs source separation
  transcribe.py   basic-pitch wrapper
  tempo.py        BPM / beat detection (librosa)
  tabify.py       Guitar/bass tab engine (internal module)
  piano.py        Piano notation engine
  chords.py       Chord name detection
frontend/
  index.html      Single-page UI
  style.css
  app.js          Tab/sheet rendering, playback, highlighting
scripts/          Smoke and unit tests
run.ps1           Windows launcher
requirements.txt
```

## Limitations

- Transcription is **approximate** — no bends, slides, palm muting, or articulation marks.
- CPU separation is slow for long tracks; first run downloads model weights (~hundreds of MB).
- Piano/guitar playback uses CDN-hosted soundfonts; offline mode falls back to a simple synth.
- Notation uses a quantized rhythmic grid; audio playback uses raw transcription timing for accuracy.

## Third-party libraries

This project uses [Demucs](https://github.com/facebookresearch/demucs), [basic-pitch](https://github.com/spotify/basic-pitch), [FastAPI](https://fastapi.tiangolo.com/), [librosa](https://librosa.org/), [VexFlow](https://www.vexflow.com/) (CDN), and [soundfont-player](https://github.com/danigb/soundfont-player) (CDN). The internal module `tabify.py` is **not** affiliated with any third-party product named Tabify or Tabtify.

## Development

```powershell
# Tab / fingering unit tests
.\.venv\Scripts\python.exe scripts\tab_build_test.py
.\.venv\Scripts\python.exe scripts\fingering_test.py

# End-to-end (server must be running)
.\.venv\Scripts\python.exe scripts\e2e_test.py
```

## License

MIT — see [LICENSE](LICENSE).

Third-party models and libraries (Demucs, basic-pitch, VexFlow, soundfont-player, etc.) remain under their respective licenses.
