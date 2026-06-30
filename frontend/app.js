const $ = (sel) => document.querySelector(sel);

const fileInput = $("#file-input");
const dropzone = $("#dropzone");
const filenameEl = $("#filename");
const generateBtn = $("#generate");

const uploadCard = $("#upload-card");
const progressCard = $("#progress-card");
const resultCard = $("#result-card");
const errorCard = $("#error-card");

const statusText = $("#status-text");
const barFill = $("#bar-fill");
const logOutput = $("#log-output");
const tabOutput = $("#tab-output");
const sheetEl = $("#sheet");
const keyboardWrap = $("#keyboard-wrap");
const keyboardEl = $("#keyboard");
const errorOutput = $("#error-output");

let selectedFile = null;
let pollTimer = null;

function show(card) {
  [uploadCard, progressCard, resultCard, errorCard].forEach((c) => c.classList.add("hidden"));
  card.classList.remove("hidden");
}

function setFile(file) {
  selectedFile = file;
  filenameEl.textContent = file ? file.name : "";
  generateBtn.disabled = !file;
}

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => {
  if (e.target.files.length) setFile(e.target.files[0]);
});

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
  })
);
dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});

function syncQualityEnabled() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const qm = document.getElementById("quality-modes");
  const disabled = mode === "none";
  qm.style.opacity = disabled ? "0.45" : "1";
  qm.querySelectorAll("input").forEach((i) => (i.disabled = disabled));
}
document.querySelectorAll('input[name="mode"]').forEach((r) =>
  r.addEventListener("change", syncQualityEnabled)
);
syncQualityEnabled();

generateBtn.addEventListener("click", startJob);
$("#restart-btn").addEventListener("click", reset);
$("#error-restart").addEventListener("click", reset);

$("#copy-btn").addEventListener("click", async () => {
  const text = (tabData && tabData.ascii) || "";
  await navigator.clipboard.writeText(text);
  const btn = $("#copy-btn");
  btn.textContent = "Copied!";
  setTimeout(() => (btn.textContent = "Copy"), 1500);
});

function reset() {
  if (pollTimer) clearInterval(pollTimer);
  stopPlayback();
  playbackNotes = null;
  audioNotes = null;
  tabData = null;
  setFile(null);
  fileInput.value = "";
  uploadBpmInput.value = "";
  bpmInput.value = "";
  bpmHint.textContent = "";
  show(uploadCard);
}

async function startJob() {
  ensureAudioContext(); // this click is a user gesture — unlock audio now
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const quality = document.querySelector('input[name="quality"]:checked').value;
  const instrument = document.querySelector('input[name="instrument"]:checked').value;
  const form = new FormData();
  form.append("file", selectedFile);
  form.append("separate_mode", mode);
  form.append("quality", quality);
  form.append("instrument", instrument);
  const uploadBpm = parseFloat(uploadBpmInput.value);
  if (uploadBpm >= 30 && uploadBpm <= 300) {
    form.append("bpm", String(uploadBpm));
  }

  show(progressCard);
  statusText.textContent = "Uploading…";
  barFill.style.width = "4%";
  logOutput.textContent = "";

  let res;
  try {
    res = await fetch("/api/upload", { method: "POST", body: form });
  } catch (err) {
    return showError("Could not reach the server: " + err.message);
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    return showError(detail.detail || "Upload failed (" + res.status + ")");
  }
  const { job_id } = await res.json();
  pollTimer = setInterval(() => poll(job_id), 1200);
  poll(job_id);
}

async function poll(jobId) {
  let res;
  try {
    res = await fetch("/api/status/" + jobId);
  } catch {
    return; // transient; try again next tick
  }
  if (!res.ok) return;
  const job = await res.json();

  statusText.textContent = job.message || job.status;
  barFill.style.width = (job.progress || 0) + "%";
  logOutput.textContent = (job.logs || []).join("\n");
  logOutput.scrollTop = logOutput.scrollHeight;

  if (job.status === "done") {
    clearInterval(pollTimer);
    $("#download-tab").href = "/api/tab/" + jobId;
    const midi = $("#download-midi");
    if (job.has_midi) {
      midi.href = "/api/midi/" + jobId;
      midi.style.display = "";
    } else {
      midi.style.display = "none";
    }
    const meta = [];
    if (job.instrument) meta.push(job.instrument);
    if (job.bpm) meta.push("~" + job.bpm + " BPM");
    $("#tab-meta").textContent = meta.length ? "(" + meta.join(" · ") + ")" : "";
    $("#run-path").textContent =
      "Run saved as id " + jobId +
      "  →  outputs/" + jobId + "/  (audio, tab.txt, transcription.mid, tabdata.json, run.json + logs)";
    await setupResult(jobId, job);
    show(resultCard);
  } else if (job.status === "error") {
    clearInterval(pollTimer);
    showError(job.error + "\n\n" + (job.logs || []).join("\n"));
  }
}

