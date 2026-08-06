"""Utilidades de texto compartilhadas entre ingestão e retrieval.

Vivem aqui — e não dentro de `db/repository.py` — porque são usadas tanto pela
busca textual em memória quanto pelo provedor fake de embeddings. Enquanto eram
privadas do repositório, uma mudança na tokenização da busca alterava
silenciosamente os vetores do provedor fake.

A normalização espelha o que o Postgres faz na busca full-text
(`unaccent` + minúsculas), para que o repositório em memória tenha a mesma
semântica do banco real.
"""

from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos — espelha o `unaccent` do Postgres."""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenizar(texto: str) -> list[str]:
    """Tokenização simples por palavras (≥2 caracteres alfanuméricos), sem acentos."""
    return re.findall(r"[a-z0-9]{2,}", normalizar(texto))
