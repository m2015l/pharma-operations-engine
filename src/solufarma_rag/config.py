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
    supabase_service_role_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    )
    embedding_dimensions: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    )
    agent_model: str = field(
        default_factory=lambda: os.getenv("AGENT_MODEL", "claude-sonnet-5")
    )


def get_settings() -> Settings:
    """Retorna as configurações, carregando o `.env` na primeira chamada."""
    _carregar_dotenv()
    return Settings()