function showError(msg) {
  if (pollTimer) clearInterval(pollTimer);
  errorOutput.textContent = msg;
  show(errorCard);
}

/* --------------------- Interactive tab + playback --------------------- */

const playerEl = $("#player");
const playBtn = $("#play-btn");
const stopBtn = $("#stop-btn");
const playFill = $("#play-fill");
const playTime = $("#play-time");
const speedInput = $("#speed");
const speedVal = $("#speed-val");
const soundLabel = $("#sound-label");
const resultTitle = $("#result-title");
const uploadBpmInput = $("#upload-bpm");
const bpmInput = $("#bpm-input");
const bpmHint = $("#bpm-hint");

const GM_NAME = {
  guitar: "acoustic_guitar_steel",
  bass: "electric_bass_finger",
  piano: "acoustic_grand_piano",
};
const GM_LABEL = {
  acoustic_guitar_steel: "Steel guitar (sampled)",
  electric_bass_finger: "Electric bass (sampled)",
  acoustic_grand_piano: "Acoustic grand piano (sampled)",
};

// gleitz soundfonts key samples by flat note names (A0, Bb0, B0, C1, Db1, …).
const SF_FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
function midiToSfName(m) {
  return SF_FLAT_NAMES[m % 12] + (Math.floor(m / 12) - 1);
}
function songNoteNames() {
  const set = new Set();
  (playbackNotes || []).forEach((n) => n.midis.forEach((m) => set.add(midiToSfName(m))));
  return [...set];
}

// Create + resume the AudioContext. MUST be called from a user gesture
// (e.g. the Generate or Play click) so the browser doesn't keep it suspended.
function ensureAudioContext() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
  } catch (e) {
    /* ignore */
  }
}

let tabData = null;
let playbackNotes = null; // visual onsets for highlight [{t, d, midis, colEl?, measure?}]
let audioNotes = null;    // faithful raw notes for audio scheduling [{t, d, midis}]
let colEls = [];          // tab column elements by slot index in render order
let keyEls = {};          // midi -> piano key element
let measureEls = [];      // sheet-music measure containers by measure index
let audioCtx = null;
let activeSources = [];
let rafId = null;
let playStartCtxTime = 0;
let playFromTime = 0;     // song-time offset to start from (seconds)
let totalDuration = 0;
let activeNote = null;    // current playbackNotes entry being highlighted
let activeKeyEls = [];
let activeMeasureEl = null;
let bufferCache = {};
let sfCache = {};         // GM name -> loaded soundfont instrument
let currentSf = null;     // instrument currently scheduled (for stopping)
let schedId = null;       // look-ahead scheduler interval id
let schedIndex = 0;       // index of next note to schedule
let schedSpeed = 1;       // playback speed locked at play start
let synthMaster = null;   // synth fallback master gain node
const LOOKAHEAD = 0.5;    // seconds of audio queued ahead of the clock

speedInput.addEventListener("input", () => {
  speedVal.textContent = parseFloat(speedInput.value).toFixed(2) + "×";
});
bpmInput.addEventListener("input", () => {
  updateBpmHint();
  stopPlayback();
});
bpmInput.addEventListener("change", () => {
  updateBpmHint();
  stopPlayback();
});

function detectedBpm() {
  if (!tabData) return null;
  const d = tabData.detected_bpm ?? tabData.bpm;
  return d && d > 0 ? d : null;
}

function userBpm() {
  const v = parseFloat(bpmInput.value);
  if (v >= 30 && v <= 300) return v;
  return detectedBpm();
}

