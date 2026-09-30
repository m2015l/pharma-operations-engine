"""OpenAILLM: formato do pedido para a API da OpenAI, sem rede (cliente dublê)."""

from types import SimpleNamespace

import pytest

from solufarma_rag.agent.llm import OpenAILLM, criar_llm, criar_llm_json


class ClienteFalso:
    def __init__(self, recusar_temperatura: bool = False):
        self.pedidos: list[dict] = []
        self._recusar = recusar_temperatura
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **pedido):
        self.pedidos.append(pedido)
        if self._recusar and "temperature" in pedido:
            raise ValueError("Unsupported value: 'temperature' does not support 0")
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=200),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        )


def test_usa_max_completion_tokens_e_json(monkeypatch):
    monkeypatch.delenv("OPENAI_PRECO_ENTRADA", raising=False)
    cliente = ClienteFalso()
    llm = OpenAILLM(model="gpt-teste", json_mode=True, client=cliente)
    assert llm.completar("sistema", [{"role": "user", "content": "oi"}], max_tokens=50) == '{"ok": true}'
    pedido = cliente.pedidos[0]
    assert pedido["max_completion_tokens"] == 50
    assert "max_tokens" not in pedido
    assert pedido["response_format"] == {"type": "json_object"}
    assert pedido["messages"][0] == {"role": "system", "content": "sistema"}
    assert llm.ultimo_uso["custo_usd"] is None


def test_refaz_sem_temperatura_quando_o_modelo_recusa():
    cliente = ClienteFalso(recusar_temperatura=True)
    llm = OpenAILLM(model="gpt-teste", temperatura=0, client=cliente)
    llm.completar("s", [])
    assert len(cliente.pedidos) == 2
    assert "temperature" not in cliente.pedidos[1]


def test_custo_calculado_com_precos_do_env(monkeypatch):
    monkeypatch.setenv("OPENAI_PRECO_ENTRADA", "0.25")
    monkeypatch.setenv("OPENAI_PRECO_SAIDA", "2.00")
    llm = OpenAILLM(model="gpt-teste", client=ClienteFalso())
    llm.completar("s", [])
    assert llm.ultimo_uso["custo_usd"] == pytest.approx((1000 * 0.25 + 200 * 2.0) / 1_000_000)


def test_fabricas_aceitam_openai_e_exigem_chave(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CLASSIFICACAO_PROVIDER", "openai")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        criar_llm("openai")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        criar_llm_json("qualquer/modelo")
    with pytest.raises(ValueError):
        criar_llm("inexistente")
