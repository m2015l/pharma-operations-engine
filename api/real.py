"""Backend real: o agente que já existe (`src/solufarma_rag`) contra o Supabase.

Monta as mesmas peças que `tools/perguntar.py` — SupabaseChunkRepository →
HybridSearcher → AgenteLicitacoes — uma vez por processo. Nada de lógica de
RAG aqui: só montagem, serialização e a URL assinada do Storage.

CUSTO: cada `responder()` é uma chamada paga (LLM + embedding da consulta).
"""

from __future__ import annotations

import sys
import threading
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from schemas import CitacaoOut, DocumentoOut, RespostaOut, Turno

BUCKET = "documentos"
VALIDADE_URL_S = 600

# psycopg.Connection serializa comandos, mas o agente faz várias consultas por
# pergunta; um lock mantém cada pergunta atômica na conexão compartilhada.
# Ferramenta interna, poucos usuários simultâneos — não justifica pool ainda.
_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _pecas():
    from solufarma_rag.agent.agent import AgenteLicitacoes
    from solufarma_rag.agent.llm import criar_llm
    from solufarma_rag.db.repository import SupabaseChunkRepository, criar_conexao
    from solufarma_rag.ingestion.embeddings import criar_provedor
    from solufarma_rag.retrieval.hybrid_search import HybridSearcher

    conn = criar_conexao()
    repo = SupabaseChunkRepository(conn=conn)
    searcher = HybridSearcher(repo=repo, provider=criar_provedor(None))
    # top_k=8: mesmo padrão do tools/perguntar.py, onde as auditorias rodaram.
    agente = AgenteLicitacoes(searcher=searcher, llm=criar_llm(), top_k=8, repo_itens=repo)
    return conn, agente


_SQL_DOCUMENTOS = """
    select d.id, coalesce(d.titulo, d.storage_path), d.tipo, coalesce(l.orgao, '—'),
           d.num_paginas, d.status_processamento, d.created_at::date::text, d.storage_path,
           (select count(*) from doc_chunks c where c.documento_id = d.id)
    from documentos d
    left join licitacoes l on l.id = d.licitacao_id
    order by d.created_at
"""


def _linhas_documentos() -> list[tuple]:
    conn, _ = _pecas()
    with _LOCK, conn.cursor() as cur:
        cur.execute(_SQL_DOCUMENTOS)
        return cur.fetchall()


def documentos() -> list[DocumentoOut]:
    return [
        DocumentoOut(
            id=str(r[0]), titulo=r[1], tipo=r[2], orgao=r[3], num_paginas=r[4],
            status=r[5], indexado_em=r[6], num_chunks=r[8],
        )
        for r in _linhas_documentos()
    ]


def documento(doc_id: str) -> dict | None:
    for r in _linhas_documentos():
        if str(r[0]) == doc_id:
            return {"id": doc_id, "titulo": r[1], "storage_path": r[7]}
    return None


def responder(pergunta: str, historico: list[Turno]) -> RespostaOut:
    _, agente = _pecas()
    titulos = {d.id: d.titulo for d in documentos()}
    hist = [t.model_dump() for t in historico] or None
    with _LOCK:
        r = agente.responder(pergunta, historico=hist)
    return RespostaOut(
        texto=r.texto,
        citacoes=[
            CitacaoOut(**c.model_dump(), titulo_documento=titulos.get(c.documento_id, c.orgao))
            for c in r.citacoes
        ],
        trechos_recuperados=r.trechos_recuperados,
        contrato_citacao_ok=r.contrato_citacao_ok,
        citacoes_invalidas=r.citacoes_invalidas,
        encontrou_no_acervo=r.encontrou_no_acervo,
        tipo_fluxo=r.tipo_fluxo,
        modo="real",
    )


def url_assinada(storage_path: str) -> str:
    """URL temporária do PDF no bucket privado (Storage API, header `apikey`).

    `apikey` e não `Authorization: Bearer` — ver `_headers` em tools/upload_documento.py.
    A chave de serviço fica só aqui no servidor; o navegador só vê a URL assinada.
    """
    import httpx

    from solufarma_rag.config import get_settings

    cfg = get_settings()
    if not cfg.supabase_url or not cfg.supabase_secret_key:
        raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_KEY precisam estar no .env")
    base = cfg.supabase_url.rstrip("/")
    resp = httpx.post(
        f"{base}/storage/v1/object/sign/{BUCKET}/{storage_path}",
        headers={"apikey": cfg.supabase_secret_key},
        json={"expiresIn": VALIDADE_URL_S},
        timeout=15,
    )
    resp.raise_for_status()
    caminho = resp.json().get("signedURL") or resp.json().get("signedUrl")
    return f"{base}/storage/v1{caminho}"
