"""In-memory job store and the background processing pipeline.

A job goes through: queued -> separating (optional) -> transcribing ->
tabbing -> done (or error). Work runs on a single background worker thread
so the heavy ML steps don't contend for CPU.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import piano, separate, tabify, tempo, transcribe

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Separation steps are heavy; one at a time keeps things responsive.
_executor = ThreadPoolExecutor(max_workers=1)


@dataclass
class Job:
    id: str
    filename: str
    separate_mode: str  # "auto" | "separate" | "none"
    quality: str = "fast"  # "fast" | "high"
    instrument: str = "guitar"  # "guitar" | "bass" | "piano"
    bpm_override: float | None = None
    status: str = "queued"
    progress: int = 0
    message: str = "Queued"
    logs: list[str] = field(default_factory=list)
    tab: str | None = None
    num_columns: int = 0
    tabdata: dict | None = None
    midi_path: str | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "separate_mode": self.separate_mode,
            "instrument": self.instrument,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "logs": self.logs[-50:],
            "tab": self.tab,
            "num_columns": self.num_columns,
            "bpm": self.tabdata.get("bpm") if self.tabdata else None,
            "detected_bpm": self.tabdata.get("detected_bpm") if self.tabdata else None,
            "has_tabdata": self.tabdata is not None,
            "has_midi": self.midi_path is not None,
            "error": self.error,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(
        self,
        filename: str,
        separate_mode: str,
        quality: str = "fast",
        instrument: str = "guitar",
        bpm_override: float | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            filename=filename,
            separate_mode=separate_mode,
            quality=quality,
            instrument=instrument,
            bpm_override=bpm_override,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)


store = JobStore()


def _set(job: Job, *, status=None, progress=None, message=None):
    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = progress
    if message is not None:
        job.message = message
        job.logs.append(message)


def submit(job: Job, saved_path: Path) -> None:
    _executor.submit(_run, job, saved_path)


def _write_record(job: Job, work: Path, saved_path: Path, status: str) -> None:
    """Persist a self-contained record of the run for later review/feedback."""
    import json
    import shutil
    from datetime import datetime

    try:
        work.mkdir(parents=True, exist_ok=True)

        # Keep a copy of the original audio in the run folder under its real name.
        src_name = Path(job.filename).name or f"source{saved_path.suffix}"
        dest = work / src_name
        if saved_path.exists() and not dest.exists():
            try:
                shutil.copy2(saved_path, dest)
            except Exception:  # noqa: BLE001
                pass

        if job.tabdata is not None:
            (work / "tabdata.json").write_text(
                json.dumps(job.tabdata), encoding="utf-8"
            )

        record = {
            "id": job.id,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "original_filename": job.filename,
            "instrument": job.instrument,
            "separate_mode": job.separate_mode,
            "quality": job.quality,
            "bpm": job.tabdata.get("bpm") if job.tabdata else None,
            "num_notes": job.num_columns,
            "status": status,
            "error": job.error,
            "files": {
                "source_audio": src_name,
                "tab": "tab.txt",
                "midi": "transcription.mid",
                "tabdata": "tabdata.json",
            },
            "logs": job.logs,
        }
        (work / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

        # Append a one-line index entry so all runs are easy to scan.
        index = {
            "saved_at": record["saved_at"],
            "id": job.id,
            "file": job.filename,
            "instrument": job.instrument,
            "mode": job.separate_mode,
            "quality": job.quality,
            "bpm": record["bpm"],
            "status": status,
            "folder": str(work),
        }
        with open(OUTPUT_DIR / "runs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(index) + "\n")
    except Exception as exc:  # noqa: BLE001
        job.logs.append(f"(could not write run record: {exc})")


def _run(job: Job, saved_path: Path) -> None:
    def log(msg: str) -> None:
        job.logs.append(str(msg))

    work = OUTPUT_DIR / job.id
    work.mkdir(parents=True, exist_ok=True)

    try:
        audio_for_transcription = saved_path
        instrument = job.instrument

        do_separate = job.separate_mode in ("auto", "separate")
        if do_separate:
            q = "high quality" if job.quality == "high" else "fast"
            _set(job, status="separating", progress=10,
                 message=f"Isolating the {instrument} from the mix (Demucs, {q})...")
            stem = separate.isolate_stem(
                saved_path, work / "stems", target=instrument, quality=job.quality, log=log
            )
            audio_for_transcription = stem
            _set(job, progress=50, message=f"{instrument.title()} isolated.")
        else:
            _set(job, progress=20, message="Using uploaded audio as-is (no separation).")

        # Tempo from the original upload (full mixes give the most reliable beat).
        _set(job, progress=55, message="Detecting tempo...")
        detected_bpm, beat_origin = tempo.detect_tempo(saved_path, log=log)
        if job.bpm_override is not None:
            bpm = job.bpm_override
            if detected_bpm:
                log(f"Using manual BPM {bpm:.1f} (detected ~{detected_bpm:.1f})")
            else:
                log(f"Using manual BPM {bpm:.1f}")
        else:
            bpm = detected_bpm

        _set(job, status="transcribing", progress=62,
             message="Transcribing notes (basic-pitch)...")
        midi_path = work / "transcription.mid"
        note_events = transcribe.transcribe(
            audio_for_transcription, instrument=instrument, midi_out=midi_path, log=log
        )
        if midi_path.exists():
            job.midi_path = str(midi_path)

        if instrument == "piano":
            _set(job, status="tabbing", progress=88, message="Building piano notation...")
            data = piano.build_piano(note_events, bpm=bpm, beat_origin=beat_origin)
        else:
            _set(job, status="tabbing", progress=88,
                 message=f"Building {instrument} tab...")
            data = tabify.build_tab(
                note_events, instrument=instrument, bpm=bpm, beat_origin=beat_origin
            )
        if detected_bpm:
            data["detected_bpm"] = round(detected_bpm, 1)
        job.tabdata = data
        job.tab = data["ascii"]
        job.num_columns = data["num_notes"]

        tab_file = work / "tab.txt"
        tab_file.write_text(data["ascii"], encoding="utf-8")

        bpm_txt = f" at ~{data['bpm']} BPM" if data["bpm"] else ""
        _set(job, status="done", progress=100,
             message=f"Done. {data['num_notes']} notes{bpm_txt}.")
        _write_record(job, work, saved_path, "done")
        log(f"Run saved to {work}")
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        job.error = f"{type(exc).__name__}: {exc}"
        job.logs.append(job.error)
        job.logs.append(traceback.format_exc())
        _set(job, status="error", progress=100, message=f"Failed: {job.error}")
        _write_record(job, work, saved_path, "error")
