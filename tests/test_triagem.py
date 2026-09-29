"""
Regex da triagem por conteúdo (`solufarma.triagem`) com textos SINTÉTICOS.

Cada texto imita um dos layouts reais vistos no lote do Drive (28-29/09):
CREA-SP novo (com pontilhado de formulário e OCR antigo), CAU (SICCAU),
CREA-RJ antigo, CREA-SP antigo (rótulos numa coluna e valores em outra) e
atestado corrido. Nenhum depende de PDF em disco.
"""

from __future__ import annotations

from solufarma import triagem
from solufarma.triagem import ALTA, MEDIA, NAO

CREA_SP_NOVO = """\
Pagina 1/1
CAT COM REGISTRO DE ATESTADO
Resolução No. 1.025, de 30 de outubro de 2009
262O1 30007911
Profissional: ILDEMAR COPPIO ................................................................
Registro: 601349247-SP ............. RNP: 2605082830 ...............
Empresa Contratada: TEP TECNOLOGIA EM ENGENHARIA LTDA ......... ..........................
Contratante: CENTRO NACIONAL DE PESQLJISAS EM ENERGIA E MATERIAlS - CNPEM .......CNPJ: 01.576.817/0001-75...
Endereço ca Obra/serviço:RUA GIUSEPPE MAXIMO SCOLFARO .......................No.: 10000..
Complemento: POLO II ......... Bairro: CIDADE UNIVERSITARIA ........
Cidade: Carnpinas ...........................uF SP CEP: 13083100. PAlS: BRASIL .........
Data de inlcio: 15108/2012 Conclusão Efeilva: 27/01/2013 ....... ...Coordenadas
Atividade Técnica: 1) Execução, Instalaçoes, lnstalaçSo ElAtrica. 1541,70 metro quadrado ....
lnformaçães Complementares
Certidão de Acervo Tecnico No.2620130007911
"""

CAU = """\
Conselho de Arquitetura e Urbanismo
CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO
Nº 0000000522936
Profissional: ILZA MARIA COPPIO SATTELMAYER
Título do Profissional: Arquiteto e Urbanista
Descricao: Construção do Centro de Manipulação Farmacêutica da Aeronáutica (CEMFAR), incluindo \
demolições e remoções diversas
Empresa contratada: SOLUFARMA DO BRASIL ENGENHARIA LTDA - ME
CNPJ: 07.746.677/0001-12
 DADOS DO CONTRATO
Contratante: LABORATÓRIO QUÍMICO-FARMACÊUTICO DA AERONÁUTICA
CPF/CNPJ: 00394429009914
Cidade: RIO DE JANEIRO
Bairro: GALEÃO
UF: RJ
Data de Início: 22/01/2018
Data de término da atividade: 2019-05-20
 ATIVIDADE TÉCNICA REALIZADA
 2.1.1 - Execução de obra , 642.42 m² - metro quadrado
 ENDEREÇO DA OBRA/SERVIÇO
ESTRADA DO GALEÃO
"""

CREA_RJ_ANTIGO = """\
CERPIDAO DE AC2RVO TECNICO
CERTIDAO No. 758012010
MARCIO FLAVIO COPPIO ............................................................
EXECUTANTE.: TEP - TECNOLOGIA EN PROJETOS DE ENG LTDA ......Reg.: 2)05201155 .....
Contratante: FIOCRUZ-FUNDACAO OSWALDO CRUZ ......................................
InforinacaoComplementar ........................................................
ExECuçAo DE CABINE DE CRIOGENIA [CRIOPRESERVACAO] DE CONCENTRADO VIRAL COM
NITROGENIO LIQUIDO A -160 0C
No. Contrato: 124/20009 ...........
Endereco da Obra: AVENIDA BRASIL 4365 SL 65A ....................................
"""

# CREA-SP antigo: rótulos numa coluna, valores depois (o texto sai "descolado").
CREA_SP_ANTIGO_COLUNAS = """\
CERTIDAO DE ACERVO -CAT
CERTIDAO N°:
Profissional
MARC!O FLAVIO COPPIO
Local dix obra/serviço Rua Adherbal Stresser, 84 - Jd. Arpoador.
Cidade
Valor
Periodo
Contratante
Contratada
CREASP No
R$ 198.550,00 Uunho/2007).
04/06/2007 a 22/11/2007.
Ariston - !ndOstrias Qulmicas e Farmacêuticas Ltda.
Tep Teonoloqia em Projetos de Engenharia Ltda.
ATESTADO DE CAPACIDADE TECNICA
Atestamos Para os devidos fins e efeitos, que a empresa TEP - Tecnologia em Projetos de
Engenharia LTDA., corn sede no rnunicIpio de São José dos Campos, inscrita no CNPJ sob o
n 2. 02.905.709/0001-61
ARISTON - INDUSTRIAS QUIMICAS E FARMACEUTICAS LTDA
"""

