#!/usr/bin/env python
"""
tools/chunk_document.py — CLI de chunking (camada 3 do WAT).

Invólucro fino: a lógica vive em `src/solufarma/chunking.py`.
Não faz chamada paga — pode rodar quantas vezes quiser.

    uv run python tools/chunk_document.py                       # data/extraidos/
    uv run python tools/chunk_document.py data/extraidos/x.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from solufarma.cli import main_chunks

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main_chunks())
