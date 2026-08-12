"""Modelos Pydantic dos registros do pipeline RAG.

Espelham o DDL de docs/ARQUITETURA.md §3 (tabelas `documentos` e `doc_chunks`),
acrescidos dos metadados obrigatórios de chunk definidos na skill rag-licitacoes
(documento_id, tipo_documento, orgao, data, secao, pagina).
"""

from __future__ import annotations

import hashlib
from datetime import date

from pydantic import BaseModel, Field, field_validator

# Espelha o CHECK de `documentos.tipo` (migrations/003_tipo_atestado.sql).
# `atestado` = CAT / atestado de capacidade técnica: é o documento que prova
# obra já executada, e o que responde "já fizemos isso antes?".
TIPOS_DOCUMENTO = (
    "edital",
    "ata",
    "resultado",
    "atestado",
    "anexo",
    "proposta",
    "recurso",
    "outro",
)


class PaginaDocumento(BaseModel):
    """Texto extraído de uma página do documento (saída do tools/extract_text.py)."""

    numero: int = Field(ge=1, description="Número da página no PDF original (1-based)")
    texto: str


class DocumentoParaChunking(BaseModel):
    """Documento com texto por página + metadados, pronto para o chunking.

    É o contrato de entrada de `ingestion.chunking.gerar_chunks`.

    Nota: desde o merge com o pipeline de OCR, `tools/chunk_document.py` é o CLI
    do chunker de `solufarma.chunking` (ADR-006), não deste. `gerar_chunks` só é
    chamado por testes hoje — ele volta a ter entrada de CLI quando o port do
    pacote decidir se o chunking de edital nativo vira um regime do chunker da
    Diva (item 14 do PLANO_PROJETO).
    """

    documento_id: str = Field(min_length=1, description="UUID da linha em `documentos`")
    tipo_documento: str = Field(description="edital | ata | resultado | anexo | ...")
    orgao: str = Field(min_length=1, description="Órgão/entidade compradora")
    numero_edital: str | None = Field(default=None, description='Ex.: "PE 045/2023"')
    data: date | None = Field(default=None, description="Data de abertura da licitação")
    paginas: list[PaginaDocumento] = Field(min_length=1)

    @field_validator("tipo_documento")
    @classmethod
    def _validar_tipo(cls, v: str) -> str:
        if v not in TIPOS_DOCUMENTO:
            raise ValueError(f"tipo_documento deve ser um de {TIPOS_DOCUMENTO}, recebido: {v!r}")
        return v


class Chunk(BaseModel):
    """Um chunk indexável de documento, com rastreabilidade completa.

    `conteudo` já inclui o prefixo contextual "[Edital PE 045/2023 – Órgão – Seção: X]"
    (contextual retrieval "barato", docs/ARQUITETURA.md §4.6) — assim o embedding
    carrega o contexto do documento e o `content_hash` cobre o texto exatamente
    como será embeddado.
    """

    documento_id: str
    chunk_index: int = Field(ge=0)
    tipo_documento: str
    orgao: str
    data: date | None = None
    secao: str = Field(description='Ex.: "1. DO OBJETO", "ANEXO I – TERMO DE REFERÊNCIA"')
    pagina_inicio: int = Field(ge=1)
    pagina_fim: int = Field(ge=1)
    conteudo: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    content_hash: str = Field(description="SHA-256 do conteúdo — base da indexação incremental")

    @property
    def chave(self) -> str:
        """Chave natural do chunk — equivale ao UNIQUE(documento_id, chunk_index) do DDL."""
        return f"{self.documento_id}:{self.chunk_index}"

    @staticmethod
    def calcular_hash(conteudo: str) -> str:
        """SHA-256 hexadecimal do conteúdo (determinístico, estável entre execuções)."""
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


class ChunkComScore(BaseModel):
    """Resultado de busca: chunk + score de relevância (RRF ou similaridade)."""

    chunk: Chunk
    score: float


class Citacao(BaseModel):
    """Uma citação [n] da resposta do agente, resolvida até a fonte original.

    Contrato de rastreabilidade (docs/ARQUITETURA.md §5.4):
    [n] → chunk → documento → página.
    """

    marcador: int = Field(ge=1, description="O n do marcador [n] na resposta")
    chunk_chave: str
    documento_id: str
    tipo_documento: str
    orgao: str
    secao: str
    pagina_inicio: int
    pagina_fim: int
    trecho: str = Field(description="Início do conteúdo do chunk citado (para exibição)")


class RespostaAgente(BaseModel):
    """Resposta final do agente com as citações resolvidas."""

    texto: str
    citacoes: list[Citacao]
    tipo_fluxo: str = Field(description="consulta_historico | analise_edital | outro")
    encontrou_no_acervo: bool = True
    contrato_citacao_ok: bool = Field(
        default=True,
        description=(
            "False quando o agente afirmou algo sem fonte rastreável: resposta sem "
            "nenhum [n] apesar de haver contexto, ou com marcador inexistente. "
            "A interface NÃO deve exibir como resposta confiável."
        ),
    )
    citacoes_invalidas: list[int] = Field(
        default_factory=list,
        description="Marcadores [n] citados que não existem no contexto (alucinação de fonte)",
    )
