"""Reranker Voyage: reordenação, piso próprio e queda para o RRF em falha."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from solufarma_rag.db.models import ChunkComScore
from solufarma_rag.retrieval.hybrid_search import HybridSearcher
from solufarma_rag.retrieval.reranker import VoyageReranker, criar_reranker


class ClienteFalso:
    """Imita voyageai.Client.rerank: pontua pelo nº de palavras da consulta no texto."""

    def __init__(self, falhar: bool = False):
        self.falhar = falhar
        self.chamadas: list[tuple[str, list[str]]] = []

    def rerank(self, query, documents, model, truncation=True):
        self.chamadas.append((query, documents))
        if self.falhar:
            raise RuntimeError("503 Service Unavailable")
        termos = set(query.lower().split())
        resultados = [
            SimpleNamespace(
                index=i, relevance_score=len(termos & set(d.lower().split())) / max(len(termos), 1)
            )
            for i, d in enumerate(documents)
        ]
        # A API devolve ordenado; embaralhar prova que o código não depende disso.
        return SimpleNamespace(results=list(reversed(resultados)), total_tokens=0)


def _candidatos(fazer_chunk, textos):
    return [
        ChunkComScore(chunk=fazer_chunk(i, t), score=1.0 / (60 + i + 1))
        for i, t in enumerate(textos)
    ]


def test_reordena_pelo_score_do_reranker(fazer_chunk):
    cands = _candidatos(fazer_chunk, ["pintura do piso", "gases especiais nitrogênio"])
    saida = VoyageReranker(client=ClienteFalso())("gases especiais", cands)

    assert [r.chunk.chunk_index for r in saida] == [1, 0]
    assert saida[0].score == 1.0


def test_falha_da_api_devolve_ordem_rrf_com_aviso(fazer_chunk, caplog):
    cands = _candidatos(fazer_chunk, ["a", "b", "c"])
    with caplog.at_level(logging.WARNING):
        saida = VoyageReranker(client=ClienteFalso(falhar=True))("x", cands)

    assert saida == cands
    assert "ordem do RRF" in caplog.text


def test_piso_do_reranker_descarta_trechos_fracos(fazer_chunk):
    cands = _candidatos(fazer_chunk, ["gases especiais", "gases", "nada a ver"])
    saida = VoyageReranker(client=ClienteFalso(), piso=0.5)("gases especiais", cands)

    assert [r.chunk.chunk_index for r in saida] == [0, 1]


def test_lista_vazia_nao_chama_api():
    cliente = ClienteFalso()
    assert VoyageReranker(client=cliente)("x", []) == []
    assert cliente.chamadas == []


def test_interruptor_nenhum_desliga(monkeypatch):
    monkeypatch.setenv("RERANKER", "nenhum")
    assert criar_reranker() is None


def test_voyage_sem_chave_nao_derruba(monkeypatch):
    monkeypatch.setenv("RERANKER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    assert criar_reranker() is None


def test_searcher_manda_so_o_pool_de_rerank(repo_indexado, provider):
    cliente = ClienteFalso()
    searcher = HybridSearcher(
        repo=repo_indexado,
        provider=provider,
        reranker=VoyageReranker(client=cliente),
        candidatos_rerank=2,
    )
    searcher.buscar("edital autoclave", top_k=1)

    assert len(cliente.chamadas) == 1
    assert len(cliente.chamadas[0][1]) <= 2


def test_searcher_padrao_respeita_interruptor(repo_indexado, provider):
    # conftest fixa RERANKER=nenhum: o padrão tem de sair sem reranker.
    assert HybridSearcher(repo=repo_indexado, provider=provider).reranker is None
