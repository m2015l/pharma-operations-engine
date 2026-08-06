"""Repositórios de chunks: protocolo injetável + implementação em memória.

O Supabase real ainda não tem credenciais provisionadas (frente de Dados &
Infraestrutura). Por isso a camada de acesso a banco é um Protocol: o pipeline
de embeddings e a busca híbrida funcionam contra qualquer implementação —
`InMemoryChunkRepository` nos testes/desenvolvimento, `SupabaseChunkRepository`
quando o banco estiver provisionado (DDL em docs/ARQUITETURA.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from pydantic import BaseModel

from ..text_utils import normalizar as _normalizar
from ..text_utils import tokenizar as _tokenizar
from .models import Chunk


class FiltrosBusca(BaseModel):
    """Filtros por metadados aplicados ANTES do ranking (ARQUITETURA.md §5.1)."""

    orgao: str | None = None
    tipo_documento: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None

    def aceita(self, chunk: Chunk) -> bool:
        """Verifica se um chunk passa nos filtros (usado pelo repositório em memória)."""
        if self.tipo_documento and chunk.tipo_documento != self.tipo_documento:
            return False
        if self.orgao and _normalizar(self.orgao) not in _normalizar(chunk.orgao):
            return False
        if self.data_inicio and (chunk.data is None or chunk.data < self.data_inicio):
            return False
        if self.data_fim and (chunk.data is None or chunk.data > self.data_fim):
            return False
        return True


class ChunkRepository(Protocol):
    """Contrato mínimo que o pipeline de embeddings e a busca híbrida exigem."""

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        """Insere/atualiza chunks (chave natural: documento_id + chunk_index)."""
        ...

    def listar_pendentes(self) -> list[Chunk]:
        """Chunks sem embedding OU cujo content_hash mudou desde a última indexação."""
        ...

    def salvar_embedding(
        self, chunk_chave: str, embedding: list[float], embedding_model: str
    ) -> None:
        """Grava o embedding registrando o modelo usado e o hash embeddado."""
        ...

    def marcar_documento_indexado(self, documento_id: str) -> None:
        """status_processamento do documento → 'indexado' (workflow geracao_embeddings)."""
        ...

    def documentos_com_pendencias(self) -> set[str]:
        """IDs de documentos que ainda têm chunks sem embedding atualizado."""
        ...

    def buscar_vetorial(
        self,
        embedding_consulta: list[float],
        filtros: FiltrosBusca,
        limite: int,
        similaridade_minima: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        """Similaridade de cosseno (no Supabase: índice HNSW do pgvector).

        `similaridade_minima` é o piso de relevância: sem ele a busca vetorial
        devolve sempre os `limite` chunks mais próximos, por mais distantes que
        sejam — e o agente passaria a "responder" perguntas fora do acervo com
        contexto irrelevante. Ver nota em retrieval/hybrid_search.py.
        """
        ...

    def buscar_textual(
        self, consulta: str, filtros: FiltrosBusca, limite: int
    ) -> list[tuple[Chunk, float]]:
        """Busca léxica (no Supabase: FTS 'portuguese' + unaccent)."""
        ...


# ---------------------------------------------------------------------------
# Implementação em memória (testes e desenvolvimento offline)
# ---------------------------------------------------------------------------


def _cosseno(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores de mesma dimensão."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class _RegistroChunk:
    """Linha interna do repositório em memória (chunk + estado de indexação)."""

    chunk: Chunk
    embedding: list[float] | None = None
    embedding_model: str | None = None
    embedding_content_hash: str | None = None


@dataclass
class InMemoryChunkRepository:
    """Repositório em memória com a mesma semântica esperada do Supabase.

    Implementa a lógica incremental: um chunk é "pendente" se nunca foi
    embeddado ou se o content_hash atual difere do hash embeddado.
    """

    _registros: dict[str, _RegistroChunk] = field(default_factory=dict)
    documentos_indexados: set[str] = field(default_factory=set)

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            existente = self._registros.get(chunk.chave)
            if existente is None:
                self._registros[chunk.chave] = _RegistroChunk(chunk=chunk)
            else:
                # Mantém o embedding antigo: se o hash não mudou, não re-embedda.
                existente.chunk = chunk

    def listar_pendentes(self) -> list[Chunk]:
        pendentes = [
            r.chunk
            for r in self._registros.values()
            if r.embedding is None or r.embedding_content_hash != r.chunk.content_hash
        ]
        return sorted(pendentes, key=lambda c: (c.documento_id, c.chunk_index))

    def salvar_embedding(
        self, chunk_chave: str, embedding: list[float], embedding_model: str
    ) -> None:
        registro = self._registros[chunk_chave]
        registro.embedding = embedding
        registro.embedding_model = embedding_model
        registro.embedding_content_hash = registro.chunk.content_hash

    def marcar_documento_indexado(self, documento_id: str) -> None:
        self.documentos_indexados.add(documento_id)

    def documentos_com_pendencias(self) -> set[str]:
        return {c.documento_id for c in self.listar_pendentes()}

    def buscar_vetorial(
        self,
        embedding_consulta: list[float],
        filtros: FiltrosBusca,
        limite: int,
        similaridade_minima: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        candidatos = [
            (r.chunk, _cosseno(embedding_consulta, r.embedding))
            for r in self._registros.values()
            if r.embedding is not None and filtros.aceita(r.chunk)
        ]
        candidatos = [par for par in candidatos if par[1] >= similaridade_minima]
        candidatos.sort(key=lambda par: par[1], reverse=True)
        return candidatos[:limite]

    def buscar_textual(
        self, consulta: str, filtros: FiltrosBusca, limite: int
    ) -> list[tuple[Chunk, float]]:
        termos = set(_tokenizar(consulta))
        if not termos:
            return []
        resultados: list[tuple[Chunk, float]] = []
        for r in self._registros.values():
            if not filtros.aceita(r.chunk):
                continue
            tokens_chunk = _tokenizar(r.chunk.conteudo)
            if not tokens_chunk:
                continue
            acertos = sum(1 for t in tokens_chunk if t in termos)
            if acertos > 0:
                # Aproximação de ts_rank: frequência dos termos normalizada pelo tamanho.
                resultados.append((r.chunk, acertos / len(tokens_chunk)))
        resultados.sort(key=lambda par: par[1], reverse=True)
        return resultados[:limite]

    # Auxiliares para testes/inspeção -------------------------------------

    def obter_registro(self, chunk_chave: str) -> _RegistroChunk:
        return self._registros[chunk_chave]

    def total_chunks(self) -> int:
        return len(self._registros)


class SupabaseChunkRepository:
    """Esqueleto do repositório real (pgvector no Supabase).

    NÃO implementado nesta fatia: as credenciais do Supabase ainda não foram
    provisionadas e o DDL (docs/ARQUITETURA.md §3) será aplicado pela frente de
    Dados & Infraestrutura. A busca híbrida no banco usará a função RPC
    `busca_hibrida` — rascunho em db/migrations/rascunho_busca_hibrida.sql.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "SupabaseChunkRepository depende do provisionamento do Supabase "
            "(frente de Dados & Infraestrutura). Use InMemoryChunkRepository "
            "para testes/desenvolvimento offline."
        )