/** Scale playback so a lower manual BPM slows notes vs. auto-detected tempo. */
function playbackTempo() {
  const det = detectedBpm();
  const user = userBpm();
  if (!det || !user || user <= 0) return 1;
  return det / user;
}

function updateBpmHint() {
  const det = detectedBpm();
  const user = userBpm();
  if (!det) {
    bpmHint.textContent = user ? "Manual BPM" : "";
    return;
  }
  const factor = playbackTempo();
  if (Math.abs(factor - 1) < 0.02) {
    bpmHint.textContent = "Detected ~" + det;
    return;
  }
  const pct = Math.round((factor - 1) * 100);
  bpmHint.textContent =
    "Detected ~" + det + " · playback " + (pct > 0 ? pct + "% slower" : -pct + "% faster");
}
playBtn.addEventListener("click", () => play(0));
stopBtn.addEventListener("click", () => stopPlayback());

async function setupResult(jobId, job) {
  stopPlayback();
  tabData = null;
  playbackNotes = null;
  audioNotes = null;
  playFill.style.width = "0";
  playTime.textContent = "0:00";

  if (job.has_tabdata) {
    try {
      const res = await fetch("/api/tabdata/" + jobId);
      if (res.ok) tabData = await res.json();
    } catch {
      tabData = null;
    }
  }

  const isPiano = tabData && tabData.kind === "piano";
  tabOutput.classList.toggle("hidden", isPiano);
  sheetEl.classList.toggle("hidden", !isPiano);
  keyboardWrap.classList.toggle("hidden", !isPiano);
  resultTitle.textContent = isPiano ? "Your Sheet Music" : "Your Tab";

  if (tabData) {
    const det = tabData.detected_bpm ?? tabData.bpm;
    if (det) bpmInput.value = String(det);
    updateBpmHint();
  }

  if (tabData && isPiano) {
    renderSheet(tabData);
    buildKeyboard(tabData);
    buildPlaybackNotes();
    playerEl.style.display = "";
    playBtn.disabled = !(playbackNotes && playbackNotes.length);
    warmSound();
  } else if (tabData) {
    renderTab(tabData);
    buildPlaybackNotes();
    playerEl.style.display = "";
    playBtn.disabled = !(playbackNotes && playbackNotes.length);
    warmSound();
  } else {
    tabOutput.textContent = job.tab || "(no tab)";
    playerEl.style.display = "none";
  }
}

function instrumentName() {
  return (tabData && tabData.instrument) || "guitar";
}

async function ensureInstrument() {
  if (window.__sfFailed || !window.Soundfont || !audioCtx) return null;
  const gm = GM_NAME[instrumentName()] || GM_NAME.guitar;
  const notes = songNoteNames();
  const cached = sfCache[gm];
  if (cached && notes.every((n) => cached.notes.has(n))) return cached.inst;
  try {
    const opts = notes.length ? { notes } : undefined; // load only used samples
    const t = performance.now();
    const inst = await Soundfont.instrument(audioCtx, gm, opts);
    console.log("[sf] loaded %s (%d notes) in %sms", gm, notes.length, (performance.now() - t).toFixed(0));
    sfCache[gm] = { inst, notes: new Set(notes) };
    return inst;
  } catch (e) {
    console.warn("Soundfont load failed; using synth.", e);
    return null;
  }
}

// Pre-load the (subset) instrument so the first Play has no lag. The audio
// context was already created/resumed on the Generate click, so loading here
// is allowed and decodes only the notes this song uses.
async function warmSound() {
  if (!(playbackNotes && playbackNotes.length)) {
    soundLabel.textContent = "";
    return;
  }
  if (window.__sfFailed || !window.Soundfont || !audioCtx) {
    soundLabel.textContent = "Sound: built-in synth";
    return;
  }
  const gm = GM_NAME[instrumentName()];
  soundLabel.textContent = "Sound: loading…";
  const inst = await ensureInstrument();
  soundLabel.textContent = inst
    ? "Sound: " + (GM_LABEL[gm] || "sampled")
    : "Sound: built-in synth";
}

