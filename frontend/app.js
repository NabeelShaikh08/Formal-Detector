/* =====================================================================
   SARTOR — client logic
   Three modes (Still / Reel / Live) → the same detect+assess API.
   Boxes are returned as NORMALIZED coords and drawn on a canvas overlay.
   ===================================================================== */

const $ = (sel) => document.querySelector(sel);

const VERDICT_CLASS = {
  "Formal": "",
  "Smart Casual": "is-smart",
  "Casual": "is-casual",
  "Undetermined": "is-undetermined",
};

/* ---------------------------------------------------------------- status */
async function checkHealth() {
  const pill = $("#statusPill");
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    if (h.model_loaded) {
      pill.textContent = "— ATELIER OPEN";
      pill.style.color = "var(--brass)";
    } else {
      pill.textContent = "— AWAITING MODEL";
      pill.style.color = "var(--oxblood)";
    }
    if (h.classes?.length) {
      $("#footClasses").textContent = h.classes.join(" · ");
    }
  } catch {
    pill.textContent = "— OFFLINE";
    pill.style.color = "var(--oxblood)";
  }
}

/* ------------------------------------------------------------- mode tabs */
const panels = document.querySelectorAll("[data-panel]");
document.querySelectorAll(".mode").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    const mode = btn.dataset.mode;
    panels.forEach((p) => p.classList.toggle("is-shown", p.dataset.panel === mode));
    if (mode !== "live") stopLive();
    setCaption(mode);
  });
});

function setCaption(mode) {
  const c = {
    still: "Fig. — the subject under assessment",
    reel: "Fig. — the subject in motion",
    live: "Fig. — a live sitting",
  };
  $("#stageCaption").textContent = c[mode] || "";
}

/* --------------------------------------------------------------- helpers */
function showStatus(text) {
  $("#stageStatusText").textContent = text;
  $("#stageStatus").hidden = false;
}
function hideStatus() { $("#stageStatus").hidden = true; }

function renderVerdict(a) {
  $("#verdictEmpty").hidden = true;
  $("#verdictResult").hidden = false;

  const word = $("#verdictWord");
  word.textContent = a.verdict;
  word.className = "verdict-word " + (VERDICT_CLASS[a.verdict] ?? "");

  // count-up the index
  animateNumber($("#indexValue"), a.index);
  $("#gaugeFill").style.width = a.index + "%";

  // ledger
  const list = $("#ledgerList");
  list.innerHTML = "";
  a.ledger.forEach((it, i) => {
    const li = document.createElement("li");
    li.className = "ledger-item";
    li.style.animationDelay = (i * 60) + "ms";
    li.innerHTML =
      `<span class="dot dot--${it.polarity}"></span>` +
      `<span class="ledger-name">${it.label}</span>` +
      `<span class="ledger-conf">${Math.round(it.confidence * 100)}%</span>`;
    list.appendChild(li);
  });

  // notes
  const notes = $("#notesBody");
  notes.innerHTML = "";
  a.reasons.forEach((r, i) => {
    const p = document.createElement("p");
    p.className = "note-line";
    p.style.animationDelay = (i * 90) + "ms";
    p.textContent = r;
    notes.appendChild(p);
  });
}

