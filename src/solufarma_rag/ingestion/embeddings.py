"""Geração de embeddings dos chunks — incremental e com provedor injetável.

Cumpre o SOP workflows/geracao_embeddings.md:
1. Seleciona apenas chunks pendentes (sem embedding ou com content_hash alterado);
2. Gera embeddings em lotes de ~100 chunks por chamada;
3. Grava registrando o modelo e a dimensão (`embedding_model`);
4. Ao concluir todos os chunks de um documento, marca o documento como indexado;
5. Registra contagens e tokens consumidos (custo) no relatório.

O provedor de embeddings é um Protocol: `FakeEmbeddingProvider` (determinístico,
offline) para testes, `LangChainEmbeddingProvider` para produção quando a
OPENAI_API_KEY estiver provisionada (docs/ARQUITETURA.md §2.2:
text-embedding-3-large com dimensions=1024).

O provedor de produção é a camada LangChain do pipeline (ADR-008, opção B):
qualquer objeto `Embeddings` do LangChain serve, o que permite trocar de
fornecedor sem tocar neste pipeline. `criar_provedor_openai()` monta o padrão da
arquitetura; a importação de `langchain_openai` é tardia para que os testes
continuem rodando offline sem a biblioteca instalada.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from ..db.repository import ChunkRepository
from ..text_utils import tokenizar
from .chunking import estimar_tokens

TAMANHO_LOTE_PADRAO = 100
# Chunks cujo corpo é menor que isso são ruído de OCR (página de carimbos etc.)
# e não devem ser indexados — retrieval ruim é pior que acervo menor (SOP).
MIN_CARACTERES_CONTEUDO = 30


class EmbeddingProvider(Protocol):
    """Contrato de qualquer provedor de embeddings (real ou fake)."""

    @property
    def model_id(self) -> str:
        """Identificador gravado em `doc_chunks.embedding_model` (modelo + dimensão)."""
        ...

    @property
    def dimensions(self) -> int:
        ...

    def embed_batch(self, textos: list[str]) -> list[list[float]]:
        """Gera um embedding por texto, na mesma ordem."""
        ...


@dataclass
class FakeEmbeddingProvider:
    """Provedor determinístico e offline para testes e desenvolvimento.

    Usa bag-of-words com hashing SHA-256 das palavras: textos que compartilham
    vocabulário produzem vetores próximos (cosseno alto), o que torna os testes
    de retrieval significativos. Não usa `hash()` do Python (salteado por
    processo) — o vetor de um mesmo texto é idêntico entre execuções.

    A dimensão padrão é 1024, igual à de produção (text-embedding-3-large com
    dimensions=1024). Não é só simetria: em dimensões baixas (testado com 64),
    colisões de hash davam similaridade ALTA a textos sem nenhuma palavra em
    comum — "inexistente zzz" pontuava acima de "autoclave" contra um edital de
    autoclaves, o que inverte o resultado dos testes de relevância.
    """

    dim: int = 1024

    @property
    def model_id(self) -> str:
        return f"fake-bow-{self.dim}"

    @property
    def dimensions(self) -> int:
        return self.dim

    def embed_batch(self, textos: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in textos]

    def _embed(self, texto: str) -> list[float]:
        vetor = [0.0] * self.dim
        for palavra in tokenizar(texto):
            digest = hashlib.sha256(palavra.encode("utf-8")).digest()
            indice = int.from_bytes(digest[:4], "big") % self.dim
            vetor[indice] += 1.0
        norma = math.sqrt(sum(v * v for v in vetor))
        if norma > 0:
            vetor = [v / norma for v in vetor]
        return vetor


@dataclass
class LangChainEmbeddingProvider:
    """Adapta qualquer `Embeddings` do LangChain ao Protocol `EmbeddingProvider`.

    Esta é a camada LangChain do pipeline de RAG (ADR-008, opção B): o pipeline
    acima não conhece fornecedor nenhum, só este adaptador. Trocar OpenAI por
    outro modelo é trocar o objeto passado em `embeddings` — nada mais muda.

    `model_id` é gravado em `doc_chunks.embedding_model` e precisa identificar
    modelo **e** dimensão: misturar dimensões diferentes no mesmo índice
    corrompe a busca vetorial silenciosamente.
    """

    embeddings: object  # langchain_core.embeddings.Embeddings
    model: str
    dims: int

    @property
    def model_id(self) -> str:
        return f"{self.model}-{self.dims}"

    @property
    def dimensions(self) -> int:
        return self.dims

    def embed_batch(self, textos: list[str]) -> list[list[float]]:  # pragma: no cover
        return self.embeddings.embed_documents(textos)


def criar_provedor_openai(
    model: str | None = None, dimensions: int | None = None
) -> LangChainEmbeddingProvider:
    """Monta o provedor de produção: `langchain_openai.OpenAIEmbeddings`.

    Padrões vêm do `.env` via `get_settings()` (text-embedding-3-large @ 1024,
    docs/ARQUITETURA.md §2.2). Requer OPENAI_API_KEY no ambiente — a chave é
    resolvida pelo próprio cliente da OpenAI.

    Import tardio: `langchain-openai` só é exigido quando o provedor real é de
    fato usado, para os testes seguirem rodando offline com o fake.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError as exc:  # pragma: no cover - caminho de produção
        raise ImportError(
            "O pacote 'langchain-openai' não está instalado. Instale-o "
            "(requirements.txt) para gerar embeddings reais, ou use "
            "FakeEmbeddingProvider nos testes."
        ) from exc
    from ..config import get_settings

    settings = get_settings()
    modelo = model or settings.embedding_model
    dims = dimensions or settings.embedding_dimensions

    extras: dict = {}
    if settings.embedding_base_url:
        # Gateway compatível com a API da OpenAI (OpenRouter, Azure, vLLM...).
        extras["base_url"] = settings.embedding_base_url
        # `check_embedding_ctx_length=False`: a contagem de tokens client-side do
        # langchain-openai usa o tiktoken do modelo pelo NOME. Com o slug do
        # gateway (`openai/text-embedding-3-large`) ele não reconhece o modelo e
        # quebra antes de qualquer chamada de rede.
        extras["check_embedding_ctx_length"] = False
    if settings.embedding_api_key:
        extras["api_key"] = settings.embedding_api_key

    return LangChainEmbeddingProvider(
        embeddings=OpenAIEmbeddings(model=modelo, dimensions=dims, **extras),
        model=modelo,
        dims=dims,
    )


