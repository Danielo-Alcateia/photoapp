"""Detecção automática de marca d'água (heurística determinística, sem IA).

Localiza regiões tipo texto/logotipo próximas às bordas da foto (posição
típica de marca d'água) e devolve uma máscara binária pronta para o
inpainting — sem precisar que o usuário pinte com o dedo.

Técnica (100% OpenCV, ~100ms em fotos de celular, leve para o Render free):
  1. MSER detecta regiões de texto (letras/elementos da marca).
  2. Canny + componentes conexos capturam logotipos não-textuais.
  3. Só candidatos no "anel de borda" da imagem (topo/base/laterais) passam,
     com filtros de área e compactação para rejeitar texturas do cenário.
  4. O resultado é conservador: se a área detectada for grande demais ou
     pulverizada, devolve "não encontrado" (o usuário pinta manualmente).

NÃO usa rede neural nem qualquer modelo generativo. Determinístico.
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

import cv2
import numpy as np

from config import DETECT_CACHE_MAX

_WORK = 1280  # maior lado usado na detecção (equilíbrio velocidade/precisão)

# Cache LRU em memória (por conteúdo da imagem): evita re-detectar a mesma foto
# em chamadas repetidas (frontend + orquestrador). Leve (~máscara 8-bit).
_cache: "OrderedDict[str, tuple]" = OrderedDict()
_cache_lock = threading.Lock()

# Limites do "anel de borda" onde marcas d'água costumam aparecer.
_TOP_RATIO = 0.18
_BOTTOM_RATIO = 0.18
_SIDE_RATIO = 0.11


def _edge_zones(h: int, w: int) -> np.ndarray:
    """Máscara binária das regiões onde marcas d'água são esperadas."""
    zones = np.zeros((h, w), np.uint8)
    top = max(1, int(_TOP_RATIO * h))
    bottom = max(1, int(_BOTTOM_RATIO * h))
    left = max(1, int(_SIDE_RATIO * w))
    right = max(1, int(_SIDE_RATIO * w))

    zones[0:top, :] = 255
    zones[h - bottom :, :] = 255
    zones[top : h - bottom, 0:left] = 255
    zones[top : h - bottom, w - right :] = 255
    # Suaviza as bordas do anel para não descartar marcas "quase" de fora.
    return cv2.dilate(zones, np.ones((31, 31), np.uint8), iterations=3)


def _centroid_in(box, zh: int, zw: int, ring: np.ndarray, key_name: str = "") -> bool:
    """Valida geometria do candidato E que o centróide esteja no anel."""
    x, y, bw, bh = [int(v) for v in box]
    if bw <= 2 or bh <= 2:
        return False
    area = bw * bh
    if area < 90 or area > 0.06 * zh * zw:  # nem grão de pó, nem poste inteiro
        return False
    if bh > 0.35 * zh or bw > 0.75 * zw:
        return False
    cx, cy = x + bw // 2, y + bh // 2
    if ring[cy, cx] == 0:
        return False
    return True


