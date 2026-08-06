"""Testes do Retriever LangChain sobre a busca híbrida (ADR-005, opção B).

Rodam offline: usam o repositório em memória e o provedor fake, sem Supabase e
sem chave de API. O que importa aqui é a fronteira — o que atravessa do nosso
domínio para o `Document` do LangChain, e se a rastreabilidade sobrevive a ela.
"""

from __future__ import annotations

from datetime import date

from solufarma_rag.db.models import Chunk, ChunkComScore
from solufarma_rag.db.repository import FiltrosBusca
from solufarma_rag.retrieval.hybrid_search import HybridSearcher
from solufarma_rag.retrieval.langchain_retriever import (
    SolufarmaRetriever,
    chunk_para_documento,
)


def test_documento_carrega_metadados_de_citacao(fazer_chunk):
    """Sem estes metadados a citação [n] → documento → página morre na fronteira."""
    chunk = fazer_chunk(3, "conteúdo do chunk", pagina_inicio=4, pagina_fim=5)
    doc = chunk_para_documento(ChunkComScore(chunk=chunk, score=0.42))

    assert doc.page_content == "conteúdo do chunk"
    assert doc.metadata["chunk_chave"] == "doc-001:3"
    assert doc.metadata["documento_id"] == "doc-001"
    assert doc.metadata["pagina_inicio"] == 4
    assert doc.metadata["pagina_fim"] == 5
    assert doc.metadata["secao"] == "1. DO OBJETO"
    assert doc.metadata["score"] == 0.42


def test_data_vira_iso_ou_none(fazer_chunk):
    """Metadado de Document precisa ser serializável — date não é."""
    com_data = chunk_para_documento(
        ChunkComScore(chunk=fazer_chunk(0, data=date(2023, 5, 10)), score=1.0)
    )
    sem_data = chunk_para_documento(ChunkComScore(chunk=fazer_chunk(1), score=1.0))

    assert com_data.metadata["data"] == "2023-05-10"
    assert sem_data.metadata["data"] is None


def test_invoke_devolve_documentos_do_acervo(repo_indexado, provider):
    """Caminho completo: invoke() do LangChain → busca híbrida → Documents."""
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)
    retriever = SolufarmaRetriever(searcher=searcher, top_k=3)

    docs = retriever.invoke("autoclave horizontal esterilização")

    assert 0 < len(docs) <= 3
    assert any("autoclave" in d.page_content.lower() for d in docs)
    assert all(d.metadata["documento_id"] == "doc-001" for d in docs)


def test_respeita_top_k(repo_indexado, provider):
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)
    assert len(SolufarmaRetriever(searcher=searcher, top_k=1).invoke("autoclave")) == 1


def test_repassa_filtros_ao_searcher(repo_indexado, provider):
    """Filtro que não casa deve zerar o resultado — prova que ele chega na busca."""
    searcher = HybridSearcher(repo=repo_indexado, provider=provider)
    retriever = SolufarmaRetriever(
        searcher=searcher, filtros=FiltrosBusca(orgao="Órgão Inexistente")
    )

    assert retriever.invoke("autoclave") == []


def test_acervo_vazio_devolve_lista_vazia(provider):
    """O agente depende disso para dizer 'não encontrei' em vez de inventar."""
    from solufarma_rag.db.repository import InMemoryChunkRepository

    searcher = HybridSearcher(repo=InMemoryChunkRepository(), provider=provider)
    assert SolufarmaRetriever(searcher=searcher).invoke("qualquer coisa") == []


def test_aceita_qualquer_searcher_com_buscar(fazer_chunk):
    """`searcher` é Protocol: um stub simples precisa servir, sem herdar de nada."""

    class SearcherStub:
        def buscar(self, consulta, filtros=None, top_k=5):
            return [ChunkComScore(chunk=fazer_chunk(0, "resultado do stub"), score=1.0)]

    docs = SolufarmaRetriever(searcher=SearcherStub()).invoke("pergunta")
    assert [d.page_content for d in docs] == ["resultado do stub"]


def test_chunk_completo_sobrevive_ao_round_trip(fazer_chunk):
    """O Document precisa bastar para remontar a citação sem voltar ao banco."""
    chunk: Chunk = fazer_chunk(7, "texto", orgao="SES/GO", tipo_documento="ata")
    meta = chunk_para_documento(ChunkComScore(chunk=chunk, score=0.1)).metadata

    assert meta["orgao"] == "SES/GO"
    assert meta["tipo_documento"] == "ata"
    assert meta["chunk_index"] == 7
