"""Orquestrador automático de remoção de marca d'água.

Dado (imagem, máscara), este módulo decide sozinho o melhor caminho:

  1. ANALISA a região mascarada (textura, densidade de bordas, cobertura);
  2. DECIDE o motor primário:
       - fundo liso  -> "free" (inpainting local LaMa/Telea, custo zero)
       - texturizado -> "bria" (remoção pura, sem alucinar)
       - área grande -> "flux" (inpainting generativo)
  3. EXECUTA, MEDE a qualidade do resultado (marca residual + halo de brilho +
     emenda na borda) e, se ficar ruim, encadeia o motor complementar (combo);
  4. Devolve o MELHOR resultado, respeitando um teto de chamadas pagas.

Fidelidade: cada motor já compõe a saída apenas dentro da máscara.
"""
from __future__ import annotations

import cv2
import numpy as np

from config import (
    AUTO_EARLY_STOP,
    AUTO_MAX_CALLS,
    AUTO_RESIDUAL_THRESHOLD,
    BRIA_MASK_INVERT,
    COST_ERASER_USD,
    COST_FILL_USD,
)
from .ai_inpaint import bria_erase, flux_fill
from .inpainting import remove_watermark
from .watermark import central_mask, detect_watermark

# Limiares de análise (heurísticos, conservadores).
_TEX_SMOOTH = 120.0      # variância do Laplaciano abaixo disso = fundo liso
_EDGE_SMOOTH = 0.05      # densidade de bordas abaixo disso = fundo liso
_COVERAGE_LARGE = 0.06   # máscara acima de 6% da foto = "área grande"

_SHORT = {"flux": "FLUX", "bria": "Bria", "free": "Local"}


