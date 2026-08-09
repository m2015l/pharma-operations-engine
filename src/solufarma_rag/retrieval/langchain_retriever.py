"""Adapta a busca híbrida a um `BaseRetriever` do LangChain (ADR-008, opção B).

Por que este arquivo existe: a opção B previa `langchain-postgres` como vector
store, mas ele impõe schema próprio (tabelas `langchain_pg_*` com metadados em
JSONB) e não faz a busca híbrida com filtros SQL sobre `licitacoes`. Adotá-lo
significaria ou duplicar o armazenamento vetorial, ou jogar fora o DDL e a
rastreabilidade chunk → documento → página, que é requisito central do projeto.

O caminho que preserva as duas coisas é este: o pgvector continua sendo acessado
pelo `SupabaseChunkRepository`, e o `HybridSearcher` é exposto como Retriever.
O pipeline segue LangChain de ponta a ponta — `Embeddings` → `Retriever` →
resposta — sem que o schema tenha de se dobrar à biblioteca.

Uso:

    retriever = SolufarmaRetriever(searcher=searcher, top_k=5)
    docs = retriever.invoke("prazo de entrega de autoclaves")
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from ..db.models import Chunk, ChunkComScore
from ..db.repository import FiltrosBusca
from .hybrid_search import TOP_K_PADRAO


def chunk_para_documento(resultado: ChunkComScore) -> Document:
    """Converte um resultado da busca em `Document` do LangChain.

    Os metadados carregam tudo que a citação precisa (chave, documento, seção,
    páginas). Sem isso o Document seria texto solto e a rastreabilidade —
    requisito central do projeto — morreria na fronteira com o LangChain.
    """
    chunk: Chunk = resultado.chunk
    return Document(
        page_content=chunk.conteudo,
        metadata={
            "chunk_chave": chunk.chave,
            "documento_id": chunk.documento_id,
            "chunk_index": chunk.chunk_index,
            "tipo_documento": chunk.tipo_documento,
            "orgao": chunk.orgao,
            "data": chunk.data.isoformat() if chunk.data else None,
            "secao": chunk.secao,
            "pagina_inicio": chunk.pagina_inicio,
            "pagina_fim": chunk.pagina_fim,
            "score": resultado.score,
        },
    )


class SolufarmaRetriever(BaseRetriever):
    """Retriever LangChain sobre a busca híbrida (vetorial + léxica + RRF).

    `searcher` é tipado como `Any` porque `Searcher` é um Protocol e o
    BaseRetriever é um modelo Pydantic — qualquer objeto com `.buscar()` serve,
    inclusive os stubs dos testes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    searcher: Any
    top_k: int = TOP_K_PADRAO
    filtros: FiltrosBusca | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun | None = None
    ) -> list[Document]:
        resultados = self.searcher.buscar(query, filtros=self.filtros, top_k=self.top_k)
        return [chunk_para_documento(r) for r in resultados]
