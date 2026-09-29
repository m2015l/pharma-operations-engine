"""
Classificação/sumarização de documentos (`solufarma.classificacao`) — offline,
com `FakeLLM` e chunks sintéticos que imitam o layout real (cabeçalho
contextual do chunker, OCR ruidoso de CAT do CREA-SP + atestado anexo).
"""

from __future__ import annotations

import json

import pytest

from solufarma import classificacao as cl
from solufarma_rag.agent.llm import FakeLLM

CHUNKS = [
    cl.ChunkEntrada(
        chunk_index=1,
        pagina_inicio=1,
        pagina_fim=1,
        content_hash="h1",
        conteudo=(
            "[Trocadores de Calor PW e WFI (CAT SJC-02085) | p. 1]\n"
            "CERTIDAO DL ACERVO TECNICO — CAT\n"
            "CERTIDAO N°: SJC-02085\n"
            "Contratada\nTep Tecnologia emPrôjètos de Engenharia Ltda.\n"
            "R$ 497:12000 (Julho/2006)\nInstituto Buthntari.\n"
        ),
    ),
    cl.ChunkEntrada(
        chunk_index=2,
        pagina_inicio=2,
        pagina_fim=3,
        secao="ATESTADO DE CAPACIDADE TECNICA",
        content_hash="h2",
        conteudo=(
            "[Trocadores de Calor PW e WFI (CAT SJC-02085) | ATESTADO | p. 2]\n"
            "Atestamos que a empresa TEP TECNOLOGIA EM PROJETOS DE ENGENHARIA LTDA. corn "
            "sede no municIpio de São José dos Campos, inscrita no CNPJ sob o n°. "
            "02.905.709/0001-61, executou o projeto executivo, montagem e comissionamento "
            "do sistema de trocadores de calor para os tanques de agua PW e WFI, da nova "
            "planta de produção de vacina contra Influenza. Capacidade de 4500 L/h.\n"
            "Valor do Contrato: R$ 497.120,00\nPerlodo de Execuçâo: Julho a Setembro/2006\n"
            "FUNDAcAO BUTANTAN\n"
        ),
    ),
]


def resposta_boa(**sobrescreve) -> str:
    dados = {
        "tipo_documento": {"valor": "cat", "pagina": 1, "trecho": "CERTIDAO N°: SJC-02085"},
        "numero_documento": {"valor": "SJC-02085", "pagina": 1, "trecho": "SJC-02085"},
        "orgao_contratante": {
            "valor": "Fundação Butantan",
            "pagina": 2,
            "trecho": "FUNDAcAO BUTANTAN",
        },
        "executante": {
            "valor": "TEP Tecnologia em Projetos de Engenharia Ltda.",
            "pagina": 2,
            "trecho": "TEP TECNOLOGIA EM PROJETOS DE ENGENHARIA LTDA",
        },
        "executante_grupo": {"valor": "tep", "pagina": 2},
        "consorcio_membros": [],
        "disciplinas": [
            {"valor": "agua_purificada", "pagina": 2},
            {"valor": "mecanica", "pagina": 2},
            {"valor": "automacao_instrumentacao", "pagina": 2},
        ],
        "atividades": [
            {"valor": "projeto", "pagina": 2},
            {"valor": "comissionamento", "pagina": 2},
        ],
        "tipo_instalacao": {
            "valor": "biotecnologia",
            "pagina": 2,
            "trecho": "vacina contra Influenza",
        },
        "classificacao_iso": [],
        "periodo": {"inicio": "2006-07", "fim": "2006-09", "pagina": 2},
        "valor_contrato": {"valor": 497120.0, "texto": "R$ 497.120,00", "pagina": 2},
        "quantitativos_chave": [
            {
                "descricao": "capacidade do trocador",
                "quantidade": "4500",
                "unidade": "L/h",
                "pagina": 2,
            }
        ],
        "local": {"municipio": "São Paulo", "uf": "SP", "pagina": 1},
        "resumo": "A TEP executou o projeto, montagem e comissionamento de trocadores de calor.",
    }
    dados.update(sobrescreve)
    return json.dumps(dados, ensure_ascii=False)