function renderTab(data) {
  tabOutput.textContent = "";
  colEls = [];

  const labels = document.createElement("div");
  labels.className = "tab-labels";
  const labelSpacer = document.createElement("div");
  labelSpacer.className = "tab-chord";        // align with the chord lane
  labels.appendChild(labelSpacer);
  data.labels.forEach((l) => {
    const c = document.createElement("div");
    c.className = "tab-cell";
    c.textContent = l;
    labels.appendChild(c);
  });
  tabOutput.appendChild(labels);

  const track = document.createElement("div");
  track.className = "tab-track";
  data.slots.forEach((slot) => {
    const col = document.createElement("div");
    col.className = "tab-col";
    if (slot.bar) col.classList.add("bar");
    col.dataset.t = slot.t;

    const chord = document.createElement("div");
    chord.className = "tab-chord";
    if (slot.chord) chord.textContent = slot.chord;
    col.appendChild(chord);
    for (let si = 0; si < data.labels.length; si++) {
      const cell = document.createElement("div");
      cell.className = "tab-cell";
      const fret = slot.frets ? slot.frets[si] : undefined;
      if (fret !== undefined) {
        const span = document.createElement("span");
        span.className = "fret";
        span.textContent = fret;
        cell.appendChild(span);
      }
      col.appendChild(cell);
    }
    // Click a column to play from that point.
    if (slot.midis || slot.frets) {
      col.addEventListener("click", () => play(parseFloat(slot.t) || 0));
    }
    track.appendChild(col);
    colEls.push(col);
  });
  tabOutput.appendChild(track);
}

/* ----------------------------- Piano keyboard ----------------------------- */

const BLACK_PCS = new Set([1, 3, 6, 8, 10]);
const WHITE_W = 22;
const BLACK_W = 14;

function buildKeyboard(data) {
  keyboardEl.innerHTML = "";
  keyEls = {};

  let lo = 1e9;
  let hi = -1e9;
  data.onsets.forEach((o) =>
    o.midis.forEach((m) => {
      lo = Math.min(lo, m);
      hi = Math.max(hi, m);
    })
  );
  if (lo > hi) {
    lo = 48;
    hi = 84;
  }
  lo -= lo % 12;            // down to a C
  hi += 11 - (hi % 12);     // up to a B

  let whiteIndex = 0;
  for (let m = lo; m <= hi; m++) {
    const pc = m % 12;
    const isBlack = BLACK_PCS.has(pc);
    const k = document.createElement("div");
    k.className = "key " + (isBlack ? "black" : "white");
    if (isBlack) {
      k.style.width = BLACK_W + "px";
      k.style.left = whiteIndex * WHITE_W - BLACK_W / 2 + "px";
    } else {
      k.style.width = WHITE_W + "px";
      k.style.left = whiteIndex * WHITE_W + "px";
      if (pc === 0) {
        const lab = document.createElement("div");
        lab.className = "klabel";
        lab.textContent = "C" + (Math.floor(m / 12) - 1);
        k.appendChild(lab);
      }
      whiteIndex++;
    }
    keyboardEl.appendChild(k);
    keyEls[m] = k;
  }
  keyboardEl.style.width = whiteIndex * WHITE_W + "px";
}

/* --------------------------- Sheet music (VexFlow) ------------------------- */

const TOK_SLOTS = { w: 16, hd: 12, h: 8, qd: 6, q: 4, "8d": 3, "8": 2, "16": 1 };
const SLOT_TOK = [[16, "w"], [12, "hd"], [8, "h"], [6, "qd"], [4, "q"], [3, "8d"], [2, "8"], [1, "16"]];

function restTokens(nslots) {
  const out = [];
  let r = nslots;
  for (const [s, tok] of SLOT_TOK) {
    while (r >= s) {
      out.push(tok);
      r -= s;
    }
  }
  return out;
}

function largestToken(slots) {
  for (const [s, tok] of SLOT_TOK) if (s <= slots) return tok;
  return "16";
}

