"""
Resposta do VLM cortada no teto de tokens não pode virar cache.

Regressão de 07/10 e 08/10: na pág. 35 do Complexo Farmacêutico Industrial 3ª fase e nas 16 e 193 do
HUC o modelo parou de escrever a tabela no meio e encheu o resto da resposta
com espaços até bater em 8.000 tokens. A página saiu pela metade, o resultado
foi para o cache, e toda reexecução devolvia a mesma metade — de graça e sem
aviso. Repetir a chamada resolveu nos três casos, na primeira tentativa.

Nenhuma chamada de rede aqui: `requests.post` é trocado por uma fila de respostas.
"""

from __future__ import annotations

import json

import pytest

from pharma_ops import config, extracao

JPEG = b"\xff\xd8pagina-de-teste"
BOA = {"markdown": "| 5.14 | ISOLAMENTO | 1,00 | vb |", "confianca": 0.93, "observacoes": ""}


class _Resposta:
    status_code = 200
    ok = True
    text = ""

    def __init__(self, conteudo: str, tokens_saida: int, finish_reason: str = "stop"):
        self._corpo = {
            "choices": [{"message": {"content": conteudo}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 3000, "completion_tokens": tokens_saida},
        }

    def json(self) -> dict:
        return self._corpo


def _cortada() -> _Resposta:
    """JSON aberto que nunca fecha, parado no teto de tokens."""
    return _Resposta('{"markdown": "| 5.14 | ISOLAMENTO |\\n| ', 8000, "length")


def _boa(tokens_saida: int = 2100) -> _Resposta:
    return _Resposta(json.dumps(BOA, ensure_ascii=False), tokens_saida)


@pytest.fixture
def fila(monkeypatch, tmp_path):
    """Troca a rede por uma fila de respostas e isola o cache em tmp_path."""
    respostas: list[_Resposta] = []
    chamadas: list[int] = []

    def post(*args, **kwargs):
        chamadas.append(1)
        return respostas.pop(0)

    monkeypatch.setattr(extracao.requests, "post", post)
    monkeypatch.setattr(extracao.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "DIR_CACHE", tmp_path)
    return respostas, chamadas, tmp_path


def test_resposta_cortada_e_repetida_e_a_boa_fica(fila):
    respostas, chamadas, cache = fila
    respostas.extend([_cortada(), _boa()])

    resultado, do_cache = extracao.chamar_vlm(JPEG, "", "chave")

    assert len(chamadas) == 2
    assert do_cache is False
    assert resultado["markdown"] == BOA["markdown"]
    assert resultado["confianca"] == 0.93
    # Só a resposta boa foi para o cache.
    gravados = list(cache.glob("*.json"))
    assert len(gravados) == 1
    assert json.loads(gravados[0].read_text(encoding="utf-8"))["markdown"] == BOA["markdown"]


def test_custo_conta_tambem_a_chamada_descartada(fila):
    """Senão o relatório de custo sai menor que a conta do OpenRouter."""
    respostas, _, _ = fila
    respostas.extend([_cortada(), _boa(tokens_saida=2100)])

    resultado, _ = extracao.chamar_vlm(JPEG, "", "chave")

    assert resultado["_tokens_saida"] == 8000 + 2100
    assert resultado["_tokens_entrada"] == 3000 * 2


def test_cortada_em_todas_as_tentativas_nao_vai_para_o_cache(fila):
    respostas, chamadas, cache = fila
    respostas.extend([_cortada() for _ in range(10)])

    resultado, do_cache = extracao.chamar_vlm(JPEG, "", "chave")

    assert len(chamadas) == 1 + extracao.RETENTATIVAS_RESPOSTA_RUIM
    assert do_cache is False
    assert list(cache.glob("*.json")) == []
    # A página segue marcada para revisão, não some nem passa por boa.
    assert resultado["confianca"] <= 0.4
    assert resultado["confianca"] < config.LIMIAR_CONFIANCA_REVISAO
    assert "cortada" in resultado["observacoes"].lower()


def test_proxima_execucao_tenta_de_novo_a_pagina_que_falhou(fila):
    """Sem cache da resposta ruim, reexecutar o documento refaz só essa página."""
    respostas, chamadas, _ = fila
    respostas.extend([_cortada() for _ in range(1 + extracao.RETENTATIVAS_RESPOSTA_RUIM)])
    extracao.chamar_vlm(JPEG, "", "chave")

    respostas.append(_boa())
    resultado, do_cache = extracao.chamar_vlm(JPEG, "", "chave")

    assert do_cache is False
    assert resultado["markdown"] == BOA["markdown"]
    # E a terceira execução sai do cache, sem custo.
    antes = len(chamadas)
    _, do_cache = extracao.chamar_vlm(JPEG, "", "chave")
    assert do_cache is True
    assert len(chamadas) == antes


def test_resposta_que_nao_e_json_tambem_e_repetida(fila):
    respostas, chamadas, _ = fila
    respostas.extend([_Resposta("desculpe, não consegui ler a página", 40), _boa()])

    resultado, _ = extracao.chamar_vlm(JPEG, "", "chave")

    assert len(chamadas) == 2
    assert resultado["markdown"] == BOA["markdown"]


def test_resposta_boa_de_primeira_faz_uma_chamada_so(fila):
    respostas, chamadas, _ = fila
    respostas.append(_boa())

    extracao.chamar_vlm(JPEG, "", "chave")

    assert len(chamadas) == 1
