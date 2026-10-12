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

# ---------------------------------------------------------------------------
# Memória baixa (plano free, ~512 MB) -> desliga o Real-ESRGAN/torch
# ---------------------------------------------------------------------------
# O import do torch + RRDBNet sozinho já estoura 512 MB (oomKilled no Render
# free). Por isso detectamos o limite do cgroup: abaixo de 1 GiB o /api/upscale
# usa o fallback matemático LANCZOS + unsharp, sem torcar. Em qualquer outra
# máquina (dev, VPS, GPU) o Real-ESRGAN segue sendo o motor escolhido.
# Força manual: PHOTOAPP_UPSCALE_ENGINE=lanczos|realesrgan|auto
UPSCALE_ENGINE = os.environ.get("PHOTOAPP_UPSCALE_ENGINE", "auto").lower()


def _cgroup_memory_limit_mb() -> int | None:
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with Path(path).open() as f:
                value = f.read().strip()
            if value.isdigit():
                return int(value) // (1024 * 1024)
        except (OSError, ValueError):
            continue
    return None


_MEM_MB = _cgroup_memory_limit_mb()
LOW_RAM = _MEM_MB is not None and _MEM_MB < 1024

UPSCALE_LITTLE_RAM = UPSCALE_ENGINE == "lanczos" or (UPSCALE_ENGINE == "auto" and LOW_RAM)

# Inpainting (remover marca d'água): o LaMa + torch não cabem em 512 MB
# (oomKilled no Render free). Abaixo de 1 GiB usamos o OpenCV Telea, que é
# determinístico e usa pouquíssima RAM. Em máquinas grandes o LaMa segue.
# Força manual: PHOTOAPP_INPAINT_ENGINE=lama|opencv|auto
INPAINT_ENGINE = os.environ.get("PHOTOAPP_INPAINT_ENGINE", "auto").lower()
INPAINT_LITTLE_RAM = INPAINT_ENGINE == "opencv" or (INPAINT_ENGINE == "auto" and LOW_RAM)

# Limite de thread do OpenCV (evita travar a UI em máquinas pequenas).
try:
    import cv2

    cv2.setNumThreads(max(1, (os.cpu_count() or 2) - 1))
except Exception:  # pragma: no cover
    pass
