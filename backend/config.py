"""Configurações centrais do backend.

Define caminhos, limites de upload e a POLÍTICA DE FIDELIDADE FISIONÔMICA.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# FIDELIDADE FISIONÔMICA - regra inviolável do projeto
# ---------------------------------------------------------------------------
# Nenhum processador pode usar modelos generativos de reconstrução facial.
# Segurança defensiva: se algum destes pacotes estiver presente, ele é
# IGNORADO para impedir alteração de traços, olhos, dentes ou expressões.
FORBIDDEN_FACE_GENERATORS = (
    "codeformer",
    "gfpgan",
    "codeformer_arch",
)

MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB por requisição
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp"}

# ESCALA de super-resolução padrão (x2 é mais rápido; x4 exige GPU).
DEFAULT_UPSCALE = int(os.environ.get("PHOTOAPP_UPSCALE", "2"))

# MAIOR lado aceito após decode (reduz abaixo disso).
# Em nuvem gratuita use ~2400 para caber na memória; em casa 8000.
MAX_DIM = int(os.environ.get("PHOTOAPP_MAX_DIM", "8000"))

# Limite de thread do OpenCV (evita travar a UI em máquinas pequenas).
try:
    import cv2

    cv2.setNumThreads(max(1, (os.cpu_count() or 2) - 1))
except Exception:  # pragma: no cover
    pass