# ---------------------------------------------------------------------------
# Análise da região mascarada
# ---------------------------------------------------------------------------
def _binary(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return mask > 127


def analyze(bgr: np.ndarray, binary: np.ndarray) -> dict:
    h, w = bgr.shape[:2]
    n = int(binary.sum())
    coverage = n / float(h * w) if n else 0.0
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    texture = float(lap[binary].var()) if n else 0.0
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float((edges[binary] > 0).mean()) if n else 0.0
    return {
        "coverage": round(coverage, 4),
        "texture": round(texture, 1),
        "edge_density": round(edge_density, 4),
    }


def decide(feats: dict) -> tuple[str, str]:
    """Retorna ``(motor_primario, motor_de_reserva)`` como nomes internos."""
    smooth = feats["texture"] < _TEX_SMOOTH and feats["edge_density"] < _EDGE_SMOOTH
    if smooth:
        return "free", "flux"
    if feats["coverage"] >= _COVERAGE_LARGE:
        return "flux", "bria"
    return "bria", "flux"


# ---------------------------------------------------------------------------
# Juiz automático (menor = melhor)
# ---------------------------------------------------------------------------
def _residual(result_bgr: np.ndarray, binary: np.ndarray) -> float:
    """1.0 se ainda há marca detectável dentro da região mascarada."""
    mask_full, _boxes, found = detect_watermark(result_bgr)
    if not found:
        return 0.0
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    zone = cv2.dilate(binary.astype(np.uint8), k, iterations=1) > 0
    overlap = int(np.logical_and(mask_full > 0, zone).sum())
    return float(min(1.0, overlap / max(1, int(binary.sum()))))


def _halo(result_bgr: np.ndarray, binary: np.ndarray) -> float:
    """Diferença de brilho entre o preenchido e o entorno (halo de marca clara)."""
    if not binary.any():
        return 0.0
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    ring = cv2.dilate(binary.astype(np.uint8), k, iterations=1) > 0
    ring = np.logical_and(ring, ~binary)
    if not ring.any():
        return 0.0
    gray = cv2.cvtColor(result_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    delta = abs(float(np.median(gray[binary])) - float(np.median(gray[ring]))) / 255.0
    return float(min(1.0, delta / 0.15))


def _seam(result_bgr: np.ndarray, binary: np.ndarray) -> float:
    """Descontinuidade de gradiente na borda da máscara (emenda visível)."""
    if not binary.any():
        return 0.0
    b = (binary.astype(np.uint8)) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    band = np.logical_and(cv2.dilate(b, k) > 0, cv2.erode(b, k) == 0)
    if not band.any():
        return 0.0
    gray = cv2.cvtColor(result_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    seam = float(mag[band].mean())
    ref = float(mag.mean()) + 1e-3
    return float(min(1.0, seam / (ref * 3.0)))


def score(result_bgr: np.ndarray, binary: np.ndarray) -> float:
    """Nota de qualidade em [0,1]; menor é melhor."""
    return 0.5 * _residual(result_bgr, binary) + 0.3 * _halo(result_bgr, binary) + 0.2 * _seam(result_bgr, binary)


# ---------------------------------------------------------------------------
# Execução de um motor
# ---------------------------------------------------------------------------
def _run_engine(name: str, bgr: np.ndarray, binary: np.ndarray, prompt: str):
    """Roda um motor e devolve ``(imagem, engine_id, chamadas_pagas, custo_usd)``."""
    mask = binary.astype(np.uint8) * 255
    if name == "free":
        out, engine = remove_watermark(bgr, mask)
        return out, engine, 0, 0.0
    if name == "flux":
        out, engine = flux_fill(bgr, mask, prompt=prompt)
        return out, engine, 1, COST_FILL_USD
    if name == "bria":
        # Se a polaridade estiver errada, o resultado fica ruim e a verificação
        # descarta automaticamente (o fallback assume).
        out, engine = bria_erase(bgr, mask, invert=BRIA_MASK_INVERT)
        return out, engine, 1, COST_ERASER_USD
    raise ValueError(f"Motor desconhecido: {name}")


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def run_auto(bgr: np.ndarray, mask: np.ndarray, prompt: str = "", budget: int | None = None, central_fallback: bool = False):
    """Escolhe e executa o melhor caminho automaticamente.

    Retorna ``(melhor_bgr, relatório)``. Se a máscara vier vazia, tenta
    detectá-la automaticamente antes. Se não achar e ``central_fallback`` for
    True, usa uma máscara central sugestiva (o usuário ajusta antes de aplicar).
    """
    budget = AUTO_MAX_CALLS if budget is None else int(budget)
    binary = _binary(mask, bgr.shape[:2])

    detected = False
    used_central = False
    if int(binary.sum()) == 0:
        auto_mask, _boxes, found = detect_watermark(bgr)
        if not found:
            if central_fallback:
                binary = _binary(central_mask(bgr)[0], bgr.shape[:2])
                used_central = True
            else:
                raise ValueError(
                    "Não consegui detectar a marca automaticamente (ela pode cobrir a foto toda). "
                    "Pinte sobre ela com o dedo e toque em Aplicar, ou peça o fallback central."
                )
        else:
            binary = auto_mask > 0
            detected = True

    feats = analyze(bgr, binary)
    primary, fallback = decide(feats)

    order = [primary]
    if fallback and fallback != primary:
        order.append(fallback)
    if "free" not in order:
        order.append("free")  # rede de segurança (custo zero)

    steps: list[dict] = []
    results: list[tuple[float, np.ndarray, str, str]] = []
    paid = 0
    cost = 0.0

    for name in order:
        if name in ("flux", "bria") and paid >= budget:
            # Orçamento pago esgotado: pula pagos, mas ainda roda o grátis.
            continue
        try:
            out, engine, calls, c = _run_engine(name, bgr, binary, prompt)
        except Exception as exc:  # noqa: BLE001 - segue para o próximo motor
            steps.append({"engine": name, "error": str(exc)[:160]})
            continue
        paid += calls
        cost += c
        s = score(out, binary)
        steps.append({"engine": name, "engine_id": engine, "score": round(s, 3), "cost_usd": round(c, 3)})
        results.append((s, out, engine, name))
        # Early-stop: depois de uma chamada PAGA já boa, NÃO gastamos a 2ª
        # (economia de ~50%). Para o grátis/fallback usamos o limiar residual.
        stop_at = AUTO_EARLY_STOP if name in ("flux", "bria") else AUTO_RESIDUAL_THRESHOLD
        if s <= stop_at:
            break

    if not results:
        err = next((st["error"] for st in steps if st.get("error")), "desconhecido")
        raise RuntimeError(f"Nenhum motor conseguiu processar a imagem ({err}).")

    best_score, best_img, best_engine, _best_name = min(results, key=lambda r: r[0])

    parts = []
    for st in steps:
        label = _SHORT.get(st["engine"], st["engine"])
        parts.append(f"{label} (falhou)" if st.get("error") else label)

    report = {
        "mode": "auto",
        "auto_detected": detected,
        "fallback": ("central" if used_central else None),
        "primary": _SHORT.get(primary, primary),
        "decision": " -> ".join(parts),
        "engine": best_engine,
        "score": round(best_score, 3),
        "cost_usd": round(cost, 3),
        "steps": steps,
        "features": feats,
    }
    return best_img, report
