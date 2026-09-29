"""Contratos HTTP da API — espelham `RespostaAgente`/`Citacao` (src/solufarma_rag/db/models.py).

A API não recria lógica de RAG: estes modelos só serializam o que o agente
já devolve, acrescentando o que a tela precisa e o agente não carrega
(título do documento na citação, modo de execução, origem da fixture).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    status: str = Field(description="'simulado' (modo demo) ou 'na_fila' (modo real)")
    arquivo: str
    tamanho_bytes: int
    orgao: str
    tipo: str
    mensagem: str
    envio_id: str | None = Field(default=None, description="Para acompanhar em GET /uploads/{id}")


class EtapaOut(BaseModel):
    chave: str
    rotulo: str
    estado: Literal["pendente", "andamento", "ok", "erro"]
    detalhe: str | None = None


class EnvioOut(BaseModel):
    """Progresso de um upload real: triagem → extração → chunks → cadastro → embeddings
    → classificação."""

    id: str
    arquivo: str
    orgao: str
    tipo: str
    criado_em: datetime
    estado: Literal["na_fila", "processando", "concluido", "erro"]
    etapas: list[EtapaOut]
    titulo: str | None = None
    documento_id: str | None = None
    erro: str | None = None
    aguardando_aprovacao: bool = Field(
        default=False,
        description=(
            "True quando o envio parou antes do OCR por passar de UPLOAD_MAX_PAGINAS_OCR "
            "(estado vem 'erro' para o frontend v2). Libere com POST /uploads/{id}/aprovar."
        ),
    )


class SaudeOut(BaseModel):
    modo: str
    documentos: int


class TurnoExportado(BaseModel):
    """Um turno da conversa como o navegador tem: pergunta + o `RespostaOut` que /perguntar devolveu."""

    pergunta: str = Field(min_length=1, max_length=2000)
    perguntado_em: datetime | None = None
    resposta: RespostaOut | None = None
    erro: str | None = None


class ExportarDocxIn(BaseModel):
    """Corpo de POST /exportar/docx. A API só formata: nenhuma chamada ao LLM."""

    escopo: Literal["conversa", "resposta"] = "conversa"
    gerado_em: datetime = Field(description="Com fuso; vem do navegador")
    usuario: str | None = Field(default=None, description="Reservado para o login; não sai no documento")
    turnos: list[TurnoExportado] = Field(min_length=1, max_length=100)
