"""Lotes de embeddings respeitam o teto de tokens da Voyage (120k por requisição)."""

from types import SimpleNamespace

from pharma_rag.ingestion.embeddings import _lotes


def _c(chars: int):
    return SimpleNamespace(conteudo="x" * chars)


def test_lote_corta_por_quantidade():
    assert [len(lote) for lote in _lotes([_c(10)] * 5, 2, 10_000)] == [2, 2, 1]


def test_lote_corta_por_tokens_estimados():
    chunks = [_c(4000)] * 6  # ~1000 tokens estimados cada
    assert all(len(lote) <= 2 for lote in _lotes(chunks, 100, 2_500))


def test_chunk_maior_que_o_teto_vai_sozinho():
    assert [len(lote) for lote in _lotes([_c(400_000), _c(10)], 100, 1_000)] == [1, 1]