function animateNumber(el, target) {
  const dur = 700, start = performance.now();
  function tick(now) {
    const t = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = String(Math.round(eased * target)).padStart(2, "0");
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

/* Draw normalized boxes onto a canvas sized to the displayed media. */
function drawBoxes(canvas, mediaEl, detections) {
  const rect = mediaEl.getBoundingClientRect();
  // account for object-fit: contain / cover letterboxing
  const natW = mediaEl.naturalWidth || mediaEl.videoWidth || rect.width;
  const natH = mediaEl.naturalHeight || mediaEl.videoHeight || rect.height;
  const fit = mediaEl.classList.contains("cover") ? "cover" : "contain";

  canvas.width = rect.width;
  canvas.height = rect.height;
  const scale = fit === "cover"
    ? Math.max(rect.width / natW, rect.height / natH)
    : Math.min(rect.width / natW, rect.height / natH);
  const dw = natW * scale, dh = natH * scale;
  const ox = (rect.width - dw) / 2, oy = (rect.height - dh) / 2;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = "500 13px 'Space Mono', monospace";

  detections.forEach((d) => {
    const [x1, y1, x2, y2] = d.box;
    const px = ox + x1 * dw, py = oy + y1 * dh;
    const pw = (x2 - x1) * dw, ph = (y2 - y1) * dh;

    ctx.strokeStyle = "#c6a15b";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(px, py, pw, ph);

    const tag = `${d.label} ${Math.round(d.confidence * 100)}%`;
    const tw = ctx.measureText(tag).width;
    ctx.fillStyle = "#c6a15b";
    ctx.fillRect(px, py - 20, tw + 12, 20);
    ctx.fillStyle = "#16130f";
    ctx.fillText(tag, px + 6, py - 6);
  });
}

/* ============================== STILL ============================== */
const dropzone = $("#dropzone");
const imageInput = $("#imageInput");

dropzone.addEventListener("click", () => imageInput.click());
["dragover", "dragenter"].forEach((e) =>
  dropzone.addEventListener(e, (ev) => { ev.preventDefault(); dropzone.classList.add("is-drag"); }));
["dragleave", "drop"].forEach((e) =>
  dropzone.addEventListener(e, (ev) => { ev.preventDefault(); dropzone.classList.remove("is-drag"); }));
dropzone.addEventListener("drop", (ev) => {
  const f = ev.dataTransfer.files[0];
  if (f) handleImage(f);
});
imageInput.addEventListener("change", (ev) => {
  const f = ev.target.files[0];
  if (f) handleImage(f);
});

async function handleImage(file) {
  const img = $("#stillImg");
  img.src = URL.createObjectURL(file);
  $("#dropzone").hidden = true;
  $("#stillPreview").hidden = false;
  await img.decode().catch(() => {});

  showStatus("Assessing the cloth…");
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/detect/image", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const data = await r.json();
    img.dataset.dets = JSON.stringify(data.detections);
    drawBoxes($("#stillCanvas"), img, data.detections);
    renderVerdict(data.assessment);
  } catch (err) {
    alert("Assessment failed: " + err.message);
  } finally {
    hideStatus();
  }
}
// redraw overlay on resize
window.addEventListener("resize", () => {
  const img = $("#stillImg");
  if (img && !$("#stillPreview").hidden && img.dataset.dets) {
    drawBoxes($("#stillCanvas"), img, JSON.parse(img.dataset.dets));
  }
});

/* ============================== REEL ============================== */
const videoDrop = $("#videoDrop");
const videoInput = $("#videoInput");

videoDrop.addEventListener("click", () => videoInput.click());
["dragover", "dragenter"].forEach((e) =>
  videoDrop.addEventListener(e, (ev) => { ev.preventDefault(); videoDrop.classList.add("is-drag"); }));
["dragleave", "drop"].forEach((e) =>
  videoDrop.addEventListener(e, (ev) => { ev.preventDefault(); videoDrop.classList.remove("is-drag"); }));
videoDrop.addEventListener("drop", (ev) => {
  const f = ev.dataTransfer.files[0];
  if (f) handleVideo(f);
});
videoInput.addEventListener("change", (ev) => {
  const f = ev.target.files[0];
  if (f) handleVideo(f);
});

async function handleVideo(file) {
  showStatus("Reviewing the reel… this may take a moment.");
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/detect/video", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const data = await r.json();
    $("#videoDrop").hidden = true;
    $("#reelPreview").hidden = false;
    $("#reelVideo").src = data.video;
    renderVerdict(data.assessment);
  } catch (err) {
    alert("Assessment failed: " + err.message);
  } finally {
    hideStatus();
  }
}

/* ============================== LIVE ============================== */
let liveStream = null;
let liveTimer = null;
let liveBusy = false;

$("#liveStart").addEventListener("click", startLive);
$("#liveStop").addEventListener("click", stopLive);

async function startLive() {
  try {
    liveStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
  } catch {
    alert("Camera access is required for a live sitting.");
    return;
  }
  const v = $("#liveVideo");
  v.classList.add("cover");
  v.srcObject = liveStream;
  $("#liveIdle").hidden = true;
  $("#livePreview").hidden = false;
  await v.play().catch(() => {});
  liveTimer = setInterval(sampleLive, 700);
}

function stopLive() {
  if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
  if (liveStream) { liveStream.getTracks().forEach((t) => t.stop()); liveStream = null; }
  const idle = $("#liveIdle"), prev = $("#livePreview");
  if (idle && prev) { idle.hidden = false; prev.hidden = true; }
}

async function sampleLive() {
  if (liveBusy) return;
  const v = $("#liveVideo");
  if (!v.videoWidth) return;
  liveBusy = true;

  const c = document.createElement("canvas");
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext("2d").drawImage(v, 0, 0);
  const dataUrl = c.toDataURL("image/jpeg", 0.7);

  try {
    const r = await fetch("/api/detect/frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: dataUrl }),
    });
    if (r.ok) {
      const data = await r.json();
      drawBoxes($("#liveCanvas"), v, data.detections);
      renderVerdict(data.assessment);
    }
  } catch { /* transient — keep sampling */ }
  finally { liveBusy = false; }
}

/* --------------------------------------------------------------- init */
checkHealth();
setCaption("still");
