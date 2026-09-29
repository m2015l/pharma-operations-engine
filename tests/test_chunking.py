"""
INVARIANTE 4 — a saída do OCR é Markdown estruturado.

Se a hierarquia `A.1.1 vinílicos` chegasse como texto corrido, o caminho de
seção seria irrecuperável e todo chunk perderia o contexto que faz a busca
"acabamento de piso SENAI CETIQT" encontrar o trecho certo.
"""

from __future__ import annotations

import pytest

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


# -- I7 (PRECISÃO.md): linha de tabela como divisão de seção ---------------
#
# Reproduz o padrão real do documento (.tmp/acervo_indexado.md, por volta das
# linhas 1948-2007, não versionado — cópia local do texto já indexado):
#     | GASES | | |
#     | **HIDRÁULICA** | | |
# Sem o reconhecimento, o bloco inteiro herdava o heading markdown anterior
# ("FORNECIMENTO E MONTAGEM DE QUADRO DE DISTRIBUIÇÃO..."), que é de outra
# seção do memorial — P7 do PRECISÃO.md. Validado aqui por fixture sintética
# (mesmo padrão dos outros testes deste arquivo, ver nota em conftest.py);
# não houve reindexação real, e o comportamento com as linhas intermediárias
# do documento completo (ex.: "TUBULAÇÕES - GASES ESPECIAIS ( MAT + MDO )",
# que passa dos 40 caracteres e por isso NÃO vira pseudo-seção) não foi
# reconferido chunk a chunk contra uma nova extração completa — só contra
# estes trechos.


def test_linha_de_tabela_maiuscula_curta_vira_pseudo_secao():
    paginas = [
        {
            "numero": 45,
            "markdown": (
                "## FORNECIMENTO E MONTAGEM DE QUADRO DE DISTRIBUIÇÃO\n"
                "| Descrição | UN. | QUANT. |\n"
                "|---|---|---|\n"
                "| QDC-3P-TER | CJ | 1,00 |\n"
                "| GASES | | |\n"
                "| TUBO DE AÇO INOX | M | 3.488,56 |\n"
                "| **HIDRÁULICA** | | |\n"
                "| REGISTRO DE ESFERA | PÇ | 16,00 |"
            ),
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))

    bloco_qdc = next(b for b in blocos if "QDC-3P-TER" in "\n".join(b.linhas))
    assert bloco_qdc.caminho == ["FORNECIMENTO E MONTAGEM DE QUADRO DE DISTRIBUIÇÃO"]

    bloco_gases = next(b for b in blocos if "TUBO DE AÇO INOX" in "\n".join(b.linhas))
    assert bloco_gases.caminho == [
        "FORNECIMENTO E MONTAGEM DE QUADRO DE DISTRIBUIÇÃO",
        "GASES",
    ]

    bloco_hidraulica = next(b for b in blocos if "REGISTRO DE ESFERA" in "\n".join(b.linhas))
    assert bloco_hidraulica.caminho == [
        "FORNECIMENTO E MONTAGEM DE QUADRO DE DISTRIBUIÇÃO",
        "HIDRÁULICA",
    ]
    # GASES e HIDRÁULICA são irmãs (divisões sucessivas), não aninhadas.
    assert "GASES" not in bloco_hidraulica.caminho


def test_pseudo_secao_nao_vira_item_de_planilha():
    """A linha-divisor ('GASES') é consumida como heading, não como dado."""
    paginas = [
        {
            "numero": 45,
            "markdown": "## QUADRO\n| GASES | | |\n| TUBO | M | 10,00 |",
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))
    itens = chunking.extrair_linhas_tabela(blocos, "doc")

    assert not any(i["celulas"][0] == "GASES" for i in itens)
    assert any(i["celulas"][0] == "TUBO" for i in itens)


def test_celula_maiuscula_longa_nao_vira_pseudo_secao():
    """Limite de 40 caracteres (PRECISÃO.md): sem ele, uma descrição de item
    em caixa alta viraria uma seção nova a cada linha."""
    linha_longa = "A" * 41
    paginas = [
        {
            "numero": 1,
            "markdown": f"## SEÇÃO\n| {linha_longa} | | |\n| DADO | X | 1,00 |",
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))
    bloco = next(b for b in blocos if "DADO" in "\n".join(b.linhas))
    assert bloco.caminho == ["SEÇÃO"]


def test_celula_minuscula_nao_vira_pseudo_secao():
    paginas = [
        {
            "numero": 1,
            "markdown": "## SEÇÃO\n| Registros diversos | | |\n| ITEM | X | 1,00 |",
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))
    bloco = next(b for b in blocos if "ITEM" in "\n".join(b.linhas))
    assert bloco.caminho == ["SEÇÃO"]


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