function renderSheet(data) {
  sheetEl.innerHTML = "";
  measureEls = [];

  const VF = window.Vex && window.Vex.Flow;
  if (window.__vexflowFailed || !VF) {
    const pre = document.createElement("pre");
    pre.textContent = data.ascii;
    sheetEl.appendChild(pre);
    return;
  }

  try {
    const sub = data.subdivision;
    const ml = sub * data.beats_per_measure;
    const nMeasures = Math.max(1, Math.ceil(data.total_slots / ml));
    const beats = data.beats_per_measure;

    const byMeasure = Array.from({ length: nMeasures }, () => []);
    data.onsets.forEach((o) => {
      const mi = Math.floor(o.slot / ml);
      if (mi < nMeasures) byMeasure[mi].push(o);
    });

    for (let mi = 0; mi < nMeasures; mi++) {
      const first = mi === 0;
      const width = first ? 230 : 170;
      const div = document.createElement("div");
      div.className = "measure";
      sheetEl.appendChild(div);
      measureEls.push(div);

      const renderer = new VF.Renderer(div, VF.Renderer.Backends.SVG);
      renderer.resize(width, 260);
      const ctx = renderer.getContext();

      const treble = new VF.Stave(0, 10, width);
      const bass = new VF.Stave(0, 120, width);
      if (first) {
        treble.addClef("treble").addTimeSignature(beats + "/4");
        bass.addClef("bass").addTimeSignature(beats + "/4");
      }
      treble.setContext(ctx).draw();
      bass.setContext(ctx).draw();
      if (first) {
        new VF.StaveConnector(treble, bass).setType("brace").setContext(ctx).draw();
        new VF.StaveConnector(treble, bass).setType("singleLeft").setContext(ctx).draw();
      }

      const tNotes = clefNotes(VF, byMeasure[mi], "treble", mi * ml, ml);
      const bNotes = clefNotes(VF, byMeasure[mi], "bass", mi * ml, ml);
      const tVoice = new VF.Voice({ num_beats: beats, beat_value: 4 })
        .setMode(VF.Voice.Mode.SOFT)
        .addTickables(tNotes);
      const bVoice = new VF.Voice({ num_beats: beats, beat_value: 4 })
        .setMode(VF.Voice.Mode.SOFT)
        .addTickables(bNotes);
      new VF.Formatter()
        .joinVoices([tVoice])
        .joinVoices([bVoice])
        .format([tVoice, bVoice], width - 30);
      tVoice.draw(ctx, treble);
      bVoice.draw(ctx, bass);
    }
  } catch (err) {
    console.error("Sheet render failed; showing text fallback.", err);
    sheetEl.innerHTML = "";
    const pre = document.createElement("pre");
    pre.textContent = data.ascii;
    sheetEl.appendChild(pre);
  }
}

function clefNotes(VF, onsets, clef, measureStart, ml) {
  const restKey = clef === "treble" ? "b/4" : "d/3";
  const makeRest = (tok) =>
    new VF.StaveNote({ clef, keys: [restKey], duration: tok + "r" });

  const present = onsets.filter((o) => o[clef].length > 0);
  const out = [];
  if (present.length === 0) {
    restTokens(ml).forEach((tok) => out.push(makeRest(tok)));
    return out;
  }

  const end = measureStart + ml;
  let cursor = measureStart;
  for (const o of present) {
    if (o.slot > cursor) restTokens(o.slot - cursor).forEach((t) => out.push(makeRest(t)));
    const room = end - o.slot;
    let tok = o.dur_token;
    if (!TOK_SLOTS[tok] || TOK_SLOTS[tok] > room) tok = largestToken(room);

    const keys = o[clef].map((n) => n.key);
    const sn = new VF.StaveNote({ clef, keys, duration: tok });
    keys.forEach((k, idx) => {
      if (k.includes("#")) sn.addModifier(new VF.Accidental("#"), idx);
    });
    const fingers = o[clef].map((n) => n.finger).filter(Boolean);
    if (fingers.length) {
      const ann = new VF.Annotation(fingers.join("·"));
      ann.setFont("Arial", 10);
      ann.setVerticalJustification(
        clef === "treble"
          ? VF.Annotation.VerticalJustify.TOP
          : VF.Annotation.VerticalJustify.BOTTOM
      );
      sn.addModifier(ann, 0);
    }
    // One chord symbol per onset: prefer the treble note, else the bass note.
    const showChord =
      o.chord &&
      ((clef === "treble" && o.treble.length) ||
        (clef === "bass" && o.treble.length === 0));
    if (showChord && VF.ChordSymbol) {
      try {
        const cs = new VF.ChordSymbol().addText(o.chord);
        sn.addModifier(cs, 0);
      } catch (e) {
        /* older VexFlow without ChordSymbol — skip */
      }
    }
    out.push(sn);
    cursor = o.slot + TOK_SLOTS[tok];
  }
  if (cursor < end) restTokens(end - cursor).forEach((t) => out.push(makeRest(t)));
  return out;
}

