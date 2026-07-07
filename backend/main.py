"""FastAPI application for the formal-attire assessment tool.

Three input modes, all backed by the same detector + formality layer:
  • POST /api/detect/image  — single photograph (multipart upload)
  • POST /api/detect/frame  — one webcam frame (base64 JSON)  → drives Live mode
  • POST /api/detect/video  — a short clip (multipart) → annotated clip + summary

The model is loaded ONCE at startup and kept in memory (contrast with the old
os.system-per-request pattern). The frontend is served as static files.
"""
from __future__ import annotations

import base64
import io
import tempfile
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from detector import Detector
from formality import assess
from schemas import DetectResponse, FrameRequest, Health, VideoResponse

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

detector = Detector()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok = detector.load()
    if ok:
        print(f"✓ Model loaded from {detector.model_path}")
    else:
        print(f"⚠ No model yet at {detector.model_path} — detection endpoints will 503 "
              f"until best.pt is added.")
    yield


app = FastAPI(title="SARTOR — Formal Attire Assessment", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_model() -> None:
    if not detector.loaded:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Add models/best.pt and restart the server.",
        )


def _decode_data_url(data: str) -> Image.Image:
    """Accept a data URL or bare base64 and return an RGB PIL image."""
    if "," in data and data.strip().startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid image data: {exc}")


# -- API ------------------------------------------------------------------

@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(
        status="ok",
        model_loaded=detector.loaded,
        classes=list(detector.names.values()) if detector.names else [],
    )


@app.post("/api/detect/image", response_model=DetectResponse)
async def detect_image(file: UploadFile = File(...)) -> DetectResponse:
    _require_model()
    raw = await file.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read image: {exc}")
    dets = detector.detect_pil(img)
    return DetectResponse(detections=dets, assessment=assess(dets))


@app.post("/api/detect/frame", response_model=DetectResponse)
async def detect_frame(req: FrameRequest) -> DetectResponse:
    """Low-latency path for Live mode — returns box coords for the browser to draw."""
    _require_model()
    img = _decode_data_url(req.image)
    dets = detector.detect_pil(img)
    return DetectResponse(detections=dets, assessment=assess(dets))


# Elegant, restrained annotation for burned-in video frames.
_BRASS = (91, 161, 198)   # BGR of #C6A15B
_BONE = (216, 230, 237)   # BGR of soft bone


def _draw(frame: np.ndarray, result) -> None:
    for b in result.boxes:
        x1, y1, x2, y2 = (int(v) for v in b.xyxy[0])
        cls_id = int(b.cls[0])
        label = detector.names.get(cls_id, str(cls_id))
        conf = float(b.conf[0])
        cv2.rectangle(frame, (x1, y1), (x2, y2), _BRASS, 2)
        tag = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_DUPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), _BRASS, -1)
        cv2.putText(frame, tag, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_DUPLEX, 0.5,
                    (20, 18, 15), 1, cv2.LINE_AA)


@app.post("/api/detect/video", response_model=VideoResponse)
async def detect_video(file: UploadFile = File(...)) -> VideoResponse:
    """Process a short clip: sample frames, detect, burn in boxes, summarize.

    For responsiveness we sample every Nth frame and cap the total analyzed —
    this is meant for short clips, not feature films.
    """
    _require_model()
    raw = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tin:
        tin.write(raw)
        in_path = tin.name
    out_path = in_path.replace(".mp4", "_out.mp4")

    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Could not open video.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    stride = 2            # analyze every 2nd frame
    max_frames = 300      # safety cap on analyzed frames

    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps / stride, (w, h))

    verdicts: Counter = Counter()
    all_dets: list = []
    analyzed = 0
    idx = 0
    while analyzed < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            dets, result = detector.detect_bgr(frame)
            _draw(frame, result)
            a = assess(dets)
            verdicts[a["verdict"]] += 1
            all_dets.extend(dets)
            writer.write(frame)
            analyzed += 1
        idx += 1

    cap.release()
    writer.release()

    # Summary assessment across the whole clip (aggregate of every sighting).
    summary = assess(all_dets)
    if verdicts:
        summary["verdict"] = verdicts.most_common(1)[0][0]

    with open(out_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")
    Path(in_path).unlink(missing_ok=True)
    Path(out_path).unlink(missing_ok=True)

    return VideoResponse(
        video=f"data:video/mp4;base64,{b64}",
        assessment=summary,
        frames_analyzed=analyzed,
    )


# -- Static frontend (mounted last so /api/* wins) ------------------------
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
