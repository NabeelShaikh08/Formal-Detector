"""Pydantic response models — the API's contract with the frontend."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Detection(BaseModel):
    label: str
    confidence: float
    box: List[float] = Field(..., description="Normalized [x1, y1, x2, y2] in 0..1")


class LedgerItem(BaseModel):
    label: str
    confidence: float
    polarity: str  # "formal" | "casual" | "neutral"
    note: str


class Assessment(BaseModel):
    verdict: str          # Formal | Smart Casual | Casual | Undetermined
    index: int            # 0..100 formality index
    score: float
    reasons: List[str]
    ledger: List[LedgerItem]


class DetectResponse(BaseModel):
    detections: List[Detection]
    assessment: Assessment


class VideoResponse(BaseModel):
    video: str            # base64 data URL of the annotated clip
    assessment: Assessment
    frames_analyzed: int


class Health(BaseModel):
    status: str
    model_loaded: bool
    classes: List[str]


class FrameRequest(BaseModel):
    image: str            # data URL or bare base64 (JPEG/PNG)
