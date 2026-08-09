"""
INVARIANTE 4 — a saída do OCR é Markdown estruturado.

Se a hierarquia `A.1.1 vinílicos` chegasse como texto corrido, o caminho de
seção seria irrecuperável e todo chunk perderia o contexto que faz a busca
"acabamento de piso SENAI CETIQT" encontrar o trecho certo.
"""

from __future__ import annotations

from solufarma import chunking


def test_caminho_de_secao_reflete_a_hierarquia(prosa_hierarquica):
    fluxo = chunking.costurar(prosa_hierarquica)
    blocos = chunking.parsear_blocos(fluxo)

    caminhos = [b.caminho for b in blocos]
    assert ["A. Arquitetura"] in caminhos
    assert ["A. Arquitetura", "A.1 acabamentos de pisos"] in caminhos
    assert [
        "A. Arquitetura",
        "A.1 acabamentos de pisos",
        "A.1.1 vinílicos",
    ] in caminhos


def test_heading_de_mesmo_nivel_substitui_o_irmao():
    """`A.2` não pode ficar aninhado sob `A.1`."""
    paginas = [
        {
            "numero": 1,
            "markdown": (
                "## A. Arquitetura\n"
                "### A.1 pisos\ntexto do A.1\n"
                "### A.2 vedos\ntexto do A.2"
            ),
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))
    caminho_a2 = next(b.caminho for b in blocos if "texto do A.2" in "\n".join(b.linhas))
    assert caminho_a2 == ["A. Arquitetura", "A.2 vedos"]


def test_cabecalho_contextual_carrega_documento_secao_e_pagina():
    cab = chunking.cabecalho_contextual(
        "SENAI CETIQT CAT 576640", ["A. Arquitetura", "A.1.1 vinílicos"], 8
    )
    assert "SENAI CETIQT CAT 576640" in cab
    assert "A. Arquitetura > A.1.1 vinílicos" in cab
    assert "p. 8" in cab


def test_chunk_de_tabela_repete_o_cabecalho_em_cada_janela(tabela_dividida, monkeypatch):
    """
    Cada janela precisa ser autossuficiente: sem o cabeçalho, a linha
    `#240MM2 COR VERDE (TERRA) | M | 300,00` é um vetor sem sinal semântico.
    """
    monkeypatch.setattr(chunking.config, "LINHAS_POR_CHUNK_TABELA", 2)

    blocos = chunking.parsear_blocos(chunking.costurar(tabela_dividida))
    tabela = next(b for b in blocos if b.tipo == "tabela")
    chunks = chunking.chunk_tabela(tabela, "SENAI CETIQT", "abc123", [0])

    assert chunks, "a tabela deveria gerar ao menos um chunk"
    for c in chunks:
        assert "Descrição" in c.texto_puro, "janela sem cabeçalho de coluna"
        assert c.tipo == "tabela"


def test_janela_orfa_volta_para_o_chunk_anterior(monkeypatch):
    """Chunk de 2 linhas de planilha não tem sinal para recuperar nada."""
    monkeypatch.setattr(chunking.config, "LINHAS_POR_CHUNK_TABELA", 5)

    linhas = ["| Descrição | Un | Qtd |", "|---|---|---|"]
    linhas += [f"| ITEM {i} | M | {i}00,00 |" for i in range(7)]  # 5 + 2 órfãs

    from solufarma.modelos import Bloco

    bloco = Bloco("tabela", linhas, ["Planilha"], 44, 44)
    chunks = chunking.chunk_tabela(bloco, "doc", "h", [0])

    assert len(chunks) == 1, "as 2 linhas órfãs deveriam ter voltado para a janela anterior"
    assert "ITEM 6" in chunks[0].texto_puro


def test_linhas_de_planilha_viram_dados_relacionais(tabela_dividida):
    """
    "Quanto de piso vinílico já fornecemos?" é um SUM, e RAG não soma.
    As linhas precisam sair também como registros para `itens_planilha`.
    """
    blocos = chunking.parsear_blocos(chunking.costurar(tabela_dividida))
    itens = chunking.extrair_linhas_tabela(blocos, "abc123")

    assert len(itens) == 4, "4 linhas de dados, sem contar cabeçalho e separador"
    assert all(len(i["celulas"]) == 3 for i in itens)
    assert itens[0]["pagina"] == 44
    # O valor bruto precisa chegar intacto — o parse pt-BR acontece na indexação.
    assert any("19.541,00" in c for i in itens for c in i["celulas"])


def test_separador_de_tabela_nao_vira_item(tabela_dividida):
    blocos = chunking.parsear_blocos(chunking.costurar(tabela_dividida))
    itens = chunking.extrair_linhas_tabela(blocos, "abc123")
    assert not any(set("".join(i["celulas"])) <= {"-", ":", " "} for i in itens)


def test_documento_completo_produz_chunks_e_itens(documento_extraido):
    chunks, itens = chunking.chunkar_documento(documento_extraido)

    assert chunks, "documento deveria gerar chunks"
    assert itens, "documento com tabela deveria gerar itens de planilha"
    assert {c.tipo for c in chunks} <= {"prosa", "tabela", "metadados"}
    for c in chunks:
        assert c.texto_puro in c.texto, "texto_puro precisa ser prefixo-livre de texto"
        assert c.pagina_inicio > 0, "sem página não há citação de fonte possível"


def test_ids_de_chunk_sao_unicos(documento_extraido):
    chunks, _ = chunking.chunkar_documento(documento_extraido)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
