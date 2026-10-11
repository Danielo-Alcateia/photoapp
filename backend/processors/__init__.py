"""Processadores de imagem do PhotoApp.

Todos os processadores são ESTRITAMENTE não-generativos em relação à
identidade da pessoa:
  * inpainting -> apenas texturas/vizinhança da própria foto (LaMa ou Telea);
  * iluminação  -> matemática de histograma/exposição com OpenCV;
  * resolução   -> Real-ESRGAN (nítidez de textura) ou LANCZOS+unsharp.
"""
from .lighting import improve_lighting
from .inpainting import remove_watermark
from .upscale import improve_resolution

__all__ = ["improve_lighting", "remove_watermark", "improve_resolution"]
