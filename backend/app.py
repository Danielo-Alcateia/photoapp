"""PhotoApp - servidor Flask.

Serve o PWA (frontend/) e expõe três endpoints de edição cirúrgica,
todos NÃO-generativos em relação à identidade das pessoas:

    POST /api/inpaint   -> Remove Marca d'Água (LaMa / OpenCV Telea)
    POST /api/lighting  -> Melhora Iluminação (CLAHE + white balance)
    POST /api/upscale   -> Melhora Resolução (Real-ESRGAN / LANCZOS)

Execute:  python app.py   (ou  python -m flask --app app run)
"""
from __future__ import annotations

import importlib.util
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import (
    ALLOWED_EXTENSIONS,
    DEFAULT_UPSCALE,
    FRONTEND_DIR,
    INPAINT_LITTLE_RAM,
    MAX_CONTENT_LENGTH,
    MODELS_DIR,
    REPLICATE_MODEL,
    UPSCALE_LITTLE_RAM,
)
from image_io import decode_image, decode_mask, encode, limit_size
from processors import improve_lighting, improve_resolution, remove_watermark
from processors.ai_inpaint import ai_available, remove_watermark_ai
from processors.watermark import detect_watermark, encode_mask

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(
    app,
    expose_headers=[
        "X-Engine",
        "X-Width",
        "X-Height",
        "X-Watermark-Found",
        "X-Watermark-Boxes",
    ],
)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _get_image(field: str = "image"):
    if field not in request.files:
        raise ValueError(f"Campo '{field}' ausente no formulário.")
    bgr = decode_image(request.files[field])
    return limit_size(bgr)


def _out(bgr, engine: str, extra_headers: dict | None = None):
    fmt = request.form.get("format", "png")
    quality = int(request.form.get("quality", 92))
    data, mime = encode(bgr, fmt=fmt, quality=quality)
    resp = app.response_class(data, mimetype=mime)
    h, w = bgr.shape[:2]
    resp.headers["X-Engine"] = engine
    resp.headers["X-Width"] = str(w)
    resp.headers["X-Height"] = str(h)
    for key, value in (extra_headers or {}).items():
        resp.headers[key] = str(value)
    return resp


def _has(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "engines": {
                "inpaint": (
                    "opencv-telea"
                    if INPAINT_LITTLE_RAM
                    else ("lama" if _has("simple_lama_inpainting") else "opencv-telea-fallback")
                ),
                "lighting": "opencv-clahe",
                "upscale": (
                    f"lanczos-x{DEFAULT_UPSCALE}"
                    if UPSCALE_LITTLE_RAM
                    else ("realesrgan-rrdbnet" if _has("torch") else f"lanczos-x{DEFAULT_UPSCALE}-fallback")
                ),
            },
            "face_fidelity_policy": "enforced (generative face reconstruction forbidden)",
            "max_upload_mb": MAX_CONTENT_LENGTH // (1024 * 1024),
            "ai": {
                "available": ai_available(),
                "engine": REPLICATE_MODEL,
            },
        }
    )


@app.post("/api/detect-watermark")
def api_detect_watermark():
    """Detecta automaticamente a marca d'água e devolve a máscara em PNG.

    Cabeçalhos:
        X-Watermark-Found  -> "1" se encontrou, "0" caso contrário
        X-Watermark-Boxes  -> "x,y,w,h;x,y,w,h;..." (coordenadas originais)
    """
    try:
        img, _ = _get_image("image")
        mask, boxes, found = detect_watermark(img)

        headers = {
            "X-Engine": "watermark-detect",
            "X-Watermark-Found": "1" if found else "0",
            "X-Watermark-Boxes": ";".join(f"{x},{y},{bw},{bh}" for (x, y, bw, bh) in boxes),
        }
        return _out(encode_mask(mask), "watermark-detect", headers)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Falha ao detectar marca d'água: {exc}"}), 500


@app.post("/api/inpaint")
def api_inpaint():
    try:
        img, scale = _get_image("image")
        if "mask" not in request.files:
            raise ValueError("Campo 'mask' ausente. Pinte a marca d'água antes de aplicar.")
        mask = decode_mask(request.files["mask"], img.shape[:2])
        dilate = int(request.form.get("dilate", 6))
        if scale != 1.0:
            dilate = max(2, int(round(dilate * scale)))
        out, engine = remove_watermark(img, mask, dilate=dilate)
        return _out(out, engine)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Falha ao remover marca d'água: {exc}"}), 500


@app.post("/api/inpaint-ai")
def api_inpaint_ai():
    """Remoção com IA (FLUX.1 Fill via Replicate) — opcional e pago por uso."""
    try:
        if not ai_available():
            raise ValueError("Modo IA indisponível: defina REPLICATE_API_TOKEN no servidor.")
        img, _ = _get_image("image")
        if "mask" not in request.files:
            raise ValueError("Campo 'mask' ausente. Detecte ou pinte a marca d'água antes.")
        mask = decode_mask(request.files["mask"], img.shape[:2])
        prompt = request.form.get("prompt", "")
        out, engine = remove_watermark_ai(img, mask, prompt=prompt)
        return _out(out, engine)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Falha no modo IA: {exc}"}), 502


@app.post("/api/lighting")
def api_lighting():
    try:
        img, _ = _get_image("image")
        strength = float(request.form.get("strength", 1.0))
        out = improve_lighting(img, strength=strength)
        return _out(out, "opencv-clahe")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Falha ao melhorar iluminação: {exc}"}), 500


@app.post("/api/upscale")
def api_upscale():
    try:
        img, _ = _get_image("image")
        scale = int(request.form.get("scale", DEFAULT_UPSCALE))
        if scale not in (2, 4):
            scale = DEFAULT_UPSCALE
        out, engine = improve_resolution(img, scale=scale)
        return _out(out, engine)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Falha ao melhorar resolução: {exc}"}), 500


# ---------------------------------------------------------------------------
# PWA / arquivos estáticos
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    if (FRONTEND_DIR / path).is_file():
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    import threading

    port = int(os.environ.get("PORT", "8000"))

    # Pré-carrega LaMa e Real-ESRGAN em segundo plano (não bloqueia o servidor).
    # Os pesos já baixados tornam o primeiro uso instantâneo.
    # DESLIGADO por padrão na nuvem: em máquinas com pouca RAM (ex.: Render
    # Free = 512 MB) carregar os dois modelos de uma vez estoura a memória e
    # derruba o container. Ligue com PHOTOAPP_WARMUP=1 só onde houver memória.
    def _warmup():
        try:
            from processors.inpainting import get_lama
            from processors.upscale import get_model, ensure_weights

            get_lama()
            ensure_weights(int(os.environ.get("PHOTOAPP_UPSCALE", "2")))
            get_model(int(os.environ.get("PHOTOAPP_UPSCALE", "2")))
            print("[warmup] modelos LaMa + Real-ESRGAN prontos.")
        except Exception as exc:  # pragma: no cover
            print(f"[warmup] aviso (será carregado sob demanda): {exc}")

    if os.environ.get("PHOTOAPP_WARMUP", "0") == "1":
        threading.Thread(target=_warmup, daemon=True).start()

    print(f"\n  PhotoApp PWA  ->  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
