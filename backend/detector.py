"""Model wrapper — loads the trained YOLO weights once and runs inference.

The detector is intentionally thin: it turns pixels into a normalized list of
detections. All "is this formal?" reasoning lives in ``formality.py`` so the two
concerns stay independent and testable.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

# models/best.pt sits one level up from backend/
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "best.pt"

# Fallback names if the checkpoint somehow lacks them (it shouldn't).
CLASS_NAMES = ["shirt", "t-shirt", "pants", "shorts", "tie", "shoe", "belt", "jacket"]


class Detection(dict):
    """Plain dict with a fixed shape: {label, confidence, box:[x1,y1,x2,y2]}.

    Box coordinates are **normalized** to 0..1 relative to image size so the
    frontend can scale them to whatever size it renders the image at.
    """


class Detector:
    def __init__(self, model_path: Path = MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        self.model = None
        self.names = {i: n for i, n in enumerate(CLASS_NAMES)}

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> bool:
        """Load weights into memory. Returns False if the file isn't there yet."""
        if not self.model_path.exists():
            return False
        # Imported lazily so the server can boot even before ultralytics is installed.
        from ultralytics import YOLO

        self.model = YOLO(str(self.model_path))
        if getattr(self.model, "names", None):
            self.names = self.model.names
        return True

    # -- inference ---------------------------------------------------------

    def _collect(self, result, width: int, height: int) -> List[Detection]:
        dets: List[Detection] = []
        for b in result.boxes:
            cls_id = int(b.cls[0])
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            dets.append(
                Detection(
                    label=self.names.get(cls_id, str(cls_id)),
                    confidence=round(float(b.conf[0]), 4),
                    box=[
                        round(x1 / width, 5),
                        round(y1 / height, 5),
                        round(x2 / width, 5),
                        round(y2 / height, 5),
                    ],
                )
            )
        return dets

    def detect_pil(self, image: Image.Image, conf: float = 0.35, imgsz: int = 640) -> List[Detection]:
        """Run detection on an RGB PIL image (uploads, webcam frames)."""
        if not self.loaded:
            raise RuntimeError("Model not loaded")
        image = image.convert("RGB")
        result = self.model.predict(image, conf=conf, imgsz=imgsz, verbose=False)[0]
        w, h = image.size
        return self._collect(result, w, h)

    def detect_bgr(self, frame: np.ndarray, conf: float = 0.35, imgsz: int = 640):
        """Run detection on a BGR numpy frame (OpenCV / video).

        Returns (detections, result) so callers can also draw the boxes onto the
        frame using the raw pixel coordinates in ``result``.
        """
        if not self.loaded:
            raise RuntimeError("Model not loaded")
        result = self.model.predict(frame, conf=conf, imgsz=imgsz, verbose=False)[0]
        h, w = frame.shape[:2]
        return self._collect(result, w, h), result
