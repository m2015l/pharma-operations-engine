"""CLI do pipeline de embeddings — executa workflows/geracao_embeddings.md.

Uso:
    python tools/generate_embeddings.py --dry-run
    python tools/generate_embeddings.py --lote 100

Enquanto o Supabase não estiver provisionado (frente de Dados & Infraestrutura),
apenas `--dry-run` funciona: ele roda o pipeline completo contra o repositório em
memória com o provedor fake, servindo como smoke test offline da lógica.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from solufarma_rag.db.repository import InMemoryChunkRepository
from solufarma_rag.ingestion.embeddings import (
    FakeEmbeddingProvider,
    gerar_embeddings_pendentes,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("generate_embeddings")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Roda contra repositório em memória + provedor fake (sem rede, sem custo)",
    )
    parser.add_argument("--lote", type=int, default=100, help="Chunks por chamada de API")
    args = parser.parse_args()

    if not args.dry_run:
        logger.error(
            "Execução real indisponível: o Supabase ainda não foi provisionado e a "
            "OPENAI_API_KEY não está configurada. Use --dry-run por enquanto."
        )
        return 1

    repo = InMemoryChunkRepository()
    relatorio = gerar_embeddings_pendentes(repo, FakeEmbeddingProvider(), tamanho_lote=args.lote)
    logger.info("Relatório: %s", relatorio.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
