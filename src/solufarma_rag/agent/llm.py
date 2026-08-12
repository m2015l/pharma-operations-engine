"""Cliente LLM injetável: fake determinístico para testes, Anthropic em produção.

A ANTHROPIC_API_KEY ainda não foi provisionada; todo o agente depende apenas do
Protocol `LLMClient`, então os testes rodam 100% offline com `FakeLLM` e o
código real (`AnthropicLLM`) fica pronto para receber a chave via `.env`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMClient(Protocol):
    """Contrato mínimo de um LLM de chat para o agente."""

    def completar(self, system: str, mensagens: list[dict], max_tokens: int = 4096) -> str:
        """Envia `mensagens` (formato [{"role": ..., "content": ...}]) e retorna o texto."""
        ...


@dataclass
class FakeLLM:
    """LLM fake para testes: devolve respostas pré-programadas em fila.

    Também registra todas as chamadas recebidas (`chamadas`) para que os testes
    possam inspecionar prompts e contexto enviados.
    """

    respostas: list[str] = field(default_factory=list)
    chamadas: list[dict] = field(default_factory=list)

    def completar(self, system: str, mensagens: list[dict], max_tokens: int = 4096) -> str:
        self.chamadas.append({"system": system, "mensagens": mensagens})
        if not self.respostas:
            raise AssertionError(
                "FakeLLM sem respostas na fila — o teste programou menos respostas "
                f"do que o agente pediu (chamada nº {len(self.chamadas)})"
            )
        return self.respostas.pop(0)


class AnthropicLLM:
    """Cliente real da API Anthropic (docs/ARQUITETURA.md §2.5).

    - Modelo padrão: claude-sonnet-5 (agente principal, definido na arquitetura);
    - Prompt caching: o system prompt do agente é estável → marcado com
      cache_control para economizar ~90% dos tokens repetidos por conversa;
    - Thinking adaptativo é o padrão do modelo (não configuramos `thinking`),
      e parâmetros de amostragem (temperature etc.) não são enviados — o
      claude-sonnet-5 rejeita valores não-padrão.
    """

    def __init__(self, model: str | None = None, max_retries: int = 2) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - caminho de produção
            raise ImportError(
                "O pacote 'anthropic' não está instalado. Instale-o (requirements.txt) "
                "para usar o agente real, ou use FakeLLM nos testes."
            ) from exc
        from ..config import get_settings

        settings = get_settings()
        # anthropic.Anthropic() resolve a credencial do ambiente (ANTHROPIC_API_KEY).
        self._client = anthropic.Anthropic(max_retries=max_retries)
        self._model = model or settings.agent_model

    def completar(
        self, system: str, mensagens: list[dict], max_tokens: int = 4096
    ) -> str:  # pragma: no cover - exige chave de API
        resposta = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=mensagens,
        )
        if resposta.stop_reason == "refusal":
            return (
                "Não foi possível gerar a resposta (solicitação recusada pelos "
                "filtros de segurança do modelo)."
            )
        return "".join(bloco.text for bloco in resposta.content if bloco.type == "text")


class OpenRouterLLM:
    """Mesmo Claude Sonnet 5, alcançado pelo OpenRouter em vez da API direta.

    POR QUE EXISTE
    O `.env` do projeto tem OPENROUTER_API_KEY preenchida (é o que o OCR usa) e
    ANTHROPIC_API_KEY vazia. Sem esta classe, testar o agente exigiria abrir
    conta na Anthropic antes de saber se o RAG funciona — uma barreira que não
    tem nada a ver com o que está sendo testado.

    O modelo é o mesmo (`anthropic/claude-sonnet-5`), então a qualidade da
    resposta é a mesma. O que muda é a rota e a fatura.

    QUANDO TROCAR PARA AnthropicLLM
    Quando a ANTHROPIC_API_KEY existir. A API direta dá acesso a prompt caching
    explícito (o `cache_control` que a AnthropicLLM já usa no system prompt),
    que aqui não é aproveitado — em produção, com o system prompt do agente
    repetido a cada pergunta, isso é economia real.
    """

    URL_BASE = "https://openrouter.ai/api/v1"

    def __init__(self, model: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - caminho de produção
            raise ImportError(
                "O pacote 'openai' não está instalado — é o cliente usado para "
                "falar com o endpoint compatível do OpenRouter."
            ) from exc
        import os

        from ..config import get_settings

        settings = get_settings()
        chave = os.getenv("OPENROUTER_API_KEY", "")
        if not chave:
            raise RuntimeError("OPENROUTER_API_KEY não está no .env.")

        self._client = OpenAI(api_key=chave, base_url=self.URL_BASE)
        # O slug do OpenRouter exige o prefixo do fornecedor. AGENT_MODEL guarda
        # o id puro da Anthropic (`claude-sonnet-5`), que aqui não resolve.
        modelo = model or os.getenv("OPENROUTER_MODELO") or f"anthropic/{settings.agent_model}"
        self._model = modelo if "/" in modelo else f"anthropic/{modelo}"

    def completar(
        self, system: str, mensagens: list[dict], max_tokens: int = 4096
    ) -> str:  # pragma: no cover - exige chave de API
        resposta = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *mensagens],
        )
        return resposta.choices[0].message.content or ""


def criar_llm(nome: str | None = None) -> LLMClient:
    """Fábrica: escolhe o cliente conforme AGENT_PROVIDER do `.env`.

    Padrão `openrouter` porque é a chave que o projeto tem hoje. Vira
    `anthropic` trocando uma linha, quando a chave direta existir.
    """
    import os

    escolhido = (nome or os.getenv("AGENT_PROVIDER", "openrouter")).strip().lower()
    if escolhido == "openrouter":
        return OpenRouterLLM()
    if escolhido == "anthropic":
        return AnthropicLLM()
    raise ValueError(f"AGENT_PROVIDER inválido: {escolhido!r}. Use 'openrouter' ou 'anthropic'.")
