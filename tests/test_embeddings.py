"""Testes do pipeline incremental de embeddings (workflows/geracao_embeddings.md)."""

from __future__ import annotations

import pytest

from solufarma_rag.db.repository import InMemoryChunkRepository
from solufarma_rag.ingestion.chunking import gerar_chunks
from solufarma_rag.ingestion.embeddings import (
    FakeEmbeddingProvider,
    gerar_embeddings_pendentes,
)


def test_embedda_todos_os_chunks_pendentes(documento, provider):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))

    relatorio = gerar_embeddings_pendentes(repo, provider)

    assert relatorio.embeddados == repo.total_chunks()
    assert relatorio.total_pendentes == repo.total_chunks()
    assert repo.listar_pendentes() == []


def test_segunda_execucao_nao_reembedda_nada(documento, provider):
    """Incremental: sem mudança de conteúdo, nenhuma chamada nova ao provedor."""
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))
    gerar_embeddings_pendentes(repo, provider)

    relatorio = gerar_embeddings_pendentes(repo, provider)

    assert relatorio.total_pendentes == 0
    assert relatorio.embeddados == 0
    assert relatorio.lotes == 0


def test_apenas_chunk_alterado_e_reembeddado(documento, provider):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))
    gerar_embeddings_pendentes(repo, provider)

    documento.paginas[0].texto = documento.paginas[0].texto.replace(
        "centrífuga laboratorial refrigerada", "centrífuga laboratorial de bancada"
    )
    repo.upsert_chunks(gerar_chunks(documento))
    relatorio = gerar_embeddings_pendentes(repo, provider)

    assert 0 < relatorio.embeddados < repo.total_chunks(), (
        "só os chunks tocados deveriam ser reembeddados"
    )


def test_registra_modelo_de_embedding_por_chunk(documento, provider):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))

    gerar_embeddings_pendentes(repo, provider)

    chave = gerar_chunks(documento)[0].chave
    registro = repo.obter_registro(chave)
    assert registro.embedding_model == provider.model_id
    assert len(registro.embedding) == provider.dimensions


def test_marca_documento_como_indexado(documento, provider):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))

    relatorio = gerar_embeddings_pendentes(repo, provider)

    assert "doc-001" in repo.documentos_indexados
    assert relatorio.documentos_indexados == ["doc-001"]


def test_pula_chunk_que_e_ruido_de_ocr(documento, provider):
    """Página de carimbos vira chunk minúsculo — não deve poluir o índice."""
    repo = InMemoryChunkRepository()
    chunks = gerar_chunks(documento)
    ruido = chunks[0].model_copy(
        update={
            "chunk_index": 999,
            "conteudo": "[Edital PE 045/2023 – SES/GO – Seção: X]\nfl. 12",
            "content_hash": "hash-ruido",
        }
    )
    repo.upsert_chunks(chunks + [ruido])

    relatorio = gerar_embeddings_pendentes(repo, provider)

    assert relatorio.pulados_ruido == 1
    assert relatorio.embeddados == len(chunks)


def test_respeita_tamanho_do_lote(documento, provider):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))
    total = repo.total_chunks()

    relatorio = gerar_embeddings_pendentes(repo, provider, tamanho_lote=1)

    assert relatorio.lotes == total


def test_falha_se_provedor_devolve_dimensao_errada(documento):
    """Nunca misturar modelos/dimensões no mesmo índice — deve explodir cedo."""

    class ProvedorInconsistente(FakeEmbeddingProvider):
        def embed_batch(self, textos):
            return [[0.1, 0.2] for _ in textos]  # devolve dimensão 2, mas declara 1024

    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))

    with pytest.raises(RuntimeError, match="dimensão"):
        gerar_embeddings_pendentes(repo, ProvedorInconsistente())


def test_embedding_do_fake_e_deterministico():
    """Vetores idênticos entre execuções/processos (SHA-256, não hash())."""
    p1, p2 = FakeEmbeddingProvider(), FakeEmbeddingProvider()

    assert p1.embed_batch(["autoclave hospitalar"]) == p2.embed_batch(["autoclave hospitalar"])