ATESTADO_CONSORCIO = """\
ATESTADO DE CAPACIDADE TÉCNICA
Atestamos a quem possa Interessar que o Consórcio CTM, sediado em São José dos Campos - SP
composto pela TEP TECNOLOGIA EM ENGENHARIA LTDA com participação de 35%, através dos \
responsáveis técnicos abaixo relacionados:
Engenheiro Industrial-Mecânico: Márcio Flávio Copplo
Contrato nº20/2017 assinado com FUNDAÇÃO OSWALDO CRUZ, através da unidade FARMANGUINHOS.
A contratada executou no período de 17/04/2017 a 17/06/2018, pelo valor de R$ 23.732.320,06 \
os serviços de projeto executivo para as obras de adequações físicas do Prédio 70
"""


def _md(texto: str) -> triagem.Metadados:
    return triagem.extrair_metadados([texto])


# --- normalização ------------------------------------------------------------


def test_dobrar_preserva_comprimento_e_tira_acento():
    s = "Certidão Técnica — Nº ç"
    d = triagem.dobrar(s)
    assert len(d) == len(s)
    assert d.startswith("CERTIDAO TECNICA")


def test_limpar_texto_remove_nul():
    assert triagem.limpar_texto("a\x00b\x07c") == "abc"


def test_formatar_cnpj_tolera_barra_lida_como_1():
    assert triagem.formatar_cnpj("45.186.05310001-87") == "45.186.053/0001-87"
    assert triagem.formatar_cnpj("33173097000193") == "33.173.097/0001-93"
    assert triagem.formatar_cnpj("123") is None


# --- CREA-SP novo -----------------------------------------------------------------


def test_crea_sp_novo_campos_estruturados():
    md = _md(CREA_SP_NOVO)
    assert md.tipo.valor == "CAT"
    assert (md.numero_cat.valor, md.numero_cat.confianca) == ("2620130007911", ALTA)
    assert md.orgao.valor == "CNPEM" and md.orgao.confianca == ALTA
    assert md.contratante_cnpj.valor == "01.576.817/0001-75"
    assert md.executante_grupo.valor == "TEP" and md.executante_grupo.confianca == ALTA
    assert md.responsavel_tecnico.valor == "Ildemar Coppio"
    assert md.periodo.valor == "15/08/2012 a 27/01/2013"
    assert "Carnpinas/SP" in md.local.valor
    assert "1541,70" in md.objeto.valor


def test_crea_sp_novo_numero_so_no_cabecalho_com_ocr_trocando_zero():
    texto = CREA_SP_NOVO.replace("Certidão de Acervo Tecnico No.2620130007911\n", "")
    md = _md(texto)
    assert md.numero_cat.valor == "2620130007911"
    assert md.numero_cat.confianca == MEDIA


# --- CAU -----------------------------------------------------------------------------


def test_cau_solufarma_executante_e_datas_iso():
    md = _md(CAU)
    assert md.numero_cat.valor == "522936"  # zeros à esquerda removidos
    assert md.orgao.valor == "LAQFA/CEMFAR"
    assert md.executante_grupo.valor == "Solufarma"
    assert md.executante_cnpj.valor == triagem.SOLUFARMA_CNPJ
    assert md.contratante_cnpj.valor == "00.394.429/0099-14"
    assert md.periodo.valor == "22/01/2018 a 20/05/2019"
    assert md.local.valor.endswith("RIO DE JANEIRO/RJ")
    assert md.objeto.valor.startswith("Construção do Centro de Manipulação")
    assert md.responsavel_tecnico.valor == "Ilza Maria Coppio Sattelmayer"


def test_carimbo_cau_numero_com_ano():
    md = _md("Certidão nº 576640/2020 - 01/09/2020, 18:04 - Chave de Impressão")
    assert md.numero_cat.valor == "576640/2020"


# --- CREA-RJ antigo ------------------------------------------------------------------


def test_crea_rj_antigo_fiocruz_criogenia():
    md = _md(CREA_RJ_ANTIGO)
    assert md.numero_cat.valor == "758012010"
    assert md.orgao.valor == "FIOCRUZ"
    assert md.executante_grupo.valor == "TEP"
    assert "CABINE DE CRIOGENIA" in md.objeto.valor


def test_crea_rj_numero_com_ocr_lendo_n_como_m():
    md = _md("CERTIDAO DE ACERVO TECNICO\nCERTIDAO Mo. 4305/2010\n")
    assert md.numero_cat.valor == "4305/2010"


# --- CREA-SP antigo (colunas) ---------------------------------------------------------


