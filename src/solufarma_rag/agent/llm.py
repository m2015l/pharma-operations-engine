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

    def __init__(
        self,
        model: str | None = None,
        *,
        json_mode: bool = False,
        temperatura: float | None = None,
    ) -> None:
        """`json_mode` e `temperatura` servem a usos fora do agente (ex.: a
        classificação de documentos, que quer JSON e saída estável). O agente
        não passa nenhum dos dois e continua com o comportamento de antes.

        Depois de cada chamada, `ultimo_uso` guarda tokens e o custo real em
        US$ devolvido pelo OpenRouter (`usage.cost`), quando disponível.
        """
        self._json_mode = json_mode
        self._temperatura = temperatura
        self.ultimo_uso: dict = {}
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
        extras: dict = {}
        if self._json_mode:
            extras["response_format"] = {"type": "json_object"}
        if self._temperatura is not None:
            extras["temperature"] = self._temperatura
        resposta = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *mensagens],
            # Pede ao OpenRouter o custo real da chamada em `usage.cost`.
            extra_body={"usage": {"include": True}},
            **extras,
        )
        uso = resposta.usage
        self.ultimo_uso = {
            "modelo": self._model,
            "tokens_entrada": getattr(uso, "prompt_tokens", None),
            "tokens_saida": getattr(uso, "completion_tokens", None),
            "custo_usd": getattr(uso, "cost", None),
        }
        return resposta.choices[0].message.content or ""


class OpenAILLM:
    """Modelo da própria OpenAI, pela API direta (`OPENAI_API_KEY`).

    POR QUE EXISTE
    Alternativa quando o OpenRouter está indisponível (ex.: limite mensal da
    chave estourado em 29/09) e há crédito na conta da OpenAI. Os prompts foram
    calibrados no Claude: trocar o modelo do agente exige conferir a qualidade
    das respostas de novo (golden set / auditoria), não é troca neutra.

    Os modelos recentes da OpenAI usam `max_completion_tokens` (não
    `max_tokens`) e alguns não aceitam `temperature`; se a API recusar a
    temperatura, a chamada é refeita sem ela. O custo em `ultimo_uso` só é
    calculado se `OPENAI_PRECO_ENTRADA`/`OPENAI_PRECO_SAIDA` (US$/Mtok) estiverem
    no `.env` — a API da OpenAI não devolve custo.
    """

    MODELO_PADRAO = "gpt-5-mini"

    def __init__(
        self,
        model: str | None = None,
        *,
        json_mode: bool = False,
        temperatura: float | None = None,
        client=None,
    ) -> None:
        import os

        self._json_mode = json_mode
        self._temperatura = temperatura
        self.ultimo_uso: dict = {}
        self._model = model or os.getenv("OPENAI_MODELO") or self.MODELO_PADRAO
        self._preco_ent = _float_env("OPENAI_PRECO_ENTRADA")
        self._preco_sai = _float_env("OPENAI_PRECO_SAIDA")
        if client is not None:  # testes injetam um dublê
            self._client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - caminho de produção
            raise ImportError("O pacote 'openai' não está instalado.") from exc
        chave = os.getenv("OPENAI_API_KEY", "")
        if not chave:
            raise RuntimeError("OPENAI_API_KEY não está no .env.")
        self._client = OpenAI(api_key=chave)

    def completar(self, system: str, mensagens: list[dict], max_tokens: int = 4096) -> str:
        pedido: dict = {
            "model": self._model,
            "max_completion_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *mensagens],
        }
        if self._json_mode:
            pedido["response_format"] = {"type": "json_object"}
        if self._temperatura is not None:
            pedido["temperature"] = self._temperatura
        try:
            resposta = self._client.chat.completions.create(**pedido)
        except Exception as exc:
            if "temperature" not in pedido or "temperature" not in str(exc):
                raise
            pedido.pop("temperature")
            resposta = self._client.chat.completions.create(**pedido)
        uso = resposta.usage
        ent = getattr(uso, "prompt_tokens", None)
        sai = getattr(uso, "completion_tokens", None)
        custo = None
        if None not in (ent, sai, self._preco_ent, self._preco_sai):
            custo = (ent * self._preco_ent + sai * self._preco_sai) / 1_000_000
        self.ultimo_uso = {
            "modelo": self._model,
            "tokens_entrada": ent,
            "tokens_saida": sai,
            "custo_usd": custo,
        }
        return resposta.choices[0].message.content or ""


def _float_env(nome: str) -> float | None:
    import os

    valor = os.getenv(nome, "").strip()
    return float(valor) if valor else None


def criar_llm(nome: str | None = None) -> LLMClient:
    """Fábrica: escolhe o cliente conforme AGENT_PROVIDER do `.env`.

    Padrão `openrouter` (Claude). `openai` usa a API direta da OpenAI com
    `OPENAI_MODELO`; `anthropic` usa a API direta da Anthropic.
    """
    import os

    escolhido = (nome or os.getenv("AGENT_PROVIDER", "openrouter")).strip().lower()
    if escolhido == "openrouter":
        return OpenRouterLLM()
    if escolhido == "anthropic":
        return AnthropicLLM()
    if escolhido == "openai":
        return OpenAILLM()
    raise ValueError(
        f"AGENT_PROVIDER inválido: {escolhido!r}. Use 'openrouter', 'openai' ou 'anthropic'."
    )


def criar_llm_json(modelo_openrouter: str) -> LLMClient:
    """Cliente para saída JSON estável (classificação), conforme CLASSIFICACAO_PROVIDER.

    `openrouter` (padrão) usa `modelo_openrouter`; `openai` usa
    `CLASSIFICACAO_MODELO_OPENAI` (ou `OPENAI_MODELO`, ou o padrão da classe).
    """
    import os

    provedor = os.getenv("CLASSIFICACAO_PROVIDER", "openrouter").strip().lower()
    if provedor == "openai":
        modelo = os.getenv("CLASSIFICACAO_MODELO_OPENAI") or None
        return OpenAILLM(model=modelo, json_mode=True, temperatura=0)
    if provedor == "openrouter":
        return OpenRouterLLM(model=modelo_openrouter, json_mode=True, temperatura=0)
    raise ValueError(f"CLASSIFICACAO_PROVIDER inválido: {provedor!r}. Use 'openrouter' ou 'openai'.")
