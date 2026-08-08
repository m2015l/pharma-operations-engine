#!/usr/bin/env python
"""
tools/extract_text.py — CLI de extração (camada 3 do WAT).

Invólucro fino: a lógica vive em `src/solufarma/extracao.py`.
Ver `workflows/ocr_escaneados.md` para quando e como rodar.

    uv run python tools/extract_text.py                    # data/brutos/ inteiro
    uv run python tools/extract_text.py data/brutos/x.pdf  # um documento
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from solufarma.cli import main_extrair

if __name__ == "__main__":
    raise SystemExit(main_extrair())