def _mser_mask(gray: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Regiões de texto via MSER, filtradas por anel e compactação."""
    mask = np.zeros(gray.shape[:2], np.uint8)
    try:
        mser = cv2.MSER_create()
        regions, bboxes = mser.detectRegions(gray)
    except Exception:
        return mask

    polygons = []
    for region, box in zip(regions, bboxes):
        x, y, bw, bh = [int(v) for v in box]
        if not _centroid_in(box, gray.shape[0], gray.shape[1], ring):
            continue
        fill = len(region) / (bw * bh + 1e-6)
        if fill < 0.12 or fill > 0.98:  # texto é "traço", não blob cheio
            continue
        polygons.append(np.array(region, dtype=np.int32).reshape(-1, 2))
    if polygons:
        cv2.fillPoly(mask, polygons, 255)
    return mask


def _edge_mask(gray: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Logotipos sem textura de texto: Canny + componentes conexos."""
    edges = cv2.Canny(gray, 60, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    mask = np.zeros(gray.shape[:2], np.uint8)
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if not _centroid_in((x, y, bw, bh), gray.shape[0], gray.shape[1], ring):
            continue
        if bw / bh > 6 or bh / bw > 5.5:  # evita "espaguetes" (cabo, fio)
            continue
        area = cv2.contourArea(cnt)
        if area / (bw * bh + 1e-6) < 0.10:
            continue
        cv2.fillPoly(mask, [cnt], 255)
    return mask


def detect_watermark(bgr: np.ndarray) -> tuple[np.ndarray, list, bool]:
    """Detecta marca d'água em ``bgr`` (com cache LRU por conteúdo).

    Retorna ``(mask_na_resolução_original, boxes_em_px_originais, encontrado)``.
    """
    key = None
    if DETECT_CACHE_MAX > 0:
        digest = hashlib.sha1(np.ascontiguousarray(bgr).tobytes()).hexdigest()
        key = f"{bgr.shape}:{digest}"
        with _cache_lock:
            hit = _cache.get(key)
            if hit is not None:
                _cache.move_to_end(key)
                return hit[0], list(hit[1]), hit[2]

    result = _detect_watermark(bgr)

    if key is not None:
        with _cache_lock:
            _cache[key] = (result[0], list(result[1]), result[2])
            _cache.move_to_end(key)
            while len(_cache) > DETECT_CACHE_MAX:
                _cache.popitem(last=False)
    return result


def central_mask(bgr: np.ndarray, ratio: float = 0.15) -> tuple[np.ndarray, list]:
    """Máscara de segurança no centro da foto (marca d'água "full-image").

    Usada quando a detecção falha e o usuário pede o fallback: cobre ~15% da
    imagem no centro — o usuário ainda ajusta/apaga com o pincel antes de aplicar.
    """
    h, w = bgr.shape[:2]
    bw = max(1, int(round(w * ratio)))
    bh = max(1, int(round(h * ratio)))
    x0 = (w - bw) // 2
    y0 = (h - bh) // 2
    mask = np.zeros((h, w), np.uint8)
    mask[y0 : y0 + bh, x0 : x0 + bw] = 255
    return mask, [(x0, y0, bw, bh)]


def _detect_watermark(bgr: np.ndarray) -> tuple[np.ndarray, list, bool]:
    h, w = bgr.shape[:2]
    scale = min(1.0, _WORK / max(h, w))
    zh, zw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))

    if scale < 1.0:
        small = cv2.resize(bgr, (zw, zh), interpolation=cv2.INTER_AREA)
    else:
        small = bgr

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    ring = _edge_zones(zh, zw)

    combined = cv2.bitwise_or(_mser_mask(gray, ring), _edge_mask(gray, ring))
    if combined.max() == 0:
        return np.zeros((h, w), np.uint8), [], False

    # Limpa farelos; falhas pequenas de detecção viram manchas coesas.
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cleaned = cv2.dilate(cleaned, np.ones((3, 3), np.uint8), iterations=1)

    n_pix = int(np.count_nonzero(cleaned))
    img_area = zh * zw
    coverage = n_pix / img_area
    if coverage < 0.0005 or coverage > 0.02:
        # Muito pouco = ruído; muito = detalhe do cenário, não marca.
        return np.zeros((h, w), np.uint8), [], False

    num_cc, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    if num_cc - 1 > 40:  # pulverizado demais -> não é uma marca coesa
        return np.zeros((h, w), np.uint8), [], False

    # Escala de volta para a resolução original.
    if scale < 1.0:
        mask_full = cv2.resize(cleaned, (w, h), interpolation=cv2.INTER_NEAREST)
    else:
        mask_full = cleaned

    boxes = []
    for i in range(1, num_cc):
        x, y, bw, bh = stats[i][:4]
        if bw <= 1 or bh <= 1 or bw * bh < 60:
            continue
        if scale < 1.0:
            x = min(w - 1, int(round(x / scale)))
            y = min(h - 1, int(round(y / scale)))
            bw = min(w - x, max(1, int(round(bw / scale))))
            bh = min(h - y, max(1, int(round(bh / scale))))
        boxes.append((x, y, bw, bh))

    return mask_full, boxes, True


def encode_mask(mask: np.ndarray) -> np.ndarray:
    """Máscara 8-bit -> BGR (para o frontend desenhar sobre a foto)."""
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)