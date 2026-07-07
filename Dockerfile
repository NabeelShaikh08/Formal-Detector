# SARTOR — Hugging Face Spaces (Docker SDK) image
FROM python:3.11-slim

# System libraries OpenCV needs even in headless mode.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching).
COPY backend/requirements.txt ./backend/requirements.txt
# CPU-only PyTorch — Spaces free tier has no GPU, and this avoids the ~2.5GB CUDA build.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the rest of the project (backend, frontend, models, ...).
COPY . .

# HF Spaces serves the app on port 7860.
ENV PORT=7860
# Cache dirs must be writable by the non-root Spaces user.
ENV HF_HOME=/tmp/hf ULTRALYTICS_CONFIG_DIR=/tmp/ultralytics MPLCONFIGDIR=/tmp/mpl
EXPOSE 7860

WORKDIR /app/backend
CMD ["python", "main.py"]
