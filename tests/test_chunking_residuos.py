"""Trechos-lixo de tabela (Cristália Obra II, 29/09).

Em memorial de cabos o "#" é o símbolo de bitola ("# 1,0 mm²   1"). O
RE_HEADING lia isso como heading markdown: cada bitola abria uma "seção", o
chunk seguinte herdava o rótulo absurdo e a sobra numérica entre duas bitolas
("50 \\nm \\n42.5") virava um chunk próprio — curto demais até para receber
embedding. As fixtures reproduzem o padrão real da p. 46 do documento.
"""

from __future__ import annotations

import pytest

from solufarma import chunking

# Padrão real (Cristália Obra II, p. 46), com nomes e textos encurtados.
MEMORIAL_CABOS = (
    "## DESCRIÇÃO\n"
    "42.2 \n"
    "CABO DE ENERGIA SINGELO 0,6/1kV, REFERÊNCIA SINTENAX FLEX, CLASSE 5, NAS SEGUINTES BITOLAS: \n"
    "42.3 \n"
    "BITOLA  Nº DE CONDUTORES \n"
    "42.4 \n"
    "# 1,0 mm²   1 \n"
    "50 \n"
    "m \n"
    "42.5 \n"
    "# 2,5 mm²   1 \n"
    "50 \n"
    "m \n"
    "42.6 \n"
    "CABO DE ENERGIA SINGELO 450/750V, REFERÊNCIA SUPERASTIC FLEX, CLASSE 5, DA PRYSMIAN \n"
    "# 115 \n"
    "# 70mm²  VBC-Y4 \n"
    "1 \n"
    "pç \n"
)


def _doc(paginas):
    return {"arquivo": "Cristalia Obra II.pdf", "hash_documento": "cris", "paginas": paginas}


def test_bitola_de_cabo_nao_vira_secao():
    chunks, _ = chunking.chunkar_documento(_doc([{"numero": 46, "markdown": MEMORIAL_CABOS}]))

    assert {tuple(c.caminho_secao) for c in chunks} == {("DESCRIÇÃO",)}
    # A bitola continua no texto: é dado útil ("cabo de 1,0 mm²"), só não é seção.
    assert any("# 1,0 mm²" in c.texto_puro and "50" in c.texto_puro for c in chunks)


def test_nenhum_chunk_residuo_numerico():
    chunks, _ = chunking.chunkar_documento(_doc([{"numero": 46, "markdown": MEMORIAL_CABOS}]))

    assert all(not chunking._e_residuo(c.texto_puro) for c in chunks)


@pytest.mark.parametrize(
    "titulo",
    ["1,0 mm²   1", "35 mm²", "115", "1,5 mm² +SH  2", "70mm²  VBC-Y4", "**240 MM2**", "3 pç"],
)
def test_titulo_que_e_dado(titulo):
    assert chunking._titulo_e_dado(titulo)


@pytest.mark.parametrize(
    "titulo",
    [
        "1. DO OBJETO",
        "A. ARQUITETURA",
        "ANEXO I – TERMO DE REFERÊNCIA",
        "GASES",
        "2.1 Instalações elétricas",
        "3 MEDIÇÕES",
        "Protocolo de Assinatura(s)",
    ],
)
def test_titulo_de_secao_real(titulo):
    assert not chunking._titulo_e_dado(titulo)


def test_heading_real_continua_sendo_heading():
    md = "# 1. DO OBJETO\nTexto do objeto.\n## 2.1 Instalações elétricas\nTexto elétrico."
    blocos = chunking.parsear_blocos(chunking.costurar([{"numero": 1, "markdown": md}]))

    assert [b.caminho for b in blocos] == [["1. DO OBJETO"], ["1. DO OBJETO", "2.1 Instalações elétricas"]]


def test_celula_numerica_de_tabela_nao_vira_pseudo_secao():
    assert chunking._pseudo_heading_tabela("| 35 MM² | | |") is None
    assert chunking._pseudo_heading_tabela("| 115 | | |") is None
    assert chunking._pseudo_heading_tabela("| GASES | | |") == "GASES"


def _chunk(texto, secao, pag=1):
    return chunking.Chunk(
        id=f"x#{pag}",
        texto=f"[doc | {secao} | p. {pag}]\n{texto}",
        texto_puro=texto,
        tipo="prosa",
        caminho_secao=[secao],
        pagina_inicio=pag,
        pagina_fim=pag,
        n_chars=len(texto),
    )


def test_residuo_funde_com_o_anterior_mesmo_com_secao_diferente():
    anterior = _chunk("CABO DE ENERGIA SINGELO, NAS SEGUINTES BITOLAS: " * 10, "CABOS", 45)
    residuo = _chunk("50 \nm \n42.5", "OUTRA", 46)

    saida = chunking._fundir_residuos([anterior, residuo])

    assert len(saida) == 1
    assert saida[0].texto_puro.endswith("42.5")
    assert saida[0].pagina_fim == 46


def test_residuo_sem_anterior_e_descartado():
    saida = chunking._fundir_residuos([_chunk("Página 6 de 8", "X"), _chunk("Texto útil " * 50, "Y")])

    assert [c.caminho_secao for c in saida] == [["Y"]]


def test_frase_curta_com_palavras_nao_e_residuo():
    # Seção real com uma frase só (Hipolabor, Delta): continua chunk próprio.
    assert not chunking._e_residuo("Os sistemas foram instalados conforme descritivo abaixo:")


def test_bloco_longo_cita_a_pagina_de_cada_pedaco(monkeypatch):
    """Sem heading falso partindo o memorial, o bloco atravessa dezenas de
    páginas: cada chunk precisa citar a SUA página, não a do início do bloco."""
    monkeypatch.setattr(chunking.config, "ALVO_CHARS", 300)
    monkeypatch.setattr(chunking.config, "MIN_CHARS", 50)
    paginas = [
        {"numero": n, "markdown": f"Item da página {n}. " + "Descrição do serviço executado. " * 8}
        for n in range(10, 16)
    ]
    paginas[0]["markdown"] = "## DESCRIÇÃO\n" + paginas[0]["markdown"]
    chunks, _ = chunking.chunkar_documento(_doc(paginas))

    assert len(chunks) >= 3
    for c in chunks:
        primeira = int(c.texto_puro.split("Item da página ")[1].split(".")[0]) if (
            c.texto_puro.startswith("Item da página ")
        ) else None
        if primeira is not None:
            assert c.pagina_inicio == primeira
        assert c.texto.startswith(f"[Cristalia Obra II | DESCRIÇÃO | p. {c.pagina_inicio}]")
    assert chunks[-1].pagina_fim == 15
    assert chunks[0].pagina_inicio == 10 and chunks[-1].pagina_inicio > 10
