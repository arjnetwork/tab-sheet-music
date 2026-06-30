"""End-to-end HTTP test against a running server (separation enabled)."""
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
wav = Path(__file__).resolve().parent.parent / "outputs" / "_smoke" / "melody.wav"
mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
quality = sys.argv[2] if len(sys.argv) > 2 else "fast"
instrument = sys.argv[3] if len(sys.argv) > 3 else "guitar"

with open(wav, "rb") as f:
    r = requests.post(
        f"{BASE}/api/upload",
        files={"file": ("melody.wav", f, "audio/wav")},
        data={"separate_mode": mode, "quality": quality, "instrument": instrument},
    )
jid = r.json()["job_id"]
print("job", jid, "mode", mode)

last = ""
s = {}
for _ in range(120):
    s = requests.get(f"{BASE}/api/status/{jid}").json()
    if s["message"] != last:
        print(f"[{s['progress']}%] {s['status']}: {s['message']}")
        last = s["message"]
    if s["status"] in ("done", "error"):
        break
    time.sleep(1.5)

print("FINAL:", s["status"], "| bpm:", s.get("bpm"), "| instrument:", s.get("instrument"))
print(s["tab"] if s["status"] == "done" else s["error"])
if s["status"] == "done":
    n = requests.get(f"{BASE}/api/tabdata/{jid}")
    d = n.json()
    onset = [x for x in d["slots"] if x.get("midis")]
    print("tabdata:", n.status_code, "| labels:", d["labels"],
          "| slots:", len(d["slots"]), "| notes:", len(onset),
          "| bars:", sum(1 for x in d["slots"] if x.get("bar")))
    print("first 3 onsets:", [(x["col"], x["t"], x["frets"], x.get("midis")) for x in onset[:3]])
