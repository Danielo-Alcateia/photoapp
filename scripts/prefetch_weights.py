# Pré-busca os pesos dos modelos para "assar" na imagem Docker (build time).
# Assim o primeiro acesso no servidor é rápido, sem baixar 200MB na hora.
#
# Uso:
#   python scripts/prefetch_weights.py
#
# Requer torch + simple-lama-inpainting instalados.
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Garante cache determinístico para o LaMa (torch hub).
os.environ.setdefault("TORCH_HOME", str(ROOT / "backend" / "models" / "torch"))
os.environ.setdefault("HOME", str(ROOT / "backend" / "models"))

print("[prefetch] LaMa (big-lama.pt)...", flush=True)
from simple_lama_inpainting import SimpleLama  # noqa: E402

SimpleLama()

print("[prefetch] Real-ESRGAN x2...", flush=True)
from processors.upscale import ensure_weights  # noqa: E402

ensure_weights(2)

print("[prefetch] pesos prontos.", flush=True)