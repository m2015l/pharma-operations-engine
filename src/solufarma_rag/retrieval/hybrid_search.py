"""Busca híbrida: similaridade vetorial + full-text + filtros, fundidas por RRF.

Design (docs/ARQUITETURA.md §5.1):
- A parte léxica é crítica no domínio de licitações: códigos ("PE 045/2023"),
  siglas (ANVISA, RDC) e nomes de equipamentos são exatamente o que embeddings
  erram;
- Filtros por metadados (órgão, tipo, período) são aplicados ANTES do ranking;
- Reciprocal Rank Fusion (RRF, k=60) combina os dois rankings — mesma fórmula
  da função RPC `busca_hibrida` (db/migrations/rascunho_busca_hibrida.sql);
- Top-k inicial generoso (20) seguido de corte/rerank para 5–8 chunks finais.

Contra o Supabase real, este módulo passará a chamar a RPC; contra o
repositório em memória, executa a mesma semântica localmente. O reranker
(fase 1: LLM-as-reranker com Haiku) é um hook injetável opcional.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from ..db.models import Chunk, ChunkComScore
from ..db.repository import ChunkRepository, FiltrosBusca
from ..ingestion.embeddings import EmbeddingProvider, embeddar_consulta

RRF_K = 60  # constante clássica do RRF; igual à usada no SQL
CANDIDATOS_PADRAO = 20
TOP_K_PADRAO = 5

# Piso de relevância da busca vetorial (similaridade de cosseno).
#
# Sem esse piso, a busca vetorial devolve SEMPRE os `candidatos` chunks mais
# próximos, mesmo que nenhum tenha relação com a pergunta — o acervo nunca
# "não responde", e o agente recebe contexto irrelevante como se fosse fonte.
# O ramo léxico já tem piso natural (só casa quem contém os termos).
#
# CALIBRAR com embeddings reais: o valor abaixo foi ajustado contra o provedor
# fake (bag-of-words), cuja escala de similaridade é diferente da de um modelo
# real. Cada modelo tem sua própria escala, então o piso é por modelo.
#
# NÃO CHUTE ESTE VALOR. `tools/avaliar.py --calibrar` mede a distribuição real
# dos scores contra o golden set — o maior score de trecho irrelevante (ruído)
# e o menor score de trecho correto (sinal) — e recomenda um piso entre os dois.
# Aplique o resultado em SIMILARIDADE_MINIMA no .env, sem editar este arquivo.
SIMILARIDADE_MINIMA_PADRAO = 0.15


def _piso_padrao() -> float:
    """Lê o piso do `.env`, caindo no valor histórico quando não houver."""
    from ..config import get_settings

    return get_settings().similaridade_minima

# Reranker opcional: recebe (consulta, candidatos) e devolve os candidatos
# reordenados. Fase 1 do MVP: LLM-as-reranker com Haiku (a implementar quando
# houver chave de API); sem reranker, vale a ordem do RRF.
Reranker = Callable[[str, list[ChunkComScore]], list[ChunkComScore]]


class Searcher(Protocol):
    """Interface de busca consumida pelo agente (permite fakes nos testes)."""

    def buscar(
        self, consulta: str, filtros: FiltrosBusca | None = None, top_k: int = TOP_K_PADRAO
    ) -> list[ChunkComScore]:
        ...


def fundir_rrf(
    ranking_vetorial: list[Chunk],
    ranking_lexico: list[Chunk],
    k: int = RRF_K,
) -> list[ChunkComScore]:
    """Reciprocal Rank Fusion: score(c) = Σ 1/(k + posição) em cada ranking.

    Chunks presentes nos dois rankings somam as duas parcelas e tendem a subir —
    é o comportamento desejado: concordância entre busca semântica e léxica é
    forte sinal de relevância.
    """
    scores: dict[str, float] = {}
    por_chave: dict[str, Chunk] = {}
    for ranking in (ranking_vetorial, ranking_lexico):
        for posicao, chunk in enumerate(ranking, start=1):
            por_chave[chunk.chave] = chunk
            scores[chunk.chave] = scores.get(chunk.chave, 0.0) + 1.0 / (k + posicao)
    ordenado = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [ChunkComScore(chunk=por_chave[chave], score=score) for chave, score in ordenado]


@dataclass
class HybridSearcher:
    """Busca híbrida contra um ChunkRepository (injetável) qualquer."""

    repo: ChunkRepository
    provider: EmbeddingProvider
    candidatos: int = CANDIDATOS_PADRAO
    reranker: Reranker | None = None
    similaridade_minima: float = field(default_factory=_piso_padrao)

    def buscar(
        self, consulta: str, filtros: FiltrosBusca | None = None, top_k: int = TOP_K_PADRAO
    ) -> list[ChunkComScore]:
        """Executa a busca híbrida completa: vetorial + léxica → RRF → top-k.

        Retorna lista vazia quando nada no acervo atinge o piso de relevância —
        é o sinal que o agente usa para dizer que não encontrou, em vez de
        responder com contexto irrelevante.
        """
        filtros = filtros or FiltrosBusca()

        # `embeddar_consulta` e não `embed_batch`: a Voyage embedda pergunta e
        # documento de formas diferentes, e usar o modo errado degrada o recall
        # sem gerar erro. Provedores sem essa distinção caem no caminho antigo.
        embedding_consulta = embeddar_consulta(self.provider, consulta)
        # Pool 2× por ramo antes de fundir — mesma proporção do `match_count * 2`
        # da RPC SQL. Sem isso o comportamento testado offline teria recall menor
        # que o de produção, e os testes deixariam de ser representativos.
        pool = self.candidatos * 2
        vetorial = self.repo.buscar_vetorial(
            embedding_consulta, filtros, pool, self.similaridade_minima
        )
        lexica = self.repo.buscar_textual(consulta, filtros, pool)

        fundidos = fundir_rrf(
            [chunk for chunk, _ in vetorial],
            [chunk for chunk, _ in lexica],
        )
        if self.reranker is not None:
            fundidos = self.reranker(consulta, fundidos)
        return fundidos[:top_k]