function buildPlaybackNotes() {
  playbackNotes = [];
  audioNotes = null;
  if (!tabData) return;
  // Faithful audio = every transcribed note at its real time (no grid merge).
  if (tabData.playback && tabData.playback.length) {
    audioNotes = tabData.playback.slice().sort((a, b) => a.t - b.t);
  }
  if (tabData.kind === "piano") {
    const ml = tabData.subdivision * tabData.beats_per_measure;
    tabData.onsets.forEach((o) => {
      if (o.midis && o.midis.length) {
        playbackNotes.push({
          t: o.t,
          d: o.dur || 0.25,
          midis: o.midis,
          measure: Math.floor(o.slot / ml),
        });
      }
    });
    return;
  }
  tabData.slots.forEach((slot, i) => {
    if (slot.midis && slot.midis.length) {
      playbackNotes.push({
        t: slot.t,
        d: slot.dur || 0.25,
        midis: slot.midis,
        colEl: colEls[i],
      });
    }
  });
}

function midiToFreq(m) {
  return 440 * Math.pow(2, (m - 69) / 12);
}

// Karplus-Strong plucked-string synthesis -> a short AudioBuffer per pitch.
function pluckBuffer(freq, dur) {
  const sr = audioCtx.sampleRate;
  const key = Math.round(freq) + ":" + dur.toFixed(2);
  if (bufferCache[key]) return bufferCache[key];

  const len = Math.max(1, Math.floor(sr * dur));
  const buf = audioCtx.createBuffer(1, len, sr);
  const out = buf.getChannelData(0);
  const N = Math.max(2, Math.round(sr / freq));
  const ring = new Float32Array(N);
  for (let i = 0; i < N; i++) ring[i] = Math.random() * 2 - 1;
  let idx = 0;
  const decay = 0.996;
  for (let i = 0; i < len; i++) {
    const cur = ring[idx];
    const nxt = ring[(idx + 1) % N];
    const val = (cur + nxt) * 0.5 * decay;
    out[i] = cur;
    ring[idx] = val;
    idx = (idx + 1) % N;
  }
  bufferCache[key] = buf;
  return buf;
}

async function play(fromTime) {
  if (!playbackNotes || !playbackNotes.length) return;
  stopPlayback();
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  await audioCtx.resume();

  schedSpeed = parseFloat(speedInput.value) || 1;
  playFromTime = fromTime || 0;

  const gm = GM_NAME[instrumentName()];
  if (!window.__sfFailed && window.Soundfont && !sfCache[gm]) {
    soundLabel.textContent = "Sound: loading…";
  }
  const inst = await ensureInstrument();
  currentSf = inst;
  soundLabel.textContent = inst
    ? "Sound: " + (GM_LABEL[gm] || "sampled")
    : "Sound: built-in synth";

  const sched = audioNotes && audioNotes.length ? audioNotes : playbackNotes;
  totalDuration = 0;
  for (const note of sched) {
    totalDuration = Math.max(totalDuration, note.t + note.d);
  }
  for (const note of playbackNotes) {
    totalDuration = Math.max(totalDuration, note.t + note.d);
  }

  playStartCtxTime = audioCtx.currentTime + 0.12;

  if (!inst) {
    // Offline fallback synth: route everything through one master gain.
    bufferCache = {};
    synthMaster = audioCtx.createGain();
    synthMaster.gain.value = 0.85;
    synthMaster.connect(audioCtx.destination);
  }

  // Start at the first note at/after the seek point.
  schedIndex = 0;
  while (schedIndex < sched.length && sched[schedIndex].t < playFromTime - 1e-6) {
    schedIndex++;
  }

  playBtn.disabled = true;
  stopBtn.disabled = false;
  // Queue audio a little at a time so we never flood the audio engine.
  schedId = setInterval(scheduleAhead, 25);
  scheduleAhead();
  tick();
}

