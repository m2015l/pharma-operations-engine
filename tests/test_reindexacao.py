"""Reindexação de um documento: upsert + remoção de órfãos, só daquele documento_id."""

from __future__ import annotations

import pytest

from pharma_rag.db.repository import InMemoryChunkRepository, SupabaseChunkRepository
from pharma_rag.ingestion.embeddings import FakeEmbeddingProvider, gerar_embeddings_pendentes
from tests.falsos import ConexaoFalsa


def _lote(fazer_chunk, documento_id, n, prefixo="texto"):
    return [
        fazer_chunk(i, f"{prefixo} {i} com corpo suficiente para indexar",
                    documento_id=documento_id, content_hash=f"{prefixo}-{i}")
        for i in range(1, n + 1)
    ]


def test_memoria_remove_orfaos_so_do_documento(fazer_chunk):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(_lote(fazer_chunk, "doc-a", 3) + _lote(fazer_chunk, "doc-b", 3))

    removidos = repo.substituir_chunks_documento("doc-a", _lote(fazer_chunk, "doc-a", 2, "novo"))

    assert removidos == 1
    assert sorted(r.chunk.chave for r in repo._registros.values()) == [
        "doc-a:1", "doc-a:2", "doc-b:1", "doc-b:2", "doc-b:3",
    ]


def test_memoria_preserva_embedding_de_chunk_que_nao_mudou(fazer_chunk):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks(_lote(fazer_chunk, "doc-a", 2))
    gerar_embeddings_pendentes(repo, FakeEmbeddingProvider())

    novo = _lote(fazer_chunk, "doc-a", 1) + _lote(fazer_chunk, "doc-a", 2, "novo")[1:]
    repo.substituir_chunks_documento("doc-a", novo)

    # chunk 1 igual -> não pendente; chunk 2 mudou -> pendente
    assert [c.chave for c in repo.listar_pendentes()] == ["doc-a:2"]


@pytest.mark.parametrize("caso", ["vazio", "mistura", "repetido"])
def test_lote_invalido_e_recusado_antes_de_escrever(fazer_chunk, caso):
    lotes = {
        "vazio": [],
        "mistura": _lote(fazer_chunk, "doc-a", 1) + _lote(fazer_chunk, "doc-b", 1),
        "repetido": _lote(fazer_chunk, "doc-a", 1) * 2,
    }
    conn = ConexaoFalsa()
    with pytest.raises(ValueError):
        SupabaseChunkRepository(conn=conn).substituir_chunks_documento("doc-a", lotes[caso])
    assert conn.executados == []
    with pytest.raises(ValueError):
        InMemoryChunkRepository().substituir_chunks_documento("doc-a", lotes[caso])


def test_supabase_faz_upsert_e_delete_numa_transacao(fazer_chunk):
    conn = ConexaoFalsa(rowcount=4)
    repo = SupabaseChunkRepository(conn=conn)

    removidos = repo.substituir_chunks_documento("doc-a", _lote(fazer_chunk, "doc-a", 3))

    assert removidos == 4
    assert len(conn.sql("insert into doc_chunks")) == 3
    (sql, params), = conn.sql("delete from doc_chunks")
    assert "where documento_id = %s" in sql
    assert params == ("doc-a", [1, 2, 3])
    assert (conn.commits, conn.rollbacks) == (1, 0)


def test_supabase_rollback_se_o_delete_falhar(fazer_chunk):
    conn = ConexaoFalsa(erro_em="delete from doc_chunks")
    with pytest.raises(RuntimeError):
        SupabaseChunkRepository(conn=conn).substituir_chunks_documento(
            "doc-a", _lote(fazer_chunk, "doc-a", 2)
        )
    assert (conn.commits, conn.rollbacks) == (0, 1)


def test_upsert_simples_continua_sem_delete(fazer_chunk):
    conn = ConexaoFalsa()
    SupabaseChunkRepository(conn=conn).upsert_chunks(_lote(fazer_chunk, "doc-a", 2))
    assert not conn.sql("delete")
    assert conn.commits == 1
