"""Configuração central do backend — lê variáveis do `.env` / ambiente.

Mantido propositalmente simples (sem pydantic-settings) para reduzir dependências.
As chaves reais (Supabase, Anthropic, OpenAI) ainda não existem no ambiente de
desenvolvimento; todo código que depende delas recebe implementações injetáveis
(fakes) nos testes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _carregar_dotenv() -> None:
    """Carrega o `.env` da raiz do projeto, se python-dotenv estiver instalado."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        # Sem python-dotenv instalado — usa apenas as variáveis já no ambiente.
        pass


@dataclass(frozen=True)
class Settings:
    """Parâmetros de configuração do pipeline RAG.

    Os padrões seguem docs/ARQUITETURA.md:
    - §2.2: embeddings text-embedding-3-large com dimensions=1024;
    - §2.5: agente principal Claude Sonnet 5 (claude-sonnet-5).
    """

    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    # `SUPABASE_SERVICE_KEY` é o nome canônico — é o que `solufarma/config.py`
    # exige no estágio `indexacao`. Os outros são fallback para `.env` antigos:
    # SECRET_KEY (formato sb_secret_) e SERVICE_ROLE_KEY (JWT legado).
    # Ter dois nomes para a mesma chave era o caminho para ela chegar vazia aqui
    # e o erro só aparecer na primeira chamada real.
    supabase_secret_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    supabase_publishable_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY", "")
    )
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # Qual fornecedor de embeddings roda: voyage | openai | fake.
    # É o interruptor do teste A/B (tools/avaliar.py). O padrão é voyage porque a
    # voyage-4 entrega 1024 dimensões NATIVAS — a coluna do banco é vector(1024),
    # e a OpenAI chega lá truncando 3072. Ver VoyageEmbeddingProvider.
    embedding_provider: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "voyage")
    )
    voyage_api_key: str = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY", ""))
    voyage_model: str = field(
        default_factory=lambda: os.getenv("VOYAGE_MODEL", "voyage-4-large")
    )

    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    )
    # Endpoint compatível com a API da OpenAI. Vazio = OpenAI direto.
    # Apontar para o OpenRouter (https://openrouter.ai/api/v1) permite reusar a
    # OPENROUTER_API_KEY que o OCR já usa, sem abrir conta na OpenAI — o slug do
    # modelo então vira `openai/text-embedding-3-large`.
    embedding_base_url: str = field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", ""))
    # Precedência explícita: uma chave dedicada vence; senão a da OpenAI; senão a
    # do OpenRouter. Sem isso, apontar a base_url para o OpenRouter e esquecer a
    # chave produziria um 401 que parece problema de modelo.
    embedding_api_key: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("OPENROUTER_API_KEY", "")
    )
    embedding_dimensions: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    )
    agent_model: str = field(
        default_factory=lambda: os.getenv("AGENT_MODEL", "claude-sonnet-5")
    )

    # Piso de similaridade da busca vetorial. Vive aqui, e não só como constante
    # em hybrid_search.py, porque o valor certo depende do MODELO de embeddings:
    # cada um tem sua escala de cosseno. Ajustar por variável de ambiente permite
    # aplicar o resultado de `tools/avaliar.py --calibrar` sem editar código —
    # e sem reeditar a cada troca de provedor no teste A/B.
    #
    # O padrão 0.15 é o valor histórico, calibrado contra o FakeEmbeddingProvider
    # (bag-of-words). NÃO é válido para modelo real: meça antes de confiar.
    similaridade_minima: float = field(
        default_factory=lambda: float(os.getenv("SIMILARIDADE_MINIMA", "0.15"))
    )


def get_settings() -> Settings:
    """Retorna as configurações, carregando o `.env` na primeira chamada."""
    _carregar_dotenv()
    return Settings()
