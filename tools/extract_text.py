#!/usr/bin/env python
"""
tools/extract_text.py — CLI de extração (camada 3 do WAT).

Invólucro fino: a lógica vive em `src/pharma_ops/extracao.py`.
Ver `workflows/ocr_escaneados.md` para quando e como rodar.

    uv run python tools/extract_text.py                    # data/brutos/ inteiro
    uv run python tools/extract_text.py data/brutos/x.pdf  # um documento
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pharma_ops.cli import main_extrair

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main_extrair())
