# PhotoApp - imagem do servidor (Render/Railway/Docker).
# Build em camadas: deps -> pesos -> código, para reaproveitar o cache.
#
# NOTA: Python 3.11 de propósito. O simple-lama-inpainting exige
# Pillow <10.0, que não possui wheel cp312 para Linux (só build de fonte).

FROM python:3.11-slim

# Bibliotecas nativas exigidas por OpenCV/Pillow/torch (build time no slim).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    PHOTOAPP_MAX_DIM=2400 \
    PHOTOAPP_UPSCALE=2 \
    TORCH_HOME=/app/backend/models/torch \
    HOME=/app/backend/models

WORKDIR /app

# --- Camada 1: dependências ------------------------------------------------
COPY backend/requirements.txt backend/requirements.txt
COPY backend/requirements-ai.txt backend/requirements-ai.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r backend/requirements.txt \
 && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r backend/requirements-ai.txt \
 && pip uninstall -y gfpgan codeformer || true

# --- Camada 2: pesos dos modelos (assados na imagem) -----------------------
COPY backend/config.py backend/config.py
COPY backend/processors backend/processors
COPY scripts/prefetch_weights.py scripts/prefetch_weights.py
RUN python scripts/prefetch_weights.py

# --- Camada 3: código ------------------------------------------------------
COPY backend backend
COPY frontend frontend

EXPOSE 7860
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','7860')+'/api/health')"]

CMD ["python", "backend/app.py"]