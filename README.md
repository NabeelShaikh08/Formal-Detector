---
title: SARTOR Formal Attire Assessment
emoji: 🎩
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# SARTOR — Formal Attire Assessment

A computer-vision app that judges whether a person is dressed **formally** or **casually**,
and explains *why*. A YOLO26 model detects garments (shirt, tie, jacket, trousers, shoes…),
and a transparent rule layer turns those detections into a verdict.

Three input modes: **Still** (photo), **Reel** (short clip), **Live** (webcam).

```
formal-wear-detector/
├── backend/          FastAPI app (model loaded once, in-process)
│   ├── main.py       routes + static serving + video pipeline
│   ├── detector.py   YOLO wrapper → normalized detections
│   ├── formality.py  the formal-vs-casual rules (explainable)
│   └── schemas.py    API response models
├── frontend/         the atelier UI (HTML/CSS/JS, no build step)
├── models/           ← drop best.pt here (from Colab)
└── notebooks/        the Colab training notebook
```

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

1. Put your trained weights at `models/best.pt`.
2. From `backend/`:
   ```bash
   python main.py
   ```
3. Open **http://localhost:8080**

The server boots even without `best.pt` — the UI loads and shows *"Awaiting model"*;
detection endpoints return 503 until the weights are in place.

## API

| Method | Route                | Purpose                          |
|--------|----------------------|----------------------------------|
| GET    | `/api/health`        | model status + class list        |
| POST   | `/api/detect/image`  | multipart photo → verdict        |
| POST   | `/api/detect/frame`  | base64 frame → verdict (Live)    |
| POST   | `/api/detect/video`  | multipart clip → annotated + summary |

## The formality rules

The model only *detects garments*; formality is decided in `formality.py` so it's
explainable and tunable without retraining. Weights (menswear, Phase 1):

| Garment | Pull | | Garment | Pull |
|---|---|---|---|---|
| tie | +3.0 | | shoe | +0.5 |
| jacket | +2.0 | | t-shirt | −2.5 |
| shirt | +1.5 | | shorts | −3.0 |
| belt / pants | +1.0 | | | |

Score → **Formal** (≥4) · **Smart Casual** (≥1.5) · **Casual** (<1.5).

> **Note:** Fashionpedia labels a `shoe` but not "dress shoe vs. sneaker", so footwear
> is weighted lightly. The strongest signal is the necktie. Women's rules can extend
> the same table later.

## 🔭 Future Scope & Applications

This is currently a proof-of-concept, but the approach extends naturally to
**automated dress-code compliance**:

- **🏦 Corporate & Banking** — integrate with office/branch CCTV to flag whether staff meet formal-attire policy.
- **🎓 Schools & Institutions** — check uniform / formal-dress compliance at entry gates.
- **🎩 Events & Venues** — enforce dress codes (black-tie, clubs, ceremonies).
- **🏨 Retail & Hospitality** — verify staff uniform standards.

**Planned to get there:**
- Larger, balanced training set (add `coat`, strengthen `jacket` / `tie` / `shoe`)
- **Multi-person** detection in one frame via a two-stage pipeline (pretrained person
  detector → per-person garment assessment) — needed for entrances and crowds
- **Per-person tracking** across video for live monitoring
- **Configurable dress-code rules** per deployment (bank ≠ school ≠ event)

> *Responsible use: camera-based monitoring should respect privacy, consent, and local
> regulations — the tool is meant to assist policy checks, not to make automated
> judgments about individuals.*

## Deploy on Hugging Face Spaces

This repo is ready to run as a **Docker Space**:

- `Dockerfile` builds the image (installs deps + OpenCV system libs) and runs the app.
- The app reads `PORT` from the environment; HF Spaces sets it to **7860** (see the
  `app_port` field in the metadata header above). Locally it defaults to `8080`.
- The YAML header at the top of this file is the Space configuration HF reads.

To deploy: create a Docker Space, then push this repo to it (Spaces are git repos).
Free Spaces are CPU-only — image/short-video assessment run fine; live webcam works
over the HTTPS URL but is limited by CPU + network round-trips.