function scheduleAhead() {
  if (!audioCtx) return;
  const sched = audioNotes && audioNotes.length ? audioNotes : playbackNotes;
  const tempo = playbackTempo();
  const songNow =
    playFromTime + (audioCtx.currentTime - playStartCtxTime) * schedSpeed / tempo;
  const horizon = songNow + LOOKAHEAD * schedSpeed / tempo;
  while (schedIndex < sched.length) {
    const note = sched[schedIndex];
    if (note.t > horizon) break;
    const when = playStartCtxTime + (note.t - playFromTime) / schedSpeed / tempo;
    const at = Math.max(audioCtx.currentTime, when);
    const d = Math.max(0.08, note.d / schedSpeed / tempo);
    scheduleNote(note, at, d);
    schedIndex++;
  }
}

function scheduleNote(note, at, d) {
  if (currentSf) {
    const gain = 0.9 / Math.max(1, note.midis.length * 0.5);
    for (const m of note.midis) {
      try {
        currentSf.play(m, at, { duration: d + 0.25, gain });
      } catch (e) {
        /* ignore an individual note failure */
      }
    }
    return;
  }
  const tail = d + 0.35;
  for (const m of note.midis) {
    const src = audioCtx.createBufferSource();
    src.buffer = pluckBuffer(midiToFreq(m), tail);
    const g = audioCtx.createGain();
    g.gain.setValueAtTime(0.9 / Math.max(1, note.midis.length * 0.6), at);
    g.gain.setValueAtTime(g.gain.value, at + d);
    g.gain.exponentialRampToValueAtTime(0.0001, at + d + 0.12);
    src.connect(g).connect(synthMaster);
    src.start(at);
    src.stop(at + d + 0.15);
    activeSources.push(src);
  }
}

function tick() {
  const tempo = playbackTempo();
  const songTime =
    playFromTime + (audioCtx.currentTime - playStartCtxTime) * schedSpeed / tempo;
  const pct =
    totalDuration > 0 ? Math.min(1, songTime / (totalDuration * tempo)) : 0;
  playFill.style.width = (pct * 100).toFixed(1) + "%";
  playTime.textContent = fmtTime(Math.max(0, songTime));
  highlightAt(songTime);
  if (songTime >= totalDuration * tempo) {
    finishPlayback();
    return;
  }
  rafId = requestAnimationFrame(tick);
}

function highlightAt(songTime) {
  // Find the latest note whose onset has passed.
  let current = null;
  for (const note of playbackNotes) {
    if (note.t <= songTime + 1e-6) current = note;
    else break;
  }
  if (current === activeNote) return;
  clearHighlight();
  activeNote = current;
  if (!current) return;

  if (current.colEl) {
    current.colEl.classList.add("active");
    current.colEl.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }
  if (current.midis) {
    for (const m of current.midis) {
      const k = keyEls[m];
      if (k) {
        k.classList.add("active");
        activeKeyEls.push(k);
      }
    }
  }
  if (current.measure !== undefined && measureEls[current.measure]) {
    activeMeasureEl = measureEls[current.measure];
    activeMeasureEl.classList.add("active");
    activeMeasureEl.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }
}

function clearHighlight() {
  if (activeNote && activeNote.colEl) activeNote.colEl.classList.remove("active");
  activeKeyEls.forEach((k) => k.classList.remove("active"));
  activeKeyEls = [];
  if (activeMeasureEl) activeMeasureEl.classList.remove("active");
  activeMeasureEl = null;
  activeNote = null;
}

function fmtTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m + ":" + String(sec).padStart(2, "0");
}

function finishPlayback() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  if (schedId) clearInterval(schedId);
  schedId = null;
  playFill.style.width = "100%";
  playBtn.disabled = false;
  stopBtn.disabled = true;
  clearHighlight();
}

function stopPlayback() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  if (schedId) clearInterval(schedId);
  schedId = null;
  for (const s of activeSources) {
    try {
      s.stop();
    } catch {}
  }
  activeSources = [];
  if (currentSf && currentSf.stop) {
    try {
      currentSf.stop();
    } catch {}
  }
  currentSf = null;
  playFill.style.width = "0";
  playTime.textContent = "0:00";
  playBtn.disabled = !(playbackNotes && playbackNotes.length);
  stopBtn.disabled = true;
  clearHighlight();
}
