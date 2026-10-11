"""Melhoria de Iluminação - processamento tradicional, NÃO-generativo.

Pipeline (OpenCV, puro processamento de pixels):
  1. Balanço de brancos automático (Gray-World) -> corrige dominantes de cor;
  2. CLAHE aplicado ao canal L (Luminância) no espaço LAB -> clareia sombras
     com contraste limitado, sem estourar altas luzes;
  3. Curva de tons adaptativa (gamma) -> levanta sombras preservando realces.

Nenhuma etapa geometrizа, recria ou reinterpreta feições faciais.
"""
from __future__ import annotations

import cv2
import numpy as np


def _auto_white_balance(bgr: np.ndarray) -> np.ndarray:
    """Gray-World: normaliza a média de cada canal cinza."""
    result = bgr.astype(np.float32)
    means = result.reshape(-1, 3).mean(axis=0)
    gray = float(means.mean()) if means.mean() > 0 else 1.0
    gains = gray / np.maximum(means, 1.0)
    gains = np.clip(gains, 0.5, 2.0)
    result *= gains
    return np.clip(result, 0, 255).astype(np.uint8)


def _apply_clahe(bgr: np.ndarray, clip: float = 2.0) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _lift_shadows(bgr: np.ndarray, amount: float) -> np.ndarray:
    """Curva que sobe sombras de forma suave e preserva realces.

    y = x ** gamma, com gamma < 1 quando amount > 0.
    """
    if amount == 0:
        return bgr
    gamma = float(np.clip(1.0 - 0.35 * amount, 0.45, 1.0))
    lut = ((np.arange(256) / 255.0) ** gamma * 255.0).astype(np.uint8)
    return cv2.LUT(bgr, lut)


def improve_lighting(
    bgr: np.ndarray,
    strength: float = 1.0,
    white_balance: bool = True,
) -> np.ndarray:
    """Clareia sombras e corrige cor sem alterar formas do rosto.

    Parâmetros
    ----------
    bgr : imagem BGR (uint8).
    strength : 0.0 (suave) a 2.0 (forte).
    white_balance : aplica Gray-World se True.
    """
    strength = float(np.clip(strength, 0.0, 2.0))
    out = bgr.copy()

    if white_balance:
        out = _auto_white_balance(out)

    out = _apply_clahe(out, clip=1.5 + strength)
    out = _lift_shadows(out, amount=strength)

    # Realce local de contraste muito leve (unsharp) para "parecer" nítido.
    if strength > 0.25:
        blur = cv2.GaussianBlur(out, (0, 0), 1.2)
        out = cv2.addWeighted(out, 1.0 + 0.25 * strength, blur, -0.25 * strength, 0)

    return np.clip(out, 0, 255).astype(np.uint8)
