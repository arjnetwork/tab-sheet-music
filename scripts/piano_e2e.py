"""Synthesize a short piano-ish clip and run it through the live server as piano."""
import sys
import time
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

BASE = "http://127.0.0.1:8000"
sr = 22050


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tone(midi, dur, amp=0.3):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    # a few harmonics + quick decay -> vaguely piano-like
    env = np.exp(-3.0 * t)
    sig = sum((1.0 / k) * np.sin(2 * np.pi * midi_hz(midi) * k * t) for k in (1, 2, 3))
    return amp * env * sig


def main():
    seq = [
        (0.0, 0.9, [48, 60, 64, 67]),   # C major (LH C3 + RH triad)
        (1.0, 0.45, [72]),
        (1.5, 0.45, [74]),
        (2.0, 0.45, [76]),
        (2.5, 0.9, [43, 67, 71, 74]),   # G7-ish
    ]
    total = 3.6
    audio = np.zeros(int(sr * total))
    for start, dur, notes in seq:
        seg = sum(tone(n, dur) for n in notes)
        i = int(sr * start)
        audio[i:i + len(seg)] += seg[: len(audio) - i]
    audio /= np.max(np.abs(audio)) + 1e-9

    out = Path(__file__).resolve().parent.parent / "outputs" / "_pno_test.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, audio.astype("float32"), sr)
    print("wrote", out)

    with open(out, "rb") as f:
        r = requests.post(
            f"{BASE}/api/upload",
            files={"file": ("piano.wav", f, "audio/wav")},
            data={"separate_mode": "none", "quality": "fast", "instrument": "piano"},
        )
    jid = r.json()["job_id"]
    print("job", jid)

    s = {}
    last = ""
    for _ in range(120):
        s = requests.get(f"{BASE}/api/status/{jid}").json()
        if s["message"] != last:
            print(f"[{s['progress']}%] {s['status']}: {s['message']}")
            last = s["message"]
        if s["status"] in ("done", "error"):
            break
        time.sleep(1.0)

    print("FINAL:", s["status"], "| bpm:", s.get("bpm"), "| instrument:", s.get("instrument"),
          "| has_tabdata:", s.get("has_tabdata"))
    if s["status"] != "done":
        print(s.get("error"))
        return
    d = requests.get(f"{BASE}/api/tabdata/{jid}").json()
    print("kind:", d.get("kind"), "| subdivision:", d.get("subdivision"),
          "| beats/measure:", d.get("beats_per_measure"), "| total_slots:", d.get("total_slots"),
          "| onsets:", len(d.get("onsets", [])))
    for o in d.get("onsets", [])[:6]:
        rh = ", ".join(f"{n['key']}f{n['finger']}" for n in o["treble"])
        lh = ", ".join(f"{n['key']}f{n['finger']}" for n in o["bass"])
        print(f"  slot {o['slot']:>2} t={o['t']} {o['dur_token']:<3} RH[{rh}] LH[{lh}]")


if __name__ == "__main__":
    main()
