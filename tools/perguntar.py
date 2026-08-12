"""Faz uma pergunta ao acervo — o CLI que fecha o ciclo do RAG.

Uso:
    python tools/perguntar.py "a Solufarma já implantou laboratório?"
    python tools/perguntar.py "..." --orgao "SENAI CETIQT"    # com filtro
    python tools/perguntar.py "..." --so-busca                # sem LLM, sem custo
    python tools/perguntar.py                                 # modo interativo

Amarra as três peças que já existiam mas nunca tinham sido ligadas:

    SupabaseChunkRepository  →  HybridSearcher  →  AgenteLicitacoes
        (banco real)            (vetorial+léxica)   (responde com citação)

`--so-busca` é o modo mais útil para calibrar: mostra QUAIS trechos a busca
recuperou e com que score, sem gastar token de LLM. Quando a resposta vem ruim,
é aqui que se descobre se o problema foi o retrieval ou o modelo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from solufarma_rag.agent.agent import AgenteLicitacoes  # noqa: E402
from solufarma_rag.agent.llm import criar_llm  # noqa: E402
from solufarma_rag.db.repository import (  # noqa: E402
    FiltrosBusca,
    SupabaseChunkRepository,
    criar_conexao,
)
from solufarma_rag.ingestion.embeddings import criar_provedor  # noqa: E402
from solufarma_rag.retrieval.hybrid_search import HybridSearcher  # noqa: E402


def _mostrar_busca(searcher: HybridSearcher, pergunta: str, filtros: FiltrosBusca, top_k: int):
    resultados = searcher.buscar(pergunta, filtros, top_k)
    if not resultados:
        print("\nNenhum trecho atingiu o piso de relevância.")
        print(
            "Se isso se repetir para perguntas que DEVERIAM ter resposta, o piso\n"
            "SIMILARIDADE_MINIMA_PADRAO (retrieval/hybrid_search.py) está calibrado\n"
            "para o provedor fake e precisa ser reajustado ao modelo real."
        )
        return resultados

    print(f"\n{len(resultados)} trechos recuperados:\n")
    for n, r in enumerate(resultados, start=1):
        c = r.chunk
        corpo = " ".join(c.conteudo.split())
        print(f"[{n}] score={r.score:.5f}  p.{c.pagina_inicio}-{c.pagina_fim}")
        print(f"    seção: {c.secao}")
        print(f"    {corpo[:220]}…\n")
    return resultados


def _mostrar_resposta(agente: AgenteLicitacoes, pergunta: str) -> None:
    resposta = agente.responder(pergunta)

    print("\n" + "=" * 70)
    print(resposta.texto)
    print("=" * 70)

    if not resposta.encontrou_no_acervo:
        print("\n(nada encontrado no acervo — o agente NÃO respondeu por conhecimento geral)")
        return

    print(f"\nFontes ({len(resposta.citacoes)}):")
    for c in resposta.citacoes:
        print(f"  [{c.marcador}] {c.orgao} · {c.secao} · p.{c.pagina_inicio}-{c.pagina_fim}")

    # O contrato de rastreabilidade é o requisito central do produto: resposta
    # sem fonte não é resposta boa, é resposta perigosa. Falha alto, não em log.
    if not resposta.contrato_citacao_ok:
        print("\n*** ATENÇÃO: contrato de citação violado ***")
        if resposta.citacoes_invalidas:
            print(f"    marcadores inexistentes citados: {resposta.citacoes_invalidas}")
        else:
            print("    o agente respondeu sem citar nenhuma fonte")
        print("    NÃO trate esta resposta como confiável.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pergunta", nargs="?", help="A pergunta. Sem isto, entra em modo interativo")
    p.add_argument("--orgao", default=None, help="Filtra por órgão")
    p.add_argument("--tipo", default=None, help="Filtra por tipo de documento")
    p.add_argument("--top-k", type=int, default=5, help="Trechos no contexto (padrão 5)")
    p.add_argument("--so-busca", action="store_true", help="Só o retrieval, sem chamar o LLM")
    p.add_argument("--provedor", default=None, help="voyage | openai | fake")
    args = p.parse_args()

    try:
        provider = criar_provedor(args.provedor)
    except (ImportError, RuntimeError, ValueError) as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    filtros_brutos = {k: v for k, v in (("orgao", args.orgao), ("tipo_documento", args.tipo)) if v}
    filtros = FiltrosBusca.model_validate(filtros_brutos)

    conn = criar_conexao()
    try:
        repo = SupabaseChunkRepository(conn=conn)

        # Aviso antecipado: sem embedding no banco, o ramo vetorial devolve vazio
        # e a busca vira só léxica — o sintoma é "achou pouco", não um erro.
        pendentes = len(repo.listar_pendentes())
        if pendentes:
            print(
                f"AVISO: {pendentes} chunks sem embedding. A busca vetorial não vai\n"
                f"       encontrá-los. Rode tools/generate_embeddings.py antes.\n"
            )

        searcher = HybridSearcher(repo=repo, provider=provider)
        print(f"Provedor: {provider.model_id}")

        agente = None
        if not args.so_busca:
            try:
                agente = AgenteLicitacoes(searcher=searcher, llm=criar_llm(), top_k=args.top_k)
            except (ImportError, RuntimeError, ValueError) as exc:
                print(f"\nLLM indisponível ({exc}).\nCaindo para --so-busca.\n", file=sys.stderr)

        perguntas = [args.pergunta] if args.pergunta else None
        while True:
            if perguntas is None:
                try:
                    pergunta = input("\npergunta> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not pergunta or pergunta in ("sair", "exit", "quit"):
                    break
            else:
                if not perguntas:
                    break
                pergunta = perguntas.pop(0)

            if agente is None:
                _mostrar_busca(searcher, pergunta, filtros, args.top_k)
            else:
                _mostrar_resposta(agente, pergunta)

            if perguntas is not None and not perguntas:
                break
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
