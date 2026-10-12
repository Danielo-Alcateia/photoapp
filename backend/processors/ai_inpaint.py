"""Modo IA opcional: remoção de marca d'água com FLUX.1 Fill (via Replicate).

Pago por uso e DESLIGADO por padrão: só roda quando ``REPLICATE_API_TOKEN``
estiver definido no servidor E o usuário ligar o botão "Modo IA" no app.
O token fica SEMPRE no servidor (nunca é enviado ao navegador).

Fidelidade: o resultado da IA é aplicado SOMENTE dentro da máscara da marca
d'água, com transição suave; todo o resto da foto permanece idêntico.

Sem novas dependências: usa urllib (stdlib).
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

import cv2
import numpy as np

from config import (
    AI_MAX_DIM,
    REPLICATE_API_TOKEN,
    REPLICATE_MODEL,
    REPLICATE_TIMEOUT,
)

_API = "https://api.replicate.com/v1"

# Mensagens amigáveis para os erros mais comuns da API.
_HTTP_HINTS = {
    401: "Token do Replicate inválido (REPLICATE_API_TOKEN).",
    402: "Sem créditos no Replicate — adicione crédito na conta.",
    404: f"Modelo '{REPLICATE_MODEL}' não encontrado no Replicate.",
    422: "A API recusou a entrada (imagem ou máscara inválidas).",
    429: "Muitas requisições ao Replicate — tente de novo em instantes.",
}


def ai_available() -> bool:
    """True se o modo IA está configurado (token presente)."""
    return bool(REPLICATE_API_TOKEN)


def _data_uri(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Falha ao codificar a imagem para a API.")
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def _request(method: str, url: str, payload: dict | None = None, prefer: str | None = None, timeout: int = 60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {REPLICATE_API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")
        msg = _HTTP_HINTS.get(exc.code, f"Erro {exc.code} na API do Replicate.")
        raise RuntimeError(f"{msg} {detail[:180]}".strip()) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede ao falar com o Replicate: {exc.reason}") from exc


def _fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _prepare(bgr: np.ndarray, mask: np.ndarray, dilate: int):
    """Recorta a máscara, dilata e reduz a entrada para caber no custo latência."""
    h, w = bgr.shape[:2]
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    binary = (mask > 127).astype(np.uint8) * 255
    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate * 2 + 1, dilate * 2 + 1))
        binary = cv2.dilate(binary, k, iterations=1)

    scale = 1.0
    if AI_MAX_DIM and max(h, w) > AI_MAX_DIM:
        scale = AI_MAX_DIM / max(h, w)
    if scale < 1.0:
        img_ai = cv2.resize(bgr, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
        mask_ai = cv2.resize(binary, (img_ai.shape[1], img_ai.shape[0]), interpolation=cv2.INTER_NEAREST)
    else:
        img_ai, mask_ai = bgr, binary
    return img_ai, mask_ai, binary


def remove_watermark_ai(bgr: np.ndarray, mask: np.ndarray, prompt: str = "", dilate: int = 6) -> tuple[np.ndarray, str]:
    """Remove a marca d'água com FLUX.1 Fill. Retorna ``(imagem_bgr, motor)``."""
    if not REPLICATE_API_TOKEN:
        raise ValueError("Modo IA não configurado. Defina REPLICATE_API_TOKEN no servidor.")

    h, w = bgr.shape[:2]
    img_ai, mask_ai, binary_full = _prepare(bgr, mask, dilate)
    if int(np.count_nonzero(mask_ai)) == 0:
        raise ValueError("Máscara vazia — detecte ou pinte a marca d'água antes.")

    payload = {
        "input": {
            "image": _data_uri(img_ai),
            # FLUX Fill: branco = área a preencher, preto = preservado.
            "mask": _data_uri(mask_ai),
            "prompt": prompt or "",
        }
    }

    pred = _request(
        "POST",
        f"{_API}/models/{REPLICATE_MODEL}/predictions",
        payload,
        prefer="wait=60",
        timeout=75,
    )

    deadline = time.time() + REPLICATE_TIMEOUT
    while pred.get("status") in ("starting", "processing") and time.time() < deadline:
        time.sleep(2)
        get_url = (pred.get("urls") or {}).get("get")
        if not get_url:
            break
        pred = _request("GET", get_url, timeout=30)

    if pred.get("status") != "succeeded":
        raise RuntimeError(f"A IA não concluiu (status={pred.get('status')}). {str(pred.get('error'))[:160]}")

    out = pred.get("output")
    if isinstance(out, list):
        out = out[0] if out else None
    if isinstance(out, dict):
        out = out.get("url")
    if not isinstance(out, str):
        raise RuntimeError("A IA não retornou imagem.")

    arr = cv2.imdecode(np.frombuffer(_fetch_bytes(out), np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("Falha ao ler a imagem retornada pela IA.")
    if arr.shape[:2] != (h, w):
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_LANCZOS4)

    # Cola o resultado da IA apenas dentro da máscara (resto fica idêntico).
    sigma = max(1.0, min(h, w) * 0.002)
    alpha = cv2.GaussianBlur(binary_full, (0, 0), sigma).astype(np.float32) / 255.0
    alpha = alpha[..., None]
    result = (arr.astype(np.float32) * alpha + bgr.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)
    return result, f"flux-fill ({REPLICATE_MODEL.split('/')[-1]})"