# --- contexto -----------------------------------------------------------------


def test_contexto_tira_cabecalho_e_marca_pagina():
    texto, truncado = cl.montar_contexto(CHUNKS, 100_000)
    assert not truncado
    assert "[p. 1]" in texto and "[p. 2-3 | ATESTADO DE CAPACIDADE TECNICA]" in texto
    assert "Trocadores de Calor PW e WFI (CAT" not in texto  # cabeçalho repetido saiu


def test_contexto_trunca_mantendo_todos_os_chunks():
    grandes = [
        cl.ChunkEntrada(i, f"[t | p. {i}]\n" + ("x" * (100 if i == 0 else 5000)), i, i)
        for i in range(4)
    ]
    texto, truncado = cl.montar_contexto(grandes, 3000)
    assert truncado
    for i in range(4):
        assert f"[p. {i}]" in texto  # nenhuma seção some
    assert "x" * 100 in texto  # o pequeno entra inteiro


def test_orcamento_nao_passa_do_limite():
    cotas = cl._orcamento_por_chunk([10, 500, 2000, 50], 1000)
    assert sum(cotas) <= 1000
    assert cotas[0] == 10 and cotas[3] == 50


def test_hash_muda_quando_texto_muda():
    h1 = cl.hash_conteudo(CHUNKS)
    outro = [CHUNKS[0], cl.ChunkEntrada(2, "novo", 2, 2, content_hash="h2b")]
    assert cl.hash_conteudo(outro) != h1


def test_pistas_da_triagem_acham_tep():
    pistas = cl.pistas_triagem(CHUNKS)
    assert pistas["executante_grupo"]["valor"] == "tep"


# --- parse ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "bruto",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'Aqui está:\n{"a": 1}\nFim.'],
)
def test_extrair_json_tolerante(bruto):
    assert cl.extrair_json(bruto) == {"a": 1}


def test_extrair_json_rejeita_lixo():
    with pytest.raises(cl.RespostaInvalida):
        cl.extrair_json("não sei")


# --- validação ---------------------------------------------------------------------


def test_classificacao_completa_e_verificada():
    llm = FakeLLM(respostas=[resposta_boa()])
    res = cl.classificar_documento(llm, CHUNKS, "titulo", modelo="fake/modelo")
    c = res.classificacao
    assert c["tipo_documento"]["valor"] == "cat"
    assert c["executante_grupo"]["valor"] == "tep"
    assert c["executante"]["verificado"] is True
    assert c["valor_contrato"] == {
        "valor": 497120.0,
        "texto": "R$ 497.120,00",
        "pagina": 2,
        "verificado": True,
    }
    assert [d["valor"] for d in c["disciplinas"]] == [
        "agua_purificada",
        "mecanica",
        "automacao_instrumentacao",
    ]
    assert c["meta"]["modelo"] == "fake/modelo"
    assert c["meta"]["hash_conteudo"] == cl.hash_conteudo(CHUNKS)
    assert res.resumo.startswith("A TEP")
    assert res.avisos == []
    # o prompt levou texto, pistas e as regras de "null"
    chamada = llm.chamadas[0]
    assert "nunca deduza" in chamada["system"].lower()
    assert "PISTAS" in chamada["mensagens"][0]["content"]


def test_vocabulario_fora_da_lista_e_descartado():
    llm = FakeLLM(
        respostas=[
            resposta_boa(
                disciplinas=[{"valor": "hvac", "pagina": 2}, {"valor": "paisagismo", "pagina": 2}],
                executante_grupo={"valor": "Empresa Y", "pagina": 2},
            )
        ]
    )
    res = cl.classificar_documento(llm, CHUNKS)
    assert [d["valor"] for d in res.classificacao["disciplinas"]] == ["hvac"]
    assert res.classificacao["executante_grupo"] is None
    assert any("paisagismo" in a for a in res.avisos)
    assert any("regex sugere 'tep'" in a for a in res.avisos)


