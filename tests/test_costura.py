"""
INVARIANTE 3 — página não é fronteira semântica.

A costura acontece ANTES de qualquer corte. Sem ela, todo corte de página vira
corte de chunk: a tabela das págs. 44-45 vira dois chunks, o segundo sem
cabeçalho de coluna, e "quanto de cabo #240MM2 foi fornecido" não recupera nada.
"""

from __future__ import annotations

from solufarma import chunking


def test_tabela_dividida_vira_um_bloco_so(tabela_dividida):
    fluxo = chunking.costurar(tabela_dividida)
    blocos = chunking.parsear_blocos(fluxo)

    tabelas = [b for b in blocos if b.tipo == "tabela"]
    assert len(tabelas) == 1, "a tabela das págs. 44-45 deveria ser um bloco único"
    assert tabelas[0].pag_ini == 44
    assert tabelas[0].pag_fim == 45


def test_cabecalho_reimpresso_e_descartado_na_costura(tabela_dividida):
    """
    O OCR reimprime o cabeçalho herdado na pág. 45 (a regra 5 do prompt manda).
    A costura descarta essa cópia — senão o cabeçalho aparece no meio do corpo
    e desalinha a janela de linhas do chunk_tabela.
    """
    fluxo = chunking.costurar(tabela_dividida)
    linhas = [linha for linha, _pag in fluxo]

    assert sum(1 for ln in linhas if "Descrição" in ln) == 1
    assert sum(1 for ln in linhas if chunking.RE_SEPARADOR_TABELA.match(ln)) == 1


def test_todas_as_linhas_de_dados_sobrevivem(tabela_dividida):
    """Descartar cabeçalho não pode descartar dado."""
    fluxo = chunking.costurar(tabela_dividida)
    texto = "\n".join(linha for linha, _ in fluxo)

    for valor in ("19.541,00", "16.250,00", "3.050,00", "300,00"):
        assert valor in texto, f"a linha com {valor} sumiu na costura"


def test_formato_numerico_brasileiro_preservado(tabela_dividida):
    """`1.490,00` não pode virar `1490.00` em lugar nenhum do pipeline."""
    fluxo = chunking.costurar(tabela_dividida)
    texto = "\n".join(linha for linha, _ in fluxo)
    assert "19.541,00" in texto
    assert "19541.00" not in texto


def test_paragrafo_dividido_e_emendado(paragrafo_dividido):
    """Parágrafo cortado pela paginação física vira uma frase só."""
    fluxo = chunking.costurar(paragrafo_dividido)
    texto = " ".join(linha for linha, _ in fluxo)
    assert "requisições de resistência química" in texto


def test_marcas_de_continuacao_nao_vazam_para_o_chunk(tabela_dividida):
    """Os comentários HTML são protocolo interno; não podem ir para o embedding."""
    fluxo = chunking.costurar(tabela_dividida)
    texto = "\n".join(linha for linha, _ in fluxo)
    assert "TABELA_CONTINUA" not in texto
    assert "PARAGRAFO_CONTINUA" not in texto


def test_pagina_vazia_e_ignorada():
    paginas = [
        {"numero": 1, "markdown": "conteúdo"},
        {"numero": 2, "markdown": ""},
        {"numero": 3, "markdown": "mais conteúdo"},
    ]
    fluxo = chunking.costurar(paginas)
    assert [linha for linha, _ in fluxo] == ["conteúdo", "mais conteúdo"]


def test_paginas_fora_de_ordem_sao_reordenadas():
    paginas = [
        {"numero": 3, "markdown": "terceira"},
        {"numero": 1, "markdown": "primeira"},
        {"numero": 2, "markdown": "segunda"},
    ]
    fluxo = chunking.costurar(paginas)
    assert [linha for linha, _ in fluxo] == ["primeira", "segunda", "terceira"]
