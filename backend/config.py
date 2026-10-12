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

# Em RAM baixa (Render free = 512 MB) o torch NUNCA é carregado: as flags
# abaixo são FORÇADAS, ignorando eventual override manual de engine. Assim é
# impossível um ambiente pequeno tentar carregar LaMa/Real-ESRGAN e ser morto
# por oomKilled. Em máquinas grandes o override manual segue valendo.
UPSCALE_LITTLE_RAM = LOW_RAM or UPSCALE_ENGINE == "lanczos" or (UPSCALE_ENGINE == "auto" and LOW_RAM)

# Inpainting (remover marca d'água): o LaMa + torch não cabem em 512 MB
# (oomKilled no Render free). Abaixo de 1 GiB usamos o OpenCV Telea, que é
# determinístico e usa pouquíssima RAM. Em máquinas grandes o LaMa segue.
# Força manual (só fora de RAM baixa): PHOTOAPP_INPAINT_ENGINE=lama|opencv|auto
INPAINT_ENGINE = os.environ.get("PHOTOAPP_INPAINT_ENGINE", "auto").lower()
INPAINT_LITTLE_RAM = LOW_RAM or INPAINT_ENGINE == "opencv" or (INPAINT_ENGINE == "auto" and LOW_RAM)

# ---------------------------------------------------------------------------
# Modo IA opcional (Replicate) - pago por uso, OFF por padrão
# ---------------------------------------------------------------------------
# Só é habilitado se REPLICATE_API_TOKEN existir no ambiente do servidor.
# Dois modelos, cada um cobre a fraqueza do outro:
#   * flux_fill  -> realismo/pintura (inpainting generativo)
#   * bria_erase -> remoção pura (apaga sem deixar rastro)
# O orquestrador (processors/auto_edit.py) escolhe/encadeia automaticamente.
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "").strip()
# Retrocompat: REPLICATE_MODEL define o motor de pintura (fill).
REPLICATE_MODEL = os.environ.get("REPLICATE_MODEL", "black-forest-labs/flux-fill-pro").strip()
REPLICATE_MODEL_FILL = os.environ.get("REPLICATE_MODEL_FILL", REPLICATE_MODEL).strip()
REPLICATE_MODEL_ERASER = os.environ.get("REPLICATE_MODEL_ERASER", "bria/eraser").strip()
REPLICATE_TIMEOUT = int(os.environ.get("REPLICATE_TIMEOUT", "120"))
# Limita o maior lado enviado à IA (menos custo/latência). 0 = sem limite.
AI_MAX_DIM = int(os.environ.get("PHOTOAPP_AI_MAX_DIM", "1600"))
# Máscara do Bria Eraser: branco = apagar (igual à nossa). Se a verificação
# detectar que o resultado piorou, o orquestrador tenta automaticamente invertida.
BRIA_MASK_INVERT = os.environ.get("BRIA_MASK_INVERT", "false").strip().lower() in ("1", "true", "yes")

# Orquestrador automático (auto_edit):
#   * AUTO_MAX_CALLS  -> teto de chamadas pagas por pedido (custo controlado)
#   * AUTO_RESIDUAL_THRESHOLD -> acima disso a edição é considerada "não limpa".
#   * AUTO_EARLY_STOP -> se a 1ª chamada PAGA já vier boa (score <= valor),
#     NÃO gasta a 2ª (economia de ~50%).
AUTO_MAX_CALLS = int(os.environ.get("AUTO_MAX_CALLS", "2"))
AUTO_RESIDUAL_THRESHOLD = float(os.environ.get("AUTO_RESIDUAL_THRESHOLD", "0.18"))
AUTO_EARLY_STOP = float(os.environ.get("AUTO_EARLY_STOP_SCORE", "0.12"))

# Cache LRU em memória da detecção de marca d'água (evita re-detectar a mesma
# foto). Chave = hash do conteúdo. 0 desliga.
DETECT_CACHE_MAX = int(os.environ.get("PHOTOAPP_DETECT_CACHE", "20"))

# Custo estimado por chamada (US$) - usado só para exibir no frontend.
COST_FILL_USD = float(os.environ.get("COST_FILL_USD", "0.045"))
COST_ERASER_USD = float(os.environ.get("COST_ERASER_USD", "0.035"))

# Limite de thread do OpenCV (evita travar a UI em máquinas pequenas).
try:
    import cv2

    cv2.setNumThreads(max(1, (os.cpu_count() or 2) - 1))
except Exception:  # pragma: no cover
    pass