# -- I6/P6 (PRECISÃO.md): rótulo em caixa alta na prosa como seção ----------
#
# Reproduz, com dados trocados, a folha de rosto da CAT do CAU (p.1-2 da CAT
# 576640, `.tmp/acervo_indexado.md`, não versionado): blocos chave-valor
# encabeçados por linhas soltas em caixa alta, com espaço nas pontas, sem
# heading markdown. Antes, tudo virava um bloco sem `caminho_secao` e a área
# certificada ficava escondida no meio (P6). Os rótulos de CATs do CREA
# escaneadas ("ATESTADO DE CAPACIDADE TECNICA", "ESCOPO DOS SERVIOS", sic)
# vêm do lote de 28/09 (`data/extraidos/`, também não versionado).

FOLHA_DE_ROSTO_CAU = (
    "CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO\n"
    "Nº 0000000999999\n"
    " DADOS DO PROFISSIONAL \n"
    "Profissional: FULANA DE TAL\n"
    "Título do Profissional: Arquiteto e Urbanista\n"
    " DADOS DO CONTRATO \n"
    "Contratante: EMPRESA CONTRATANTE EXEMPLO S.A.\n"
    "CPF/CNPJ: 00000000000100\n"
    "Cidade: RIO DE JANEIRO\n"
    "Valor do Contrato: R$ 1.000.000,00\n"
    " ATIVIDADE TÉCNICA REALIZADA \n"
    " 2.1.1  - Execução de obra , 5655.00 m² - metro quadrado;  2.2.4  - Execução de "
    "estrutura metálica , 23537.00 kg - quilograma;\n"
    " ENDEREÇO DA OBRA/SERVIÇO \n"
    "RUA EXEMPLO, S/N\n"
    "SÃO PAULO - SP\n"
)


def _bloco_com(blocos, trecho):
    return next(b for b in blocos if trecho in "\n".join(b.linhas))


def test_folha_de_rosto_sem_heading_vira_secoes_proprias():
    paginas = [
        {"numero": 1, "markdown": FOLHA_DE_ROSTO_CAU},
        {"numero": 3, "markdown": "## ATESTADO DE CAPACIDADE TÉCNICA\nAtestamos que a empresa..."},
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))

    # O título repetido da certidão NÃO é seção (é cabeçalho de toda página).
    assert _bloco_com(blocos, "Nº 0000000999999").caminho == []
    assert _bloco_com(blocos, "FULANA DE TAL").caminho == ["DADOS DO PROFISSIONAL"]
    assert _bloco_com(blocos, "Valor do Contrato").caminho == ["DADOS DO CONTRATO"]
    # Seções irmãs: a nova substitui a anterior, não aninha.
    atividade = _bloco_com(blocos, "5655.00 m²")
    assert atividade.caminho == ["ATIVIDADE TÉCNICA REALIZADA"]
    assert "Contratante" not in "\n".join(atividade.linhas)
    assert _bloco_com(blocos, "RUA EXEMPLO").caminho == ["ENDEREÇO DA OBRA/SERVIÇO"]
    # Heading markdown real estoura os rótulos acumulados.
    assert _bloco_com(blocos, "Atestamos").caminho == ["ATESTADO DE CAPACIDADE TÉCNICA"]


def test_atividade_tecnica_vira_chunk_proprio_com_secao_no_cabecalho():
    """O efeito que o I6 manual obteve no banco: a área certificada num chunk
    só dela, com o rótulo no cabeçalho contextual (que entra no embedding)."""
    doc = {
        "arquivo": "CAT 999999 Exemplo.pdf",
        "hash_documento": "i6teste",
        "paginas": [{"numero": 1, "markdown": FOLHA_DE_ROSTO_CAU}],
    }
    chunks, _ = chunking.chunkar_documento(doc)

    chunk_area = next(c for c in chunks if "5655.00 m²" in c.texto_puro)
    assert chunk_area.caminho_secao == ["ATIVIDADE TÉCNICA REALIZADA"]
    assert chunk_area.texto.startswith("[CAT 999999 Exemplo | ATIVIDADE TÉCNICA REALIZADA | p. 1]")
    assert "Contratante" not in chunk_area.texto_puro


