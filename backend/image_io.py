"""Leitura/escrita de imagens com correções de qualidade.

- Respeita a orientação EXIF das fotos de celular (rotações 90/180/270).
- Aceita HEIC-like via Pillow quando suportado; senão cai no OpenCV.
- Limita dimensões absurdas para evitar estouro de memória.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

from config import MAX_DIM


def decode_image(file_storage) -> np.ndarray:
    """Lê um UploadedFile e devolve BGR uint8 já com rotação EXIF aplicada."""
    data = file_storage.read()
    if not data:
        raise ValueError("Arquivo vazio ou inválido.")

    try:
        pil = Image.open(io.BytesIO(data))
        pil = ImageOps.exif_transpose(pil)  # corrige orientação do celular
        pil = pil.convert("RGB")
        rgb = np.asarray(pil)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        arr = np.frombuffer(data, np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Formato de imagem não suportado.")
        return bgr


def decode_mask(file_storage, size) -> np.ndarray:
    data = file_storage.read()
    if not data:
        raise ValueError("Máscara vazia.")
    mask = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError("Máscara inválida. Esperado PNG em tons de cinza.")
    h, w = size
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return mask


def limit_size(bgr: np.ndarray, max_dim: int = MAX_DIM) -> tuple[np.ndarray, float]:
    """Reduz a imagem se o maior lado exceder max_dim. Retorna (img, fator)."""
    h, w = bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return bgr, 1.0
    scale = max_dim / longest
    resized = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    return resized, scale


def encode(bgr: np.ndarray, fmt: str = "png", quality: int = 95) -> tuple[bytes, str]:
    """Codifica BGR para bytes. fmt: 'png' (lossless) ou 'jpg' (foto enxuta)."""
    fmt = (fmt or "png").lower()
    if fmt in ("jpg", "jpeg"):
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return (buf.tobytes(), "image/jpeg") if ok else (_raise())
    ok, buf = cv2.imencode(".png", bgr, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    return (buf.tobytes(), "image/png") if ok else (_raise())


def _raise():
    raise RuntimeError("Falha ao codificar a imagem de saída.")