def test_pagina_fora_do_documento_vira_null():
    llm = FakeLLM(respostas=[resposta_boa(numero_documento={"valor": "SJC-02085", "pagina": 40})])
    res = cl.classificar_documento(llm, CHUNKS)
    assert res.classificacao["numero_documento"]["pagina"] is None
    assert any("fora do documento" in a for a in res.avisos)


def test_valor_inventado_fica_nao_verificado():
    llm = FakeLLM(
        respostas=[
            resposta_boa(
                valor_contrato={"valor": 1_000_000, "texto": "R$ 1.000.000,00", "pagina": 2}
            )
        ]
    )
    res = cl.classificar_documento(llm, CHUNKS)
    assert res.classificacao["valor_contrato"]["verificado"] is False
    assert any("valor_contrato" in a for a in res.avisos)


def test_iso_que_nao_esta_no_texto_e_descartada():
    llm = FakeLLM(respostas=[resposta_boa(classificacao_iso=[{"valor": "ISO 7", "pagina": 2}])])
    res = cl.classificar_documento(llm, CHUNKS)
    assert res.classificacao["classificacao_iso"] == []


def test_divergencia_com_regex_vira_aviso():
    llm = FakeLLM(respostas=[resposta_boa(executante_grupo={"valor": "solufarma", "pagina": 2})])
    res = cl.classificar_documento(llm, CHUNKS)
    assert res.classificacao["executante_grupo"]["valor"] == "solufarma"  # não censura o LLM
    assert any("regex disse 'tep'" in a for a in res.avisos)


def test_campos_ausentes_ficam_null():
    llm = FakeLLM(respostas=[json.dumps({"tipo_documento": {"valor": "outro"}, "resumo": "x."})])
    res = cl.classificar_documento(llm, CHUNKS)
    c = res.classificacao
    assert c["valor_contrato"] is None and c["periodo"] is None and c["local"] is None
    assert c["disciplinas"] == [] and c["quantitativos_chave"] == []


def test_datas_e_uf_invalidas_sao_descartadas():
    llm = FakeLLM(
        respostas=[
            resposta_boa(
                periodo={"inicio": "julho/2006", "fim": "2006-09", "pagina": 2},
                local={"municipio": "São Paulo", "uf": "São Paulo", "pagina": 1},
            )
        ]
    )
    res = cl.classificar_documento(llm, CHUNKS)
    assert res.classificacao["periodo"]["inicio"] is None
    assert res.classificacao["periodo"]["fim"] == "2006-09"
    assert res.classificacao["local"]["uf"] is None


def test_json_quebrado_tenta_de_novo_uma_vez():
    llm = FakeLLM(respostas=["desculpe, segue", resposta_boa()])
    res = cl.classificar_documento(llm, CHUNKS)
    assert res.uso["chamadas"] == 2
    assert res.classificacao["tipo_documento"]["valor"] == "cat"


def test_json_quebrado_duas_vezes_levanta():
    llm = FakeLLM(respostas=["nada", "nada de novo"])
    with pytest.raises(cl.RespostaInvalida):
        cl.classificar_documento(llm, CHUNKS)


def test_documento_sem_chunks_recusa():
    with pytest.raises(ValueError):
        cl.classificar_documento(FakeLLM(), [])


def test_custo_estimado():
    assert cl.estimar_custo(1_000_000, 0.10, 0.40, tokens_saida=0) == pytest.approx(0.10)
    assert cl.estimar_tokens("x" * 300) == 101


@pytest.mark.parametrize(
    ("texto", "valor", "esperado"),
    [
        ("salas ISO classe 5 e ISO 7", "ISO 5", True),
        ("areas ISO Classe 8", "ISO 8", True),
        ("classe ISO 7 conforme NBR", "ISO 7", True),
        ("ISO classes B, C  D", "Classe D", True),
        ("certificação ISO 9001", "ISO 9", False),
        ("conforme NBR-ISO 14.644", "ISO 1", False),
        ("sem classificação", "ISO 7", False),
    ],
)
def test_iso_aceita_grafias_reais(texto, valor, esperado):
    v = cl.Validador([cl.ChunkEntrada(1, texto, 1, 1)])
    assert v.iso_no_texto(valor) is esperado
