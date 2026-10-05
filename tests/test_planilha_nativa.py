"""
Testes da terceira via do roteamento e da classificação de lacunas.

Os dois assuntos vivem no mesmo arquivo porque nasceram do mesmo achado: o
acervo real de 33 CATs tem 628 páginas nativas, 460 delas planilha, e NENHUMA
produzia uma linha em `itens_planilha`. A rota nativa lia o texto do PDF, a
grade da tabela sumia, e a ligação entre código, descrição, quantidade e
unidade — que é o dado — se perdia sem erro nenhum.

Tudo aqui roda offline: nenhuma chamada de API, nenhum PDF real.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from solufarma import config
from solufarma.chunking import (
    classificar_lacuna,
    codigos_citados,
    extrair_linhas_tabela,
    sinais_da_observacao,
)
from solufarma.extracao import parece_planilha
from solufarma.formatos import inferir_cabecalho, tabela_para_markdown
from solufarma.modelos import Bloco

# Texto nativo como o PyMuPDF devolve uma planilha: cada célula numa linha, a
# quantidade a sete linhas de distância do código a que pertence.
# Reproduz a proporção de uma página real: ~30 linhas, unidades isoladas e
# muitas linhas curtíssimas (as colunas estreitas achatadas).
PLANILHA_ACHATADA = """6.3.1
FORNECIMENTO E MONTAGEM DE ESCADA EXECUTADA TOTALMENTE COM AÇO ASTM A 572
E CHAPA XADREZ, SAPATAS DE FIXAÇÃO EM CHAPA DE AÇO.
2.169,20
kg
6.3.2
ESCADA EXISTENTE - PROLONGAMENTO DO PATAMAR EM AÇO ASTM A 572
475,20
kg
7
INSTALAÇÕES HIDRAULICA
7.1
AGUA FRIA
7.1.1
TUBO DE PVC SOLDÁVEL
152,00
m
7.1.2
CONEXÕES PARA O ITEM SUPERIOR
1,00
vb
7.1.3
REGISTRO DE GAVETA BRUTO
10,00
un
7.1.4
VÁLVULA DE RETENÇÃO HORIZONTAL
4,00
un
"""

PROSA = """ATESTADO DE EXECUÇÃO DE OBRA

Atestamos a quem possa interessar que a empresa executou a obra cujas
principais características descrevemos a seguir, dentro de elevado padrão
técnico, atendendo plenamente as disposições contratuais estabelecidas no
contrato firmado entre as partes em fevereiro de 2013.
"""


class TestDeteccaoDePlanilha:
    def test_planilha_achatada_e_detectada(self):
        assert parece_planilha(PLANILHA_ACHATADA) is True

    def test_prosa_nao_e_confundida_com_planilha(self):
        assert parece_planilha(PROSA) is False

    def test_texto_vazio_nao_quebra(self):
        assert parece_planilha("") is False

    def test_unidades_soltas_bastam(self):
        """Três unidades isoladas já denunciam a planilha, mesmo com poucas linhas."""
        assert parece_planilha("item a\nvb\nitem b\nkg\nitem c\nm²\n") is True


class TestInferenciaDeCabecalho:
    def test_reconhece_item_descricao_quantidade_unidade(self):
        linhas = [
            ["6.3.1", "FORNECIMENTO E MONTAGEM DE ESCADA METÁLICA COMPLETA", "2.169,20", "kg"],
            ["6.3.2", "ESCADA EXISTENTE - PROLONGAMENTO DO PATAMAR EM AÇO", "475,20", "kg"],
            ["6.3.3", "GUARDA CORPO EM AÇO GALVANIZADO COM PINTURA EPÓXI", "12,00", "kg"],
        ]
        nomes, inferiu = inferir_cabecalho(linhas)
        assert nomes == ["Item", "Descrição", "Quantidade", "Unidade"]
        assert inferiu is True

    def test_nao_chuta_quantidade_com_duas_colunas_numericas(self):
        """
        Com quantidade, valor unitário e total, qualquer rótulo é chute — e um
        chute aqui vira número com nome errado no banco e no embedding.
        """
        linhas = [
            ["1.1", "CONCRETO USINADO FCK 25 MPA BOMBEADO NA OBRA", "10,00", "450,00"],
            ["1.2", "AÇO CA-50 CORTADO E DOBRADO CONFORME PROJETO", "25,00", "780,00"],
        ]
        nomes, _ = inferir_cabecalho(linhas)
        assert nomes[2].startswith("Coluna")
        assert nomes[3].startswith("Coluna")

    def test_tabela_vazia_devolve_vazio(self):
        assert inferir_cabecalho([]) == ([], False)


class TestTabelaParaMarkdown:
    def test_emite_cabecalho_e_separador(self):
        md = tabela_para_markdown([["1.1", "ITEM A MUITO BEM DESCRITO AQUI NESTA LINHA", "2", "vb"]])
        linhas = md.splitlines()
        assert linhas[0].startswith("| Item |")
        assert set(linhas[1]) <= set("|-")

    def test_nenhuma_linha_de_dados_e_perdida(self):
        """
        O `find_tables()` devolve a PRIMEIRA LINHA DE DADOS como se fosse
        cabeçalho em página de continuação. Se ela virasse a linha de cabeçalho
        do markdown, `extrair_linhas_tabela` a descartaria — o mesmo modo de
        falha do bug de 07/08, ao contrário. O cabeçalho tem que ser NOSSO.
        """
        dados = [
            ["6.3.1", "ESCADA METÁLICA COMPLETA COM GUARDA CORPO E PINTURA", "2.169,20", "kg"],
            ["6.3.2", "PROLONGAMENTO DO PATAMAR EXISTENTE EM AÇO ASTM A 572", "475,20", "kg"],
        ]
        md = tabela_para_markdown(dados)
        blocos = [Bloco("tabela", md.splitlines(), ["Planilha"], 10, 10)]
        itens = extrair_linhas_tabela(blocos, "doc")
        assert len(itens) == 2
        assert [i["celulas"][0] for i in itens] == ["6.3.1", "6.3.2"]

    def test_pipe_no_conteudo_nao_quebra_a_tabela(self):
        r"""O pipe do conteúdo vira `\|` e não conta como separador."""
        md = tabela_para_markdown([["1", "TUBO 3/4 | 1/2 POLEGADA EM COBRE RÍGIDO", "5", "m"]])
        separadores = [ln.replace(r"\|", "").count("|") for ln in md.splitlines()]
        assert separadores == [5, 5, 5]


class TestCodigosCitados:
    def test_extrai_os_codigos_da_observacao_real(self):
        obs = (
            "Vários carimbos, rubricas e um selo circular sobrepõem parte da coluna "
            "DISCRIMINAÇÃO e das colunas UNIDADE/QUANTIDADE nas linhas 2.1, 2.5, 2.9, "
            "2.10, 2.12, 3.1, tornando alguns valores ilegíveis - foram deixados em "
            "branco por fidelidade."
        )
        assert codigos_citados(obs) == {"2.1", "2.5", "2.9", "2.10", "2.12", "3.1"}

    def test_numero_solto_nao_vira_codigo(self):
        """"linhas 2 e imediações" não identifica linha nenhuma."""
        assert codigos_citados("obstrução na linha 2 e imediações") == set()

    def test_observacao_vazia(self):
        assert codigos_citados("") == set()
        assert codigos_citados(None) == set()


class TestClassificacaoDeLacuna:
    CITADOS: ClassVar[set[str]] = {"2.1", "2.5"}

    def test_linha_completa_e_ok(self):
        celulas = ["1.2", "SERVIÇOS DE TOPOGRAFIA", "MES", "1,00"]
        assert classificar_lacuna(celulas, 0.55, self.CITADOS) == "ok"

    def test_linha_citada_pelo_modelo_e_ilegivel(self):
        celulas = ["2.1", "INSTALACAO DE CANTEIRO DE OBRA", "", ""]
        assert classificar_lacuna(celulas, 0.55, self.CITADOS) == "ilegivel"

    def test_cabecalho_de_secao_e_vazio_legitimo(self):
        """
        Estruturalmente idêntico à linha ilegível acima — o que separa as duas é
        só a enumeração do modelo. Sem ela, as duas seriam indistinguíveis.
        """
        celulas = ["1", "SERVIÇOS TECNICOS", "", ""]
        assert classificar_lacuna(celulas, 0.55, self.CITADOS) == "vazio"

    def test_pagina_ruim_sem_enumeracao_vira_suspeita(self):
        celulas = ["4.2", "ALVENARIA DE BLOCO", "", ""]
        assert classificar_lacuna(celulas, 0.50, set()) == "suspeita"

    def test_pagina_confiavel_com_celula_vazia_e_vazio(self):
        celulas = ["4.2", "ALVENARIA DE BLOCO", "", ""]
        assert classificar_lacuna(celulas, 1.0, set()) == "vazio"

    @pytest.mark.parametrize("confianca", [0.0, 0.74, 0.749])
    def test_limiar_de_revisao_e_respeitado(self, confianca):
        assert confianca < config.LIMIAR_CONFIANCA_REVISAO
        assert classificar_lacuna(["9.9", "X", "", ""], confianca, set()) == "suspeita"


class TestExtracaoComQualidade:
    """A confiança da página precisa chegar até a linha da planilha."""

    BLOCO = Bloco(
        "tabela",
        [
            "| Item | Descrição | Unidade | Quantidade |",
            "|---|---|---|---|",
            "| 1 | SERVIÇOS TECNICOS |  |  |",
            "| 2.1 | INSTALACAO DE CANTEIRO DE OBRA |  |  |",
            "| 2.2 | ABRIGO PROVISORIO | M2 | 50,82 |",
        ],
        ["Planilha"],
        5,
        5,
    )

    PAGINAS: ClassVar[list[dict]] = [
        {
            "numero": 5,
            "confianca": 0.55,
            "observacoes": "carimbos sobre as linhas 2.1, 2.5 — deixados em branco",
        }
    ]

    def test_status_por_linha(self):
        itens = extrair_linhas_tabela([self.BLOCO], "doc", self.PAGINAS)
        assert [i["status"] for i in itens] == ["vazio", "ilegivel", "ok"]

    def test_confianca_acompanha_a_linha(self):
        itens = extrair_linhas_tabela([self.BLOCO], "doc", self.PAGINAS)
        assert all(i["confianca"] == 0.55 for i in itens)

    def test_observacao_so_na_linha_problematica(self):
        itens = extrair_linhas_tabela([self.BLOCO], "doc", self.PAGINAS)
        assert "observacoes" in itens[1]
        assert "observacoes" not in itens[2]

    def test_sem_paginas_mantem_o_comportamento_antigo(self):
        """Chamada legada não pode quebrar nem inventar confiança baixa."""
        itens = extrair_linhas_tabela([self.BLOCO], "doc")
        assert all(i["confianca"] == 1.0 for i in itens)
        assert [i["status"] for i in itens] == ["vazio", "vazio", "ok"]


class TestPaginaPorLinha:
    """
    Rastreabilidade por página é o contrato central do projeto: toda citação
    resolve chunk -> documento -> página. Uma planilha que atravessa 128 páginas
    vira UM bloco, e antes desta correção cada linha herdava a página de início:
    2.622 itens diziam "página 15" e todo chunk de tabela dizia "páginas 15-143".
    """

    @staticmethod
    def _bloco_de_tres_paginas() -> Bloco:
        linhas = [
            "| Item | Descrição | Unidade | Quantidade |",
            "|---|---|---|---|",
            "| 1.1 | CONCRETO USINADO FCK 25 MPA | m3 | 10,00 |",
            "| 1.2 | AÇO CA-50 CORTADO E DOBRADO | kg | 25,00 |",
            "| 2.1 | ALVENARIA DE BLOCO CERÂMICO | m2 | 80,00 |",
        ]
        paginas = [40, 40, 40, 41, 42]
        return Bloco("tabela", linhas, ["Planilha"], 40, 42, paginas)

    def test_cada_item_leva_a_sua_pagina(self):
        itens = extrair_linhas_tabela([self._bloco_de_tres_paginas()], "doc")
        assert [i["pagina"] for i in itens] == [40, 41, 42]

    def test_sem_paginas_por_linha_cai_para_a_do_bloco(self):
        """Bloco construído do jeito antigo não pode quebrar."""
        bloco = self._bloco_de_tres_paginas()
        bloco.paginas_linhas = []
        itens = extrair_linhas_tabela([bloco], "doc")
        assert {i["pagina"] for i in itens} == {40}

    def test_confianca_e_lida_da_pagina_certa(self):
        """
        A página 41 é a ruim. Se a linha herdasse a página do bloco, ela leria a
        confiança da 40 e a lacuna passaria despercebida.

        O status é "suspeita" e não "ilegivel" de propósito: a observação relata
        um carimbo sobre a linha, mas não afirma que o valor ficou ilegível.
        Prometer que existe um número a recuperar quando o modelo não disse isso
        seria inventar certeza que ninguém tem.
        """
        paginas = [
            {"numero": 40, "confianca": 1.0, "observacoes": ""},
            {"numero": 41, "confianca": 0.5, "observacoes": "carimbo sobre a linha 1.2"},
            {"numero": 42, "confianca": 1.0, "observacoes": ""},
        ]
        bloco = self._bloco_de_tres_paginas()
        bloco.linhas[3] = "| 1.2 | AÇO CA-50 CORTADO E DOBRADO |  |  |"
        itens = extrair_linhas_tabela([bloco], "doc", paginas)
        assert itens[1]["pagina"] == 41
        assert itens[1]["status"] == "suspeita"


class TestIntencaoDaObservacao:
    """
    O modelo diz POR QUE a célula está vazia, e o motivo muda o que fazer. Estas
    são as observações reais do CAT SJC-003369 — não fixtures inventadas.
    """

    def test_ilegivel_quando_declara_perda(self):
        obs = (
            "Vários carimbos, rubricas e um selo circular sobrepõem parte da coluna "
            "DISCRIMINAÇÃO e das colunas UNIDADE/QUANTIDADE nas linhas 2 e imediações "
            "(2.1, 2.5, 2.9), tornando alguns valores ilegíveis - foram deixados em "
            "branco por fidelidade."
        )
        assert sinais_da_observacao(obs) == {
            "2.1": "ilegivel",
            "2.5": "ilegivel",
            "2.9": "ilegivel",
        }

    def test_vazio_quando_declara_ausencia_no_original(self):
        """
        O caso que uma busca crua por código erraria: aqui o modelo AFIRMA que não
        há valor nenhum. Marcar como ilegível mandaria alguém procurar no papel um
        número que não existe — cinco vezes, só nesta página.
        """
        obs = (
            "Algumas células de UNIDADE/QUANTIDADE ficaram vazias no original para "
            "linhas que são apenas títulos de subgrupo (ex: 6.1, 6.3, 6.5)."
        )
        assert set(sinais_da_observacao(obs).values()) == {"vazio"}

    def test_suspeita_quando_ha_carimbo_mas_o_modelo_diz_que_leu(self):
        obs = (
            "Página contém carimbos de registro profissional (CREA) sobrepostos à "
            "tabela nas linhas 7.12 a 9.2, dificultando parcialmente a leitura de "
            "algumas células, mas o conteúdo textual foi identificado."
        )
        assert sinais_da_observacao(obs) == {"7.12": "suspeita", "9.2": "suspeita"}

    def test_o_diagnostico_mais_grave_vence(self):
        """Duas frases sobre o mesmo item: ilegível não é apagado por suspeita."""
        obs = "O item 4.5 ficou ilegível. Há carimbo próximo ao item 4.5 também."
        assert sinais_da_observacao(obs) == {"4.5": "ilegivel"}

    def test_frase_sem_codigo_nao_marca_nada(self):
        assert sinais_da_observacao("Rubrica manuscrita e selos foram ignorados.") == {}

    def test_codigo_nao_e_partido_pelo_separador_de_frases(self):
        """O ponto de "2.10" não pode ser lido como fim de frase."""
        obs = "Carimbo deixou em branco o item 2.10 da planilha."
        assert sinais_da_observacao(obs) == {"2.10": "ilegivel"}