def test_parte_do_documento_contem_as_secoes_seguintes():
    """'ATESTADO DE CAPACIDADE TECNICA' é PARTE (nível mais alto); o rótulo de
    seção que vem depois aninha sob ela, e o próximo rótulo de seção é irmão."""
    paginas = [
        {
            "numero": 2,
            "markdown": (
                "ATESTADO DE CAPACIDADE TECNICA\n"
                "Atestamos para os devidos fins que a empresa EXEMPLO LTDA\n"
                "ESCOPO DOS SERVIOS\n"
                "1.1 - Montagem de 888 m2 de divisórias sanitárias\n"
                "OBSERVAÇÕES:\n"
                "Serviço concluído no prazo."
            ),
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))

    assert _bloco_com(blocos, "Atestamos").caminho == ["ATESTADO DE CAPACIDADE TECNICA"]
    assert _bloco_com(blocos, "888 m2").caminho == [
        "ATESTADO DE CAPACIDADE TECNICA",
        "ESCOPO DOS SERVIOS",
    ]
    assert _bloco_com(blocos, "concluído").caminho == [
        "ATESTADO DE CAPACIDADE TECNICA",
        "OBSERVAÇÕES",
    ]


def test_rotulo_de_prosa_fica_sob_heading_real_e_acima_da_pseudo_secao_de_tabela():
    paginas = [
        {
            "numero": 5,
            "markdown": (
                "# ANEXO I\n"
                " DADOS DO CONTRATO \n"
                "Contrato: 123/2019\n"
                "| Descrição | UN. | QUANT. |\n"
                "|---|---|---|\n"
                "| GASES | | |\n"
                "| TUBO | M | 10,00 |\n"
                " DESCRIÇÃO \n"
                "Texto livre depois da tabela."
            ),
        }
    ]
    blocos = chunking.parsear_blocos(chunking.costurar(paginas))

    assert _bloco_com(blocos, "123/2019").caminho == ["ANEXO I", "DADOS DO CONTRATO"]
    assert _bloco_com(blocos, "TUBO").caminho == ["ANEXO I", "DADOS DO CONTRATO", "GASES"]
    # O rótulo de prosa seguinte derruba a pseudo-seção de tabela pendente.
    assert _bloco_com(blocos, "Texto livre").caminho == ["ANEXO I", "DESCRIÇÃO"]


@pytest.mark.parametrize(
    "linha",
    [
        # Conteúdo em caixa alta real dos documentos (nomes, cargos, cidades).
        "GERENTE INDUSTRIAL",
        "EMPRESA EXEMPLO - INDUSTRIAS QUIMICAS",
        "INSTITUTO EXEMPLO",
        "SÃO PAULO - SP",
        "RIO DE JANEIRO RJ",
        "INSTALACAO DE SISTEMA DE GERACAO DE VAPOR PURO SENDO:",
        # Título repetido em toda página da CAT do CAU.
        "CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO",
        # Legendas de assinatura (fora do vocabulário de propósito).
        "CONTRATANTE",
        "RESPONSÁVEL TÉCNICO",
        # Chave-valor na mesma linha não é rótulo.
        "DADOS DO CONTRATO: 123/2019",
        "ENDEREÇO: RUA EXEMPLO, 100",
        # Caixa baixa / título: fora do critério.
        "Dados do contrato",
        "Atividade Técnica Realizada",
        # Linha de tabela e heading markdown têm tratamento próprio.
        "| DADOS DO CONTRATO | | |",
        "## DADOS DO CONTRATO",
        # Longa demais (> 60 caracteres).
        "DADOS DO " + "X" * 60,
    ],
)
def test_linha_que_nao_e_rotulo_de_secao(linha):
    assert chunking._rotulo_secao_prosa(linha) is None


@pytest.mark.parametrize(
    ("linha", "titulo"),
    [
        (" DADOS DO PROFISSIONAL ", "DADOS DO PROFISSIONAL"),
        (
            " DADOS DOS REGISTROS DE RESPONSABILIDADE TÉCNICA-RRT ",
            "DADOS DOS REGISTROS DE RESPONSABILIDADE TÉCNICA-RRT",
        ),
        ("ENDEREÇO DA OBRA/SERVIÇO", "ENDEREÇO DA OBRA/SERVIÇO"),
        ("INFORMAÇÕES IMPORTANTES", "INFORMAÇÕES IMPORTANTES"),
        ("2. DADOS CONTRATUAIS:", "2. DADOS CONTRATUAIS"),
        ("**OBJETO DO CONTRATO**", "OBJETO DO CONTRATO"),
        ("ESCOPO DOS SERVIOS", "ESCOPO DOS SERVIOS"),
    ],
)
def test_rotulo_de_secao_reconhecido(linha, titulo):
    resultado = chunking._rotulo_secao_prosa(linha)
    assert resultado == (chunking.NIVEL_ROTULO_SECAO, titulo)
