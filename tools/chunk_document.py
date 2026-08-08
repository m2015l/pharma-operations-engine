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

if __name__ == "__main__":
    raise SystemExit(main_chunks())
