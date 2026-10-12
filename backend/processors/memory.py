"""Controle de memória para o plano free do Render (512 MB).

No free, torch + LaMa + Real-ESRGAN residentes ao mesmo tempo estouram a RAM
e o container é morto na hora (oomKilled 512Mi). Para resolver, garante-se que
apenas UM modelo de rede neural fique residente por vez: ao carregar um motor,
os demais são descarregados (evicted). Os pesos ficam em disco
(backend/models/) e recarregam sob demanda, sem re-baixar.
"""
from __future__ import annotations

import gc
import threading

_lock = threading.Lock()
_evictors: dict[str, callable] = {}


def register(engine: str, evictor) -> None:
    """Registra a função que libera o modelo pesado de um motor."""
    with _lock:
        _evictors[engine] = evictor


def evict(keep: str | None = None) -> None:
    """Descarrega todos os modelos pesados exceto ``keep``."""
    with _lock:
        for engine, evictor in list(_evictors.items()):
            if engine == keep:
                continue
            try:
                evictor()
            except Exception:
                pass
    gc.collect()