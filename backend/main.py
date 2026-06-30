"""FastAPI app: upload audio, run the pipeline, serve the tab and the UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import jobs

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

ALLOWED_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}

app = FastAPI(
    title="Tab & Sheet Music Generator",
    description="Local audio-to-tab and sheet music for guitar, bass, and piano.",
)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    separate_mode: str = Form("auto"),
    quality: str = Form("fast"),
    instrument: str = Form("guitar"),
    bpm: str = Form(""),
) -> JSONResponse:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXT))}",
        )
    if separate_mode not in ("auto", "separate", "none"):
        separate_mode = "auto"
    if quality not in ("fast", "high"):
        quality = "fast"
    if instrument not in ("guitar", "bass", "piano"):
        instrument = "guitar"

    bpm_override = None
    if bpm.strip():
        try:
            val = float(bpm.strip())
            if 30.0 <= val <= 300.0:
                bpm_override = val
        except ValueError:
            pass

    job = jobs.store.create(
        file.filename or f"upload{ext}", separate_mode, quality, instrument, bpm_override
    )
    job_dir = jobs.UPLOAD_DIR / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    saved = job_dir / f"input{ext}"

    data = await file.read()
    saved.write_bytes(data)

    jobs.submit(job, saved)
    return JSONResponse({"job_id": job.id})


@app.get("/api/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = jobs.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(job.to_dict())


@app.get("/api/tab/{job_id}")
def download_tab(job_id: str) -> PlainTextResponse:
    job = jobs.store.get(job_id)
    if job is None or job.tab is None:
        raise HTTPException(status_code=404, detail="Tab not ready")
    return PlainTextResponse(
        job.tab,
        headers={"Content-Disposition": f'attachment; filename="tab_{job_id}.txt"'},
    )


@app.get("/api/tabdata/{job_id}")
def tab_data(job_id: str) -> JSONResponse:
    job = jobs.store.get(job_id)
    if job is None or job.tabdata is None:
        raise HTTPException(status_code=404, detail="Tab data not ready")
    return JSONResponse(job.tabdata)


@app.get("/api/midi/{job_id}")
def download_midi(job_id: str) -> FileResponse:
    job = jobs.store.get(job_id)
    if job is None or not job.midi_path:
        raise HTTPException(status_code=404, detail="MIDI not ready")
    return FileResponse(
        job.midi_path,
        media_type="audio/midi",
        filename=f"transcription_{job_id}.mid",
    )


# Serve any other static assets (css/js) from the frontend directory.
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
