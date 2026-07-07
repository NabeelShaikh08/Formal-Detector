"""The 'is this formal?' logic.

The model only *detects garments*. The judgement of formal vs. casual is a
transparent, rule-based layer on top of those detections — so it's explainable
("Formal because a necktie and a tailored jacket are present") rather than a
black box. This lives apart from the model so we can tune it without retraining.

Phase 1 targets menswear. Women's rules can extend WEIGHTS / NOTES later.
"""
from __future__ import annotations

from typing import Dict, List

# Contribution of each garment to the formality score.
# Positive = pulls formal, negative = pulls casual.
WEIGHTS: Dict[str, float] = {
    "tie": 3.0,      # the single strongest formal signal
    "jacket": 2.0,   # tailored jacket / blazer / suit
    "shirt": 1.5,    # collared / dress shirt
    "belt": 1.0,
    "pants": 1.0,    # trousers
    "shoe": 0.5,     # mildly formal in context (can't tell dress vs. sneaker)
    "t-shirt": -2.5,
    "shorts": -3.0,
}

# Human-readable notes + polarity for the ledger/UI.
NOTES: Dict[str, tuple] = {
    "tie":     ("A necktie elevates the ensemble.", "formal"),
    "jacket":  ("A tailored jacket lends structure.", "formal"),
    "shirt":   ("A collared shirt forms a proper base.", "formal"),
    "belt":    ("A belt signals a finished, deliberate look.", "formal"),
    "pants":   ("Full-length trousers read as considered.", "formal"),
    "shoe":    ("Footwear is present.", "neutral"),
    "t-shirt": ("A t-shirt keeps things casual.", "casual"),
    "shorts":  ("Shorts are decidedly informal.", "casual"),
}

# Score thresholds → verdict.
FORMAL_AT = 4.0
SMART_CASUAL_AT = 1.5

# Range used to map the raw score onto a 0–100 "formality index".
SCORE_MIN, SCORE_MAX = -3.0, 8.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def assess(detections: List[dict]) -> dict:
    """Turn a list of detections into a verdict + explanation.

    Presence-based: each garment class counts once, at its highest-confidence
    sighting. This is robust to duplicate boxes (e.g. two shoes) and keeps the
    reasoning easy to explain.
    """
    # Highest confidence seen per class.
    best: Dict[str, float] = {}
    for d in detections:
        label, c = d["label"], float(d["confidence"])
        if c > best.get(label, 0.0):
            best[label] = c

    if not best:
        return {
            "verdict": "Undetermined",
            "index": 0,
            "score": 0.0,
            "reasons": ["No assessable garments were detected."],
            "ledger": [],
        }

    score = 0.0
    ledger: List[dict] = []
    for label, conf in sorted(best.items(), key=lambda kv: -kv[1]):
        weight = WEIGHTS.get(label, 0.0)
        score += weight
        note, polarity = NOTES.get(label, ("", "neutral"))
        ledger.append(
            {"label": label, "confidence": round(conf, 4), "polarity": polarity, "note": note}
        )

    if score >= FORMAL_AT:
        verdict = "Formal"
    elif score >= SMART_CASUAL_AT:
        verdict = "Smart Casual"
    else:
        verdict = "Casual"

    index = round(_clamp((score - SCORE_MIN) / (SCORE_MAX - SCORE_MIN) * 100, 0, 100))

    # Build a short editorial rationale from the strongest contributors.
    formal_bits = [l for l in ledger if l["polarity"] == "formal"]
    casual_bits = [l for l in ledger if l["polarity"] == "casual"]
    reasons: List[str] = []
    if verdict == "Formal":
        lead = ", ".join(b["label"] for b in formal_bits[:3])
        reasons.append(f"A formal presentation, anchored by {lead}.")
    elif verdict == "Smart Casual":
        reasons.append("A composed but relaxed look — neither black-tie nor lounging.")
    else:
        if casual_bits:
            lead = ", ".join(b["label"] for b in casual_bits[:2])
            reasons.append(f"An informal look, driven by {lead}.")
        else:
            reasons.append("Too few formal elements to read as dressed-up.")
    if casual_bits and verdict != "Casual":
        reasons.append(
            "One or more casual elements ("
            + ", ".join(b["label"] for b in casual_bits[:2])
            + ") temper the formality."
        )

    return {
        "verdict": verdict,
        "index": index,
        "score": round(score, 2),
        "reasons": reasons,
        "ledger": ledger,
    }
