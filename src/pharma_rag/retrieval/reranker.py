"""Reranker da busca híbrida — Voyage rerank sobre o pool fundido pelo RRF.

POR QUE EXISTE
O RRF ordena por concordância de POSIÇÃO entre os ramos vetorial e léxico; ele
nunca lê a pergunta e o trecho juntos. No golden set de 29/09, em 10 de 22
perguntas um distrator vencia o trecho certo na similaridade vetorial — o trecho
certo estava no pool, só não no topo. Um cross-encoder (o reranker) lê pergunta
e trecho lado a lado e corrige exatamente essa ordenação.

POR QUE VOYAGE
A chave já existe (embeddings), e os 200M tokens gratuitos por conta cobrem o
rerank com folga: ~15 trechos x ~300 tokens = ~4,5k tokens por pergunta, ou
~44 mil perguntas antes de pagar qualquer coisa. Depois disso, US$ 0,05/M tokens
= ~US$ 0,0002 por pergunta. Ver docs.voyageai.com/docs/pricing.

POR QUE rerank-2.5 E NÃO rerank-3 (o mais novo)
Medido no golden set em 29/09 (22 perguntas, pool 15): rerank-2.5 MRR@8 0,81 e
top-5 21/22; rerank-3 0,79 e 20/22; rerank-3-lite pior. Instrução prefixada na
pergunta piorou os dois. Amostra pequena — remedir com o golden set maior.
Trocar é só RERANKER_MODELO no .env.

CONTRATO
- Recebe (consulta, candidatos) e devolve os candidatos reordenados, com
  `score` = relevance_score do reranker (0–1) — a mesma assinatura do gancho
  `Reranker` de hybrid_search.py.
- Falha da API NUNCA derruba a resposta: loga aviso e devolve a ordem RRF.
- Piso próprio (`RERANK_MINIMO`) opcional: trechos abaixo dele saem do
  resultado. 0 desliga. Ver `tools/avaliar.py --calibrar-rerank`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..db.models import ChunkComScore

logger = logging.getLogger(__name__)

MODELO_PADRAO = "rerank-2.5"


@dataclass
class VoyageReranker:
    """Reordena candidatos com o endpoint de rerank da Voyage."""

    client: object  # voyageai.Client
    modelo: str = MODELO_PADRAO
    piso: float = 0.0

    def __call__(self, consulta: str, candidatos: list[ChunkComScore]) -> list[ChunkComScore]:
        if not candidatos:
            return candidatos
        try:
            resposta = self.client.rerank(  # type: ignore[attr-defined]
                consulta,
                [c.chunk.conteudo for c in candidatos],
                model=self.modelo,
                truncation=True,
            )
        except Exception as exc:  # noqa: BLE001 — qualquer falha cai para o RRF
            logger.warning("Rerank indisponível (%s); mantendo a ordem do RRF.", exc)
            return candidatos

        reordenados = [
            ChunkComScore(chunk=candidatos[r.index].chunk, score=r.relevance_score)
            for r in sorted(resposta.results, key=lambda r: r.relevance_score, reverse=True)
        ]
        if self.piso > 0:
            reordenados = [r for r in reordenados if r.score >= self.piso]
        return reordenados


def criar_reranker(nome: str | None = None):
    """Monta o reranker a partir do `.env` (RERANKER=voyage|nenhum).

    Devolve None quando desligado ou quando falta chave/pacote — a busca segue
    na ordem do RRF, com aviso no log. Nunca levanta: configuração incompleta
    de um componente opcional não pode derrubar a API.
    """
    from ..config import get_settings

    settings = get_settings()
    escolhido = (nome or settings.reranker).strip().lower()
    if escolhido in ("", "nenhum", "none", "off"):
        return None
    if escolhido != "voyage":
        logger.warning("RERANKER inválido: %r; seguindo sem reranker.", escolhido)
        return None
    if not settings.voyage_api_key:
        logger.warning("RERANKER=voyage mas VOYAGE_API_KEY está vazia; seguindo sem reranker.")
        return None
    try:
        import voyageai
    except ImportError:
        logger.warning("Pacote 'voyageai' ausente; seguindo sem reranker.")
        return None
    return VoyageReranker(
        # Timeout curto e 1 retry: o rerank está no caminho da resposta ao usuário;
        # se a Voyage engasgar, melhor responder na ordem RRF do que esperar.
        client=voyageai.Client(api_key=settings.voyage_api_key, max_retries=1, timeout=15),
        modelo=settings.reranker_modelo,
        piso=settings.rerank_minimo,
    )
