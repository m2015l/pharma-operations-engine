"""Contratos HTTP da API — espelham `RespostaAgente`/`Citacao` (src/solufarma_rag/db/models.py).

A API não recria lógica de RAG: estes modelos só serializam o que o agente
já devolve, acrescentando o que a tela precisa e o agente não carrega
(título do documento na citação, modo de execução, origem da fixture).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Turno(BaseModel):
    """Um turno anterior da conversa — mesmo formato que `AgenteLicitacoes.responder` espera."""

    pergunta: str
    resposta: str = ""


class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=2, max_length=2000)
    historico: list[Turno] = Field(default_factory=list, max_length=20)


class CitacaoOut(BaseModel):
    marcador: int
    chunk_chave: str
    documento_id: str
    titulo_documento: str
    tipo_documento: str
    orgao: str
    secao: str
    pagina_inicio: int
    pagina_fim: int
    trecho: str


class RespostaOut(BaseModel):
    texto: str
    citacoes: list[CitacaoOut]
    trechos_recuperados: int
    contrato_citacao_ok: bool
    citacoes_invalidas: list[int] = Field(default_factory=list)
    encontrou_no_acervo: bool
    tipo_fluxo: str
    modo: str = Field(description="'demo' (fixtures gravadas) ou 'real' (agente + Supabase)")
    origem: str | None = Field(
        default=None, description="No modo demo: de qual turno auditado a resposta foi tirada"
    )


class DocumentoOut(BaseModel):
    id: str
    titulo: str
    tipo: str
    orgao: str
    num_paginas: int | None
    num_chunks: int
    status: str
    indexado_em: str | None


class FonteOut(BaseModel):
    documento_id: str
    titulo: str
    url: str | None = Field(description="URL assinada (modo real) ou servida localmente (demo)")
    expira_em_segundos: int | None = None
    disponivel: bool
    motivo: str | None = None


class UploadOut(BaseModel):
    status: str
    arquivo: str
    tamanho_bytes: int
    orgao: str
    tipo: str
    mensagem: str


class SaudeOut(BaseModel):
    modo: str
    documentos: int