def test_crea_sp_antigo_nao_confunde_rotulo_com_valor():
    md = _md(CREA_SP_ANTIGO_COLUNAS)
    assert md.tipo.valor == "CAT com atestado"
    assert md.numero_cat.confianca == NAO  # "CERTIDAO N°:" vazio no original
    # "Contratante" é seguido do rótulo "Contratada": não pode virar valor.
    assert md.contratante.valor is None
    assert md.orgao.valor == "Ariston" and md.orgao.confianca == MEDIA
    assert md.executante_grupo.valor == "TEP"
    assert md.periodo.valor == "04/06/2007 a 22/11/2007"
    assert md.responsavel_tecnico.valor == "Marcio Flavio Coppio"
    assert "Valor" not in (md.local.valor or "")


# --- atestado ---------------------------------------------------------------------------


def test_atestado_consorcio_com_tep():
    md = _md(ATESTADO_CONSORCIO)
    assert md.tipo.valor == "atestado de capacidade técnica"
    assert md.executante.valor.startswith("Consórcio CTM")
    assert md.executante_grupo.valor == "consórcio com TEP"
    assert md.orgao.valor == "FIOCRUZ"
    assert md.responsavel_tecnico.valor == "Márcio Flávio Copplo"
    assert md.periodo.valor == "17/04/2017 a 17/06/2018"
    assert md.objeto.valor.startswith("os serviços de projeto executivo")


def test_classificar_executante():
    assert triagem.classificar_executante("SOLUFARMA DO BRASIL ENGENHARIA LTDA") == "Solufarma"
    assert triagem.classificar_executante("Tep - Tecnologia em Projetos de Engenharia") == "TEP"
    assert triagem.classificar_executante("MPD Engenharia Ltda") is None


def test_texto_vazio_nao_quebra():
    md = _md("")
    assert md.tipo.valor == "outro"
    assert md.titulo_sugerido.valor is None


# --- título sugerido ----------------------------------------------------------------------


def test_titulo_sugerido_vem_do_conteudo():
    md = _md(CREA_SP_NOVO)
    titulo = md.titulo_sugerido.valor
    assert titulo.startswith("CAT 2620130007911 — CNPEM — ")
    assert titulo.endswith("(executante: TEP)")


# --- nome do arquivo x conteúdo --------------------------------------------------------------


def test_analisar_nome():
    r = triagem.analisar_nome("BUTANTAN CAT SJC-02542 Implantação planta industrial Rev00.pdf")
    assert r == {"orgaos": ["Instituto Butantan"], "numero_cat": "SJC-02542"}
    r = triagem.analisar_nome("FIOCRUZ CAT 7580-2010 Cabine de criogenia Rev00.pdf")
    assert r["numero_cat"] == "7580-2010"


def test_numeros_batem():
    assert triagem.numeros_batem("SJC-02085", "SJC-02085")
    assert not triagem.numeros_batem("SJC-02542", "SJC-02085")
    assert triagem.numeros_batem("0000000238897", "238897")
    assert triagem.numeros_batem("4305-2010", "4305/2010")
    assert triagem.numeros_batem("576640", "576640/2020")
    assert triagem.numeros_batem("7580-2010", "758012010")
    assert not triagem.numeros_batem("52669-2020", "758012010")
    assert not triagem.numeros_batem("ABC-01916", "2620140004961")


def test_confrontar_nome_detecta_troca():
    # Caso real de 28/09: arquivo "CNPEM ..." com conteúdo do Butantan.
    md = _md(
        CREA_SP_ANTIGO_COLUNAS.replace("Ariston", "Instituto Butantan").replace(
            "ARISTON", "INSTITUTO BUTANTAN"
        )
    )
    r = triagem.confrontar_nome("CNPEM CAT 2620130007911 Construção prédio Imas II.pdf", md)
    assert r["veredito"] == "trocado"


def test_confrontar_nome_bate():
    md = _md(CREA_SP_NOVO)
    r = triagem.confrontar_nome("CNPEM CAT 2620130007911 Construção prédio Imas II.pdf", md)
    assert r["veredito"] == "bate"
    assert len(r["motivos"]) == 2


def test_confrontar_nome_inconclusivo_sem_nada_comparavel():
    md = _md(ATESTADO_CONSORCIO)
    r = triagem.confrontar_nome("ATESTADO_DE_CAPACIDADE_TECNICA_VESTIARIO.pdf", md)
    assert r["veredito"] == "inconclusivo"


def test_fiotec_e_fiocruz_sao_compativeis():
    md = _md(CREA_RJ_ANTIGO.replace("758012010", "52669/2020"))
    r = triagem.confrontar_nome("FIOTEC CIPBR CAT 52669-2020 Planta.pdf", md)
    assert r["veredito"] == "bate"
