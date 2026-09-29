"""CLI do pipeline de embeddings — executa workflows/geracao_embeddings.md.

Uso:
    python tools/generate_embeddings.py --dry-run          # offline, fake, sem custo
    python tools/generate_embeddings.py                    # provedor do .env, banco real
    python tools/generate_embeddings.py --provedor openai  # força um provedor
    python tools/generate_embeddings.py --reset            # zera e reembedda tudo
    python tools/generate_embeddings.py --documento-id UUID --sim   # só um documento

CUSTO
A execução real chama API paga por token. O acervo inteiro projetado (40
documentos, ~1,28M tokens) custa US$ 0,00 na Voyage (200M tokens grátis) e
~US$ 0,17 na OpenAI. É barato, mas não é zero: `--dry-run` continua sendo o
jeito de exercitar a lógica sem gastar nada.

O CLI imprime quantos chunks serão embeddados e pede confirmação antes de
gastar, a menos que receba `--sim`.

SOBRE `--reset`
`listar_pendentes` marca um chunk como pendente por `embedding is null` ou por
mudança de `content_hash`. Trocar de MODELO não mexe em nenhum dos dois — então
sem `--reset` uma troca de provedor não reembedda nada e a busca passa a
comparar vetores de modelos diferentes no mesmo índice, o que corrompe o
ranking em silêncio. `--reset` zera a coluna e força o reprocessamento.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from solufarma_rag.db.repository import InMemoryChunkRepository
from solufarma_rag.ingestion.embeddings import (
    FakeEmbeddingProvider,
    RepoRestrito,
    criar_provedor,
    gerar_embeddings_pendentes,
)

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("generate_embeddings")


def _zerar_embeddings(conn) -> int:
    """Apaga os embeddings existentes. Devolve quantas linhas foram afetadas."""
    with conn.cursor() as cur:
        cur.execute(
            """
            update doc_chunks
               set embedding = null,
                   embedding_model = null,
                   embedding_content_hash = null
             where embedding is not null
            """
        )
        afetadas = cur.rowcount
    conn.commit()
    return afetadas


# `RepoRestrito` (o --documento-id) mora em solufarma_rag.ingestion.embeddings,
# importado acima: o upload da API usa o mesmo invólucro.


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Roda contra repositório em memória + provedor fake (sem rede, sem custo)",
    )
    parser.add_argument("--lote", type=int, default=100, help="Chunks por chamada de API")
    parser.add_argument(
        "--provedor",
        default=None,
        help="voyage | openai | fake. Padrão: EMBEDDING_PROVIDER do .env",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Zera os embeddings existentes antes (necessário ao trocar de modelo)",
    )
    parser.add_argument("--sim", action="store_true", help="Não pedir confirmação")
    parser.add_argument(
        "--documento-id",
        action="append",
        default=None,
        metavar="UUID",
        help="Só embedda chunks destes documentos (repetível). Não combina com --reset",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.reset and args.documento_id:
        parser.error("--reset zera o acervo inteiro; não combina com --documento-id")

    if args.dry_run:
        repo = InMemoryChunkRepository()
        relatorio = gerar_embeddings_pendentes(
            repo, FakeEmbeddingProvider(), tamanho_lote=args.lote
        )
        logger.info("Relatório: %s", relatorio.model_dump_json(indent=2))
        return 0

    from solufarma_rag.db.repository import SupabaseChunkRepository, criar_conexao

    try:
        provider = criar_provedor(args.provedor)
    except (ImportError, RuntimeError, ValueError) as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    conn = criar_conexao()
    try:
        if args.reset:
            zeradas = _zerar_embeddings(conn)
            print(f"--reset: {zeradas} embeddings apagados.")

        repo = SupabaseChunkRepository(conn=conn)
        if args.documento_id:
            repo = RepoRestrito(repo, set(args.documento_id))
            print(f"Restrito a {len(args.documento_id)} documento(s).")
        pendentes = repo.listar_pendentes()
        tokens = sum(c.token_count for c in pendentes)

        print(f"\nProvedor : {provider.model_id}  ({provider.dimensions} dimensões)")
        print(f"Pendentes: {len(pendentes)} chunks  (~{tokens:,} tokens)")

        if not pendentes:
            print("\nNada a fazer. Use --reset para reembeddar do zero.")
            return 0

        if not args.sim:
            resposta = input("\nGerar embeddings? Isto chama a API paga. [s/N] ").strip().lower()
            if resposta not in ("s", "sim", "y", "yes"):
                print("Cancelado. Nada foi gasto.")
                return 0

        relatorio = gerar_embeddings_pendentes(repo, provider, tamanho_lote=args.lote)
        print()
        logger.info("Relatório: %s", relatorio.model_dump_json(indent=2))

        restantes = len(repo.listar_pendentes())
        print(f"\nAinda pendentes: {restantes}")
        if restantes == 0:
            print("Acervo vetorizado. Próximo passo: tools/perguntar.py")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
