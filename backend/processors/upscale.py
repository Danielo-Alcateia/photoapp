"""Melhoria de Resolução - super-resolução de TEXTURA, não de identidade.

Usa a rede RRDBNet do Real-ESRGAN, reimplementada em PyTorch puro
(``processors/rrdbnet.py``) para evitar dependências pesadas e, sobretudo,
o `gfpgan` que o pacote `realesrgan` exigiria — o que feriria a política de
fidelidade fisionômica.

Fallback matemático (sem torch): LANCZOS + unsharp mask.

GUARDA DE FIDELIDADE FISIONÔMICA: nenhum modelo de reconstrução facial
(CodeFormer/GFPGAN) é instalado, importado ou usado.
"""
from __future__ import annotations

import importlib.util
import threading
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import DEFAULT_UPSCALE, FORBIDDEN_FACE_GENERATORS, MODELS_DIR

_model = None
_model_scale: Optional[int] = None
_lock = threading.Lock()
_failed = False

# Pesos oficiais do Real-ESRGAN (rede RRDBNet focada em texturas).
WEIGHTS = {
    2: ("RealESRGAN_x2plus.pth",
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"),
    4: ("RealESRGAN_x4plus.pth",
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"),
}


def _forbidden_present() -> Optional[str]:
    for name in FORBIDDEN_FACE_GENERATORS:
        if importlib.util.find_spec(name) is not None:
            return name
    return None


def ensure_weights(scale: int) -> Path:
    """Baixa os pesos do Real-ESRGAN se ainda não existirem (com cache local)."""
    name, url = WEIGHTS.get(scale, WEIGHTS[DEFAULT_UPSCALE])
    dest = MODELS_DIR / name
    if dest.exists() and dest.stat().st_size > 1024:
        return dest
    print(f"[upscale] Baixando pesos do Real-ESRGAN ({name})...")
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)
    return dest


def get_model(scale: int):
    global _model, _model_scale, _failed
    scale = scale if scale in (2, 4) else DEFAULT_UPSCALE
    if _model is not None and _model_scale == scale:
        return _model
    if _failed:
        return None
    with _lock:
        if _model is not None and _model_scale == scale:
            return _model
        try:
            import torch

            from .rrdbnet import load_rrdbnet

            weights = ensure_weights(scale)
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            _model = (load_rrdbnet(str(weights), scale, device), device, scale)
            _model_scale = scale
        except Exception as exc:  # pragma: no cover
            print(f"[upscale] Real-ESRGAN indisponível, usando fallback: {exc}")
            _failed = True
            _model = None
    return _model


def _fallback_upscale(bgr: np.ndarray, scale: int) -> np.ndarray:
    h, w = bgr.shape[:2]
    up = cv2.resize(bgr, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(up, (0, 0), 2.0)
    sharp = cv2.addWeighted(up, 1.6, blur, -0.6, 0)
    return np.clip(sharp, 0, 255).astype(np.uint8)


def improve_resolution(bgr: np.ndarray, scale: int = DEFAULT_UPSCALE) -> tuple[np.ndarray, str]:
    """Aumenta a resolução preservando a identidade da pessoa.

    Retorna ``(imagem_bgr, motor_usado)``.
    """
    scale = scale if scale in (2, 4) else DEFAULT_UPSCALE

    forbidden = _forbidden_present()
    if forbidden:
        print(f"[upscale] Pacote proibido detectado ({forbidden}); ignorado por política.")

    loaded = get_model(scale)
    if loaded is not None:
        model, device, _ = loaded
        try:
            from .rrdbnet import enhance

            out = enhance(model, bgr, scale, device)
            return out, f"realesrgan-x{scale}"
        except Exception as exc:
            print(f"[upscale] Falha no Real-ESRGAN, usando fallback: {exc}")

    return _fallback_upscale(bgr, scale), f"lanczos-x{scale}"
