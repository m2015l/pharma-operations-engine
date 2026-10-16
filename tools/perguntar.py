"""Faz uma pergunta ao acervo — o CLI que fecha o ciclo do RAG.

Uso:
    python tools/perguntar.py "a Pharma Operations Platform já implantou laboratório?"
    python tools/perguntar.py "..." --orgao "Instituto BioPharma"    # com filtro
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

from pharma_rag.agent.agent import AgenteLicitacoes
from pharma_rag.agent.llm import criar_llm
from pharma_rag.db.repository import (
    FiltrosBusca,
    SupabaseChunkRepository,
    criar_conexao,
)
from pharma_rag.ingestion.embeddings import criar_provedor
from pharma_rag.retrieval.hybrid_search import HybridSearcher

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")



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


def _mostrar_resposta(agente: AgenteLicitacoes, pergunta: str, historico: list[dict] | None = None):
    resposta = agente.responder(pergunta, historico=historico)

    print("\n" + "=" * 70)
    print(resposta.texto)
    print("=" * 70)

    if not resposta.encontrou_no_acervo:
        print("\n(nada encontrado no acervo — o agente NÃO respondeu por conhecimento geral)")
        return resposta

    # I10 (PRECISÃO.md): chunks diferentes que compartilham seção e página
    # ficam com a mesma linha ("Instituto BioPharma · · p.1-2" três vezes, turno 3.5)
    # — sem discriminador é indistinguível de bug, mesmo não sendo. O início
    # do trecho (já truncado em Citacao.trecho) desempata visualmente.
    identidades = [
        f"{c.orgao}·{c.secao}·p.{c.pagina_inicio}-{c.pagina_fim}" for c in resposta.citacoes
    ]
    repetidas = {ident for ident in identidades if identidades.count(ident) > 1}

    print(f"\nFontes ({len(resposta.citacoes)}):")
    for c, ident in zip(resposta.citacoes, identidades, strict=True):
        linha = f"  [{c.marcador}] {c.orgao} · {c.secao} · p.{c.pagina_inicio}-{c.pagina_fim}"
        if ident in repetidas:
            discriminador = " ".join(c.trecho.split())[:40].strip()
            linha += f' — "{discriminador}…"'
        print(linha)

    # Os "buracos" na numeração ([1],[3],[5]) são extrair_citacoes mostrando só
    # o que foi citado — comportamento correto, não bug (ver PRECISÃO.md I10).
    # Esta linha transforma o que parecia um bug em informação de calibração:
    # quantos trechos entraram no contexto vs. quantos o modelo usou de fato.
    print(
        f"\nFontes: {len(resposta.citacoes)} citadas de {resposta.trechos_recuperados} "
        "trechos recuperados"
    )

    # O contrato de rastreabilidade é o requisito central do produto: resposta
    # sem fonte não é resposta boa, é resposta perigosa. Falha alto, não em log.
    if not resposta.contrato_citacao_ok:
        print("\n*** ATENÇÃO: contrato de citação violado ***")
        if resposta.citacoes_invalidas:
            print(f"    marcadores inexistentes citados: {resposta.citacoes_invalidas}")
        else:
            print("    o agente respondeu sem citar nenhuma fonte")
        print("    NÃO trate esta resposta como confiável.")

    return resposta


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pergunta", nargs="?", help="A pergunta. Sem isto, entra em modo interativo")
    p.add_argument("--orgao", default=None, help="Filtra por órgão")
    p.add_argument("--tipo", default=None, help="Filtra por tipo de documento")
    p.add_argument("--top-k", type=int, default=8, help="Trechos no contexto (padrão 8)")
    p.add_argument("--so-busca", action="store_true", help="Só o retrieval, sem chamar o LLM")
    p.add_argument("--provedor", default=None, help="voyage | openai | fake")
    return p


def montar_filtros(orgao: str | None, tipo: str | None) -> FiltrosBusca:
    """Só os filtros informados — campo vazio não pode virar filtro que zera a busca."""
    brutos = {k: v for k, v in (("orgao", orgao), ("tipo_documento", tipo)) if v}
    return FiltrosBusca.model_validate(brutos)


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        provider = criar_provedor(args.provedor)
    except (ImportError, RuntimeError, ValueError) as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    filtros = montar_filtros(args.orgao, args.tipo)

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
                agente = AgenteLicitacoes(
                    searcher=searcher, llm=criar_llm(), top_k=args.top_k, repo_itens=repo
                )
            except (ImportError, RuntimeError, ValueError) as exc:
                print(f"\nLLM indisponível ({exc}).\nCaindo para --so-busca.\n", file=sys.stderr)

        perguntas = [args.pergunta] if args.pergunta else None
        # Histórico só faz sentido em modo interativo (I8, PRECISÃO.md): uma
        # única pergunta por execução não tem turno anterior para reescrever
        # referência ("e a área disso", "aquilo lá"). Acumula pares
        # pergunta/resposta na mesma forma que AgenteLicitacoes.responder espera.
        historico: list[dict] = []
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
                resposta = _mostrar_resposta(agente, pergunta, historico=historico or None)
                if resposta is not None:
                    historico.append({"pergunta": pergunta, "resposta": resposta.texto})

            if perguntas is not None and not perguntas:
                break
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
