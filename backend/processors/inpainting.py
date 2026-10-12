"""Remoção de Marca d'Água - inpainting NÃO-generativo de identidade.

Estratégia:
  1. LaMa (`simple-lama-inpainting`) quando disponível: preenche a área
     mascarada APENAS com texturas/cores vizinhas (pele, cabelo, roupa).
  2. Fallback OpenCV (Telea): difusão de pixels, 100% determinística.

Qualidade:
  * Recorta automaticamente o menor retângulo em volta da máscara (+ margem),
    o que acelera muito e melhora o resultado em fotos grandes;
  * Cola o resultado de volta com borda suave (feather) para não deixar emenda.

GUARDA DE FIDELIDADE FISIONÔMICA: nenhum modelo de reconstrução facial
(CodeFormer/GFPGAN) é carregado ou utilizado aqui.
"""
from __future__ import annotations

import importlib.util
import threading

import cv2
import numpy as np
from PIL import Image

from config import FORBIDDEN_FACE_GENERATORS
from . import memory as _memory

_lama = None
_lama_lock = threading.Lock()
_lama_failed = False


def _evict_lama():
    global _lama
    _lama = None


_memory.register("lama", _evict_lama)


def get_lama():
    """Carrega o LaMa de forma preguiçosa e thread-safe.

    Antes de carregar, descarrega outros modelos pesados (Real-ESRGAN) para
    caber nos 512 MB do plano free.
    """
    global _lama, _lama_failed
    _memory.evict(keep="lama")
    if _lama is not None or _lama_failed:
        return _lama


def _forbidden_present():
    for name in FORBIDDEN_FACE_GENERATORS:
        if importlib.util.find_spec(name) is not None:
            return name
    return None


def get_lama():
    """Carrega o LaMa de forma preguiçosa e thread-safe."""
    global _lama, _lama_failed
    if _lama is not None or _lama_failed:
        return _lama
    with _lama_lock:
        if _lama is not None or _lama_failed:
            return _lama
        try:
            import torch
            from simple_lama_inpainting import SimpleLama

            try:
                _lama = SimpleLama()
            except TypeError:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _lama = SimpleLama(device=torch.device(device))
        except Exception as exc:  # pragma: no cover
            print(f"[inpainting] LaMa indisponível, usando fallback OpenCV: {exc}")
            _lama_failed = True
            _lama = None
    return _lama


def _lama_inpaint(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    lama = get_lama()
    if lama is None:
        raise RuntimeError("LaMa indisponível")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    m = Image.fromarray(mask).convert("L")
    result = lama(image, m)
    arr = np.array(result) if isinstance(result, Image.Image) else np.asarray(result)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _opencv_inpaint(bgr: np.ndarray, mask: np.ndarray, radius: int = 4) -> np.ndarray:
    return cv2.inpaint(bgr, mask, radius, cv2.INPAINT_TELEA)


def _bbox(mask: np.ndarray, pad: int):
    ys, xs = np.where(mask > 0)
    h, w = mask.shape[:2]
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(h, int(ys.max()) + pad + 1)
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(w, int(xs.max()) + pad + 1)
    return y0, y1, x0, x1


def remove_watermark(bgr: np.ndarray, mask: np.ndarray, dilate: int = 6) -> tuple[np.ndarray, str]:
    """Remove a marca d'água nas regiões brancas da máscara.

    Retorna ``(imagem_bgr, motor_usado)``.
    """
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.shape[:2] != bgr.shape[:2]:
        mask = cv2.resize(mask, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_NEAREST)

    binary = (cv2.GaussianBlur(mask, (3, 3), 0) > 127).astype(np.uint8) * 255
    if binary.max() == 0:
        return bgr.copy(), "none"

    if dilate > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate * 2 + 1, dilate * 2 + 1))
        binary = cv2.dilate(binary, kernel, iterations=1)

    forbidden = _forbidden_present()
    if forbidden:
        print(f"[inpainting] Pacote proibido detectado ({forbidden}); ignorado por política.")

    # Recorte ao redor da máscara (+ margem proporcional).
    pad = max(24, int(0.03 * max(bgr.shape[:2])))
    y0, y1, x0, x1 = _bbox(binary, pad)
    crop_img = bgr[y0:y1, x0:x1]
    crop_mask = binary[y0:y1, x0:x1]

    try:
        out_crop = _lama_inpaint(crop_img, crop_mask)
        engine = "lama"
    except Exception as exc:
        print(f"[inpainting] Fallback OpenCV Telea: {exc}")
        out_crop = _opencv_inpaint(crop_img, crop_mask)
        engine = "opencv-telea"

    # O LaMa faz padding para múltiplo de 8; reajusta ao tamanho do recorte.
    ch, cw = crop_img.shape[:2]
    if out_crop.shape[0] < ch or out_crop.shape[1] < cw:
        out_crop = cv2.resize(out_crop, (cw, ch), interpolation=cv2.INTER_LINEAR)
    else:
        out_crop = out_crop[:ch, :cw]

    result = bgr.copy()
    alpha = cv2.GaussianBlur(crop_mask, (0, 0), max(1.0, dilate * 0.6)).astype(np.float32) / 255.0
    alpha = alpha[..., None]
    region = result[y0:y1, x0:x1].astype(np.float32)
    result[y0:y1, x0:x1] = (out_crop.astype(np.float32) * alpha + region * (1.0 - alpha)).astype(np.uint8)
    return result, engine
