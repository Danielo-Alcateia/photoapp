"""Motores de IA opcionais (Replicate) — pagos por uso e OFF por padrão.

Dois modelos, cada um cobre a fraqueza do outro:
  * ``flux_fill``  (black-forest-labs/flux-fill-*) -> inpainting generativo:
    reconstrói textura/realismo dentro da máscara.
  * ``bria_erase`` (bria/eraser) -> remoção pura: apaga objeto/marca e
    reconstrói o fundo sem "alucinar".

O orquestrador automático (``processors/auto_edit.py``) decide sozinho qual
usar e/ou encadear os dois.

Fidelidade: o resultado da IA é aplicado SOMENTE dentro da máscara, com
transição suave; o resto da foto permanece idêntico ao original.

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
    REPLICATE_MODEL_ERASER,
    REPLICATE_MODEL_FILL,
    REPLICATE_TIMEOUT,
)

_API = "https://api.replicate.com/v1"

# Mensagens amigáveis para os erros mais comuns da API.
_HTTP_HINTS = {
    401: "Token do Replicate inválido (REPLICATE_API_TOKEN).",
    402: "Sem créditos no Replicate — adicione crédito na conta.",
    404: "Modelo não encontrado no Replicate (verifique REPLICATE_MODEL_*).",
    422: "A API recusou a entrada (imagem ou máscara inválidas).",
    429: "Muitas requisições ao Replicate — tente de novo em instantes.",
}


def ai_available() -> bool:
    """True se os motores de IA estão configurados (token presente)."""
    return bool(REPLICATE_API_TOKEN)


# ---------------------------------------------------------------------------
# Cliente HTTP genérico do Replicate
# ---------------------------------------------------------------------------
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


def _call_model(model: str, input_dict: dict, timeout: int | None = None) -> list[str]:
    """Roda um modelo do Replicate e devolve as URLs das imagens de saída."""
    if not REPLICATE_API_TOKEN:
        raise ValueError("Motores de IA não configurados. Defina REPLICATE_API_TOKEN no servidor.")
    timeout = timeout or REPLICATE_TIMEOUT

    pred = _request(
        "POST",
        f"{_API}/models/{model}/predictions",
        {"input": input_dict},
        prefer="wait=60",
        timeout=75,
    )
    deadline = time.time() + timeout
    while pred.get("status") in ("starting", "processing") and time.time() < deadline:
        time.sleep(2)
        get_url = (pred.get("urls") or {}).get("get")
        if not get_url:
            break
        pred = _request("GET", get_url, timeout=30)

    if pred.get("status") != "succeeded":
        raise RuntimeError(f"A IA '{model}' não concluiu (status={pred.get('status')}). {str(pred.get('error'))[:160]}")

    out = pred.get("output")
    if isinstance(out, str):
        return [out]
    if isinstance(out, list):
        urls = [u for u in out if isinstance(u, str)]
        if urls:
            return urls
    if isinstance(out, dict) and isinstance(out.get("url"), str):
        return [out["url"]]
    raise RuntimeError("A IA não retornou imagem.")


def _decode_first(urls: list[str]) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(_fetch_bytes(urls[0]), np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("Falha ao ler a imagem retornada pela IA.")
    return arr


# ---------------------------------------------------------------------------
# Preparo e composição (compartilhados pelos motores)
# ---------------------------------------------------------------------------
def _prepare(bgr: np.ndarray, mask: np.ndarray, dilate: int):
    """Normaliza a máscara, dilata e reduz a entrada para limitar custo/latência.

    Retorna ``(img_ai, mask_ai, binary_full)`` — ``binary_full`` na resolução
    original, usado na composição final.
    """
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


def _composite(arr: np.ndarray, bgr: np.ndarray, binary_full: np.ndarray) -> np.ndarray:
    """Cola o resultado da IA apenas dentro da máscara (resto fica idêntico)."""
    h, w = bgr.shape[:2]
    if arr.shape[:2] != (h, w):
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_LANCZOS4)
    sigma = max(1.0, min(h, w) * 0.002)
    alpha = cv2.GaussianBlur(binary_full, (0, 0), sigma).astype(np.float32) / 255.0
    alpha = alpha[..., None]
    return (arr.astype(np.float32) * alpha + bgr.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)


# ---------------------------------------------------------------------------
# Motores
# ---------------------------------------------------------------------------
def flux_fill(
    bgr: np.ndarray,
    mask: np.ndarray,
    prompt: str = "",
    dilate: int = 6,
    seed: int | None = None,
    steps: int | None = None,
    model: str | None = None,
) -> tuple[np.ndarray, str]:
    """Inpainting generativo (FLUX Fill). ``mask``: branco = preencher."""
    model = model or REPLICATE_MODEL_FILL
    h, w = bgr.shape[:2]
    img_ai, mask_ai, binary_full = _prepare(bgr, mask, dilate)
    if int(np.count_nonzero(mask_ai)) == 0:
        raise ValueError("Máscara vazia — detecte ou pinte a marca d'água antes.")

    inp = {"image": _data_uri(img_ai), "mask": _data_uri(mask_ai), "prompt": prompt or ""}
    if seed is not None:
        inp["seed"] = seed
    if steps is not None:
        inp["steps"] = steps

    arr = _decode_first(_call_model(model, inp))
    return _composite(arr, bgr, binary_full), f"flux-fill ({model.split('/')[-1]})"


def bria_erase(
    bgr: np.ndarray,
    mask: np.ndarray,
    dilate: int = 6,
    invert: bool = False,
    model: str | None = None,
) -> tuple[np.ndarray, str]:
    """Remoção pura (Bria Eraser). ``invert`` manda a máscara invertida (branco = apagar)."""
    model = model or REPLICATE_MODEL_ERASER
    img_ai, mask_ai, binary_full = _prepare(bgr, mask, dilate)
    if int(np.count_nonzero(mask_ai)) == 0:
        raise ValueError("Máscara vazia — detecte ou pinte a marca d'água antes.")

    sent_mask = (255 - mask_ai) if invert else mask_ai
    inp = {"image": _data_uri(img_ai), "mask": _data_uri(sent_mask)}
    arr = _decode_first(_call_model(model, inp))
    return _composite(arr, bgr, binary_full), f"bria-erase ({model.split('/')[-1]})"


# Retrocompat: wrapper antigo (usado pelo modo manual).
def remove_watermark_ai(bgr: np.ndarray, mask: np.ndarray, prompt: str = "", dilate: int = 6) -> tuple[np.ndarray, str]:
    return flux_fill(bgr, mask, prompt=prompt, dilate=dilate)
