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


def embeddar_consulta(provider: EmbeddingProvider, consulta: str) -> list[float]:
    """Embedda o texto de uma PERGUNTA (não de um documento do acervo).

    POR QUE NÃO É SÓ `embed_batch([consulta])[0]`:
    a Voyage embedda pergunta e documento de formas diferentes — `input_type`
    "query" prefixa "Represent the query for retrieving supporting documents:",
    "document" prefixa "Represent the document for retrieval:". Usar o mesmo
    modo nos dois lados é uma perda de qualidade que não gera erro nenhum: a
    busca simplesmente devolve resultados piores, em silêncio.

    Provedores sem essa distinção (OpenAI, o fake dos testes) não precisam de
    mudança: quem não expõe `embed_query` cai no caminho antigo. Foi feito assim
    de propósito, para não quebrar a assinatura que os testes já usam.
    """
    metodo = getattr(provider, "embed_query", None)
    if metodo is not None:
        return metodo(consulta)
    return provider.embed_batch([consulta])[0]


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


@dataclass
class VoyageEmbeddingProvider:
    """Provedor da Voyage AI — o padrão do projeto (ADR pendente, ver §7 do SOP).

    POR QUE VOYAGE E NÃO OPENAI (decidido 2026-08-11):
    a coluna do banco é `vector(1024)` e a voyage-4 entrega 1024 NATIVAMENTE,
    enquanto a text-embedding-3-large entrega 3072 truncados para 1024. Os dois
    funcionam; um modelo treinado para ser bom em 1024 tende a usar melhor esse
    espaço do que um de 3072 cortado. Somado a isso, a faixa gratuita da Voyage
    (200M tokens) é ~157x o acervo inteiro (1,28M tokens projetados para os 40
    documentos), então o custo é zero.

    A decisão NÃO está fechada: `tools/avaliar.py` mede os dois contra o golden
    set. Trocar é mudar EMBEDDING_PROVIDER no .env e reembeddar.

    `input_type` existe porque a Voyage embedda pergunta e documento de formas
    diferentes — ver `embeddar_consulta()`.
    """

    client: object  # voyageai.Client
    model: str
    dims: int

    # Teto de itens por chamada da API da Voyage. O limite de TOKENS por chamada
    # (120k no voyage-4-large) é mais apertado na prática, mas com chunks de ~198
    # tokens em média são ~600 chunks até esbarrar nele — abaixo deste teto.
    MAX_ITENS_LOTE = 1000

    @property
    def model_id(self) -> str:
        return f"{self.model}-{self.dims}"

    @property
    def dimensions(self) -> int:
        return self.dims

    def embed_batch(self, textos: list[str]) -> list[list[float]]:  # pragma: no cover
        return self._embed(textos, "document")

    def embed_query(self, texto: str) -> list[float]:  # pragma: no cover
        return self._embed([texto], "query")[0]

    def _embed(self, textos: list[str], input_type: str) -> list[list[float]]:
        resultado = self.client.embed(
            textos,
            model=self.model,
            input_type=input_type,
            output_dimension=self.dims,
        )
        return resultado.embeddings


def criar_provedor_voyage(
    model: str | None = None, dimensions: int | None = None
) -> VoyageEmbeddingProvider:
    """Monta o provedor da Voyage a partir do `.env`.

    Import tardio pelo mesmo motivo do `criar_provedor_openai`: os testes rodam
    offline com o fake e não devem exigir o pacote instalado.
    """
    try:
        import voyageai
    except ImportError as exc:  # pragma: no cover - caminho de produção
        raise ImportError(
            "O pacote 'voyageai' não está instalado. Instale-o para gerar "
            "embeddings com a Voyage, ou use EMBEDDING_PROVIDER=openai."
        ) from exc
    from ..config import get_settings

    settings = get_settings()
    if not settings.voyage_api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY não está no .env. Pegue a chave em dash.voyageai.com "
            "ou use EMBEDDING_PROVIDER=openai."
        )

    return VoyageEmbeddingProvider(
        client=voyageai.Client(api_key=settings.voyage_api_key),
        model=model or settings.voyage_model,
        dims=dimensions or settings.embedding_dimensions,
    )


def criar_provedor(nome: str | None = None) -> EmbeddingProvider:
    """Fábrica única: devolve o provedor conforme EMBEDDING_PROVIDER do `.env`.

    É o ponto de troca do teste A/B (`tools/avaliar.py`). Todo o resto do
    pipeline fala com o Protocol e não sabe qual fornecedor está rodando.

    `fake` existe para o smoke test offline não precisar de chave nem de rede.
    """
    from ..config import get_settings

    escolhido = (nome or get_settings().embedding_provider).strip().lower()
    if escolhido == "voyage":
        return criar_provedor_voyage()
    if escolhido == "openai":
        return criar_provedor_openai()
    if escolhido == "fake":
        return FakeEmbeddingProvider()
    raise ValueError(
        f"EMBEDDING_PROVIDER inválido: {escolhido!r}. Use 'voyage', 'openai' ou 'fake'."
    )


class RepoRestrito:
    """Restringe o pipeline incremental a alguns documentos.

    `gerar_embeddings_pendentes` embedda TUDO o que `listar_pendentes` devolve.
    Com outra sessão inserindo documentos ao mesmo tempo, isso embeddaria (e
    marcaria como indexados) chunks que não são desta execução. Este invólucro
    filtra a lista de pendentes por `documento_id` e delega o resto. Usado pelo
    `tools/generate_embeddings.py --documento-id` e pelo upload da API.
    """

    def __init__(self, repo, documento_ids: set[str]):
        self._repo = repo
        self._ids = set(documento_ids)

    def listar_pendentes(self):
        return [c for c in self._repo.listar_pendentes() if c.documento_id in self._ids]

    def documentos_com_pendencias(self) -> set[str]:
        return self._repo.documentos_com_pendencias() & self._ids

    def __getattr__(self, nome):
        return getattr(self._repo, nome)


class RelatorioEmbeddings(BaseModel):
    """Resultado de uma execução do pipeline (log/custo — SOP passo 5)."""

    total_pendentes: int
    embeddados: int
    pulados_ruido: int
    lotes: int
    tokens_estimados: int
    embedding_model: str
    documentos_indexados: list[str]


# A Voyage recusa lote acima de 120k tokens (medido por ela). Em 30/09 um lote de
# tabelas de materiais do Cristália Obra II deu 120.348 tokens reais: texto
# numérico tokeniza bem acima da estimativa `estimar_tokens`. Por isso o teto
# é sobre a ESTIMATIVA e com folga larga (~3x).
MAX_TOKENS_ESTIMADOS_POR_LOTE = 40_000


def _lotes(chunks: list, tamanho_lote: int, max_tokens: int):
    """Fatia em lotes de até `tamanho_lote` chunks e até `max_tokens` estimados.

    Um chunk sozinho acima do teto vira um lote de um (o provedor trunca).
    """
    lote: list = []
    tokens = 0
    for chunk in chunks:
        t = estimar_tokens(chunk.conteudo)
        if lote and (len(lote) >= tamanho_lote or tokens + t > max_tokens):
            yield lote
            lote, tokens = [], 0
        lote.append(chunk)
        tokens += t
    if lote:
        yield lote


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
    for lote in _lotes(indexaveis, tamanho_lote, MAX_TOKENS_ESTIMADOS_POR_LOTE):
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
