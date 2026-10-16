"""Testes da busca híbrida (vetorial + léxica fundidas por RRF)."""

from __future__ import annotations

from datetime import date

from pharma_rag.db.repository import FiltrosBusca
from pharma_rag.retrieval.hybrid_search import RRF_K, HybridSearcher, fundir_rrf


def test_rrf_soma_parcelas_dos_dois_rankings(fazer_chunk):
    a, b = fazer_chunk(0), fazer_chunk(1)

    fundido = fundir_rrf(ranking_vetorial=[a, b], ranking_lexico=[b, a])

    scores = {r.chunk.chave: r.score for r in fundido}
    esperado = 1 / (RRF_K + 1) + 1 / (RRF_K + 2)
    assert scores[a.chave] == esperado
    assert scores[b.chave] == esperado


def test_rrf_prioriza_chunk_presente_nos_dois_rankings(fazer_chunk):
    consenso, so_vetorial, so_lexico = fazer_chunk(0), fazer_chunk(1), fazer_chunk(2)

    fundido = fundir_rrf([consenso, so_vetorial], [consenso, so_lexico])

    assert fundido[0].chunk.chave == consenso.chave


def test_rrf_com_ranking_vazio_nao_quebra(fazer_chunk):
    a = fazer_chunk(0)

    assert fundir_rrf([a], []) [0].chunk.chave == a.chave
    assert fundir_rrf([], []) == []


def test_busca_encontra_chunk_por_termo_semantico(repo_indexado, provider):
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)

    resultados = searcher.buscar("autoclave", top_k=3)

    assert resultados
    assert any("autoclave" in r.chunk.conteudo.lower() for r in resultados)


def test_busca_respeita_top_k(repo_indexado, provider):
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)

    assert len(searcher.buscar("equipamentos", top_k=2)) <= 2


def test_filtro_por_tipo_documento_exclui_outros(repo_indexado, provider):
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)

    resultados = searcher.buscar("autoclave", FiltrosBusca(tipo_documento="ata"), top_k=5)

    assert resultados == [], "acervo do teste só tem edital — filtro deve zerar"


def test_filtro_por_orgao_ignora_acentos_e_caixa(repo_indexado, provider):
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)

    assert searcher.buscar("autoclave", FiltrosBusca(orgao="ses/go"), top_k=3)


def test_filtro_por_periodo(repo_indexado, provider):
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)

    dentro = searcher.buscar(
        "autoclave", FiltrosBusca(data_inicio=date(2023, 1, 1), data_fim=date(2023, 12, 31)), 3
    )
    fora = searcher.buscar("autoclave", FiltrosBusca(data_inicio=date(2024, 1, 1)), 3)

    assert dentro
    assert fora == []


def test_reranker_injetado_reordena_resultados(repo_indexado, provider):
    def inverter(consulta, candidatos):
        return list(reversed(candidatos))

    sem_rerank = HybridSearcher(repo=repo_indexado, provider=provider).buscar("edital", top_k=5)
    com_rerank = HybridSearcher(
        repo=repo_indexado, provider=provider, reranker=inverter
    ).buscar("edital", top_k=5)

    assert [r.chunk.chave for r in com_rerank] != [r.chunk.chave for r in sem_rerank]


def test_busca_em_acervo_vazio_retorna_lista_vazia(provider):
    from pharma_rag.db.repository import InMemoryChunkRepository

    searcher = HybridSearcher(repo=InMemoryChunkRepository(), provider=provider)

    assert searcher.buscar("qualquer coisa") == []