class RelatorioEmbeddings(BaseModel):
    """Resultado de uma execução do pipeline (log/custo — SOP passo 5)."""

    total_pendentes: int
    embeddados: int
    pulados_ruido: int
    lotes: int
    tokens_estimados: int
    embedding_model: str
    documentos_indexados: list[str]


def gerar_embeddings_pendentes(
    repo: ChunkRepository,
    provider: EmbeddingProvider,
    tamanho_lote: int = TAMANHO_LOTE_PADRAO,
) -> RelatorioEmbeddings:
    """Executa o pipeline incremental de embeddings contra o repositório dado.

    Incremental por hash: chunks cujo `content_hash` não mudou desde a última
    indexação não são reprocessados (nunca reindexar tudo por mudança pequena).
    Retomável: como o estado é por chunk, uma falha no meio do lote permite
    reexecutar e processar apenas os faltantes.
    """
    pendentes = repo.listar_pendentes()

    indexaveis = []
    pulados = 0
    for chunk in pendentes:
        # Remove o prefixo contextual da contagem de "ruído": o corpo real do
        # chunk é o que interessa para decidir se vale indexar.
        corpo = chunk.conteudo.split("\n", 1)[-1].strip()
        if len(corpo) < MIN_CARACTERES_CONTEUDO:
            pulados += 1
            continue
        indexaveis.append(chunk)

    tokens_estimados = 0
    lotes = 0
    for inicio in range(0, len(indexaveis), tamanho_lote):
        lote = indexaveis[inicio : inicio + tamanho_lote]
        vetores = provider.embed_batch([c.conteudo for c in lote])
        if len(vetores) != len(lote):
            raise RuntimeError(
                f"Provedor retornou {len(vetores)} embeddings para lote de {len(lote)} chunks"
            )
        for chunk, vetor in zip(lote, vetores):
            if len(vetor) != provider.dimensions:
                raise RuntimeError(
                    f"Embedding com dimensão {len(vetor)} != {provider.dimensions} "
                    f"(chunk {chunk.chave}) — nunca misturar modelos no mesmo índice"
                )
            repo.salvar_embedding(chunk.chave, vetor, provider.model_id)
            tokens_estimados += estimar_tokens(chunk.conteudo)
        lotes += 1

    # Documentos sem pendências restantes → status 'indexado' (SOP passo 3).
    documentos_processados = {c.documento_id for c in pendentes}
    ainda_pendentes = repo.documentos_com_pendencias()
    indexados = sorted(documentos_processados - ainda_pendentes)
    for documento_id in indexados:
        repo.marcar_documento_indexado(documento_id)

    return RelatorioEmbeddings(
        total_pendentes=len(pendentes),
        embeddados=len(indexaveis),
        pulados_ruido=pulados,
        lotes=lotes,
        tokens_estimados=tokens_estimados,
        embedding_model=provider.model_id,
        documentos_indexados=indexados,
    )
