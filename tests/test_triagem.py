"""
Regex da triagem por conteúdo (`pharma_ops.triagem`) com textos SINTÉTICOS.

Cada texto imita um dos layouts reais vistos no lote do Drive (28-29/09):
CREA-SP novo (com pontilhado de formulário e OCR antigo), CAU (SICCAU),
CREA-RJ antigo, CREA-SP antigo (rótulos numa coluna e valores em outra) e
atestado corrido. Nenhum depende de PDF em disco.
"""

from __future__ import annotations

from pharma_ops import triagem
from pharma_ops.triagem import ALTA, MEDIA, NAO

CREA_SP_NOVO = """\
Pagina 1/1
CAT COM REGISTRO DE ATESTADO
Resolução No. 1.025, de 30 de outubro de 2009
262O2 40000101
Profissional: ROBERTO ALMEIDA SANTOS ................................................................
Registro: 000000002-SP ............. RNP: 2600000002 ...............
Empresa Contratada: ENTERPRISE VENDOR HUB ENGENHARIA LTDA ......... ..........................
Contratante: CENTRO NACIONAL DE BIOTECNOLOGIA - CNBIO .......CNPJ: 44.555.666/0001-14...
Endereço ca Obra/serviço:AVENIDA DA TECNOLOGIA, 1000
Complemento: POLO II ......... Bairro: CIDADE UNIVERSITARIA ........
Cidade: Carnpinas ...........................uF SP CEP: 01000000. PAlS: BRASIL .........
Data de inlcio: 15108/2012 Conclusão Efeilva: 27/01/2013 ....... ...Coordenadas
Atividade Técnica: 1) Execução, Instalaçoes, lnstalaçSo ElAtrica. 1541,70 metro quadrado ....
lnformaçães Complementares
Certidão de Acervo Tecnico No.2620240000101
"""

CAU = """\
Conselho de Arquitetura e Urbanismo
CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO
Nº 0000000100300
Profissional: ANA PAULA OLIVEIRA
Título do Profissional: Arquiteto e Urbanista
Descricao: Construção do Centro de Manipulação Farmacêutica Central (LQC), incluindo \
demolições e remoções diversas
Empresa contratada: PHARMA OPERATIONS ENGENHARIA LTDA
CNPJ: 11.222.333/0001-81
 DADOS DO CONTRATO
Contratante: LABORATORIO QUIMICO CENTRAL
CPF/CNPJ: 55666777000125
Cidade: RIO DE JANEIRO
Bairro: GALEÃO
UF: RJ
Data de Início: 22/01/2018
Data de término da atividade: 2019-05-20
 ATIVIDADE TÉCNICA REALIZADA
 2.1.1 - Execução de obra , 642.42 m² - metro quadrado
 ENDEREÇO DA OBRA/SERVIÇO
ESTRADA INDUSTRIAL, 300
"""

CREA_RJ_ANTIGO = """\
CERPIDAO DE AC2RVO TECNICO
CERTIDAO No. 100012024
CARLOS EDUARDO SILVA ............................................................
EXECUTANTE.: ENTERPRISE VENDOR HUB ENGENHARIA LTDA ......Reg.: 2)05201155 .....
Contratante: FNSP-FUNDACAO NACIONAL DE SAUDE PUBLICA ......................................
InforinacaoComplementar ........................................................
ExECuçAo DE CABINE DE CRIOGENIA [CRIOPRESERVACAO] DE CONCENTRADO VIRAL COM
NITROGENIO LIQUIDO A -160 0C
No. Contrato: 124/20009 ...........
Endereco da Obra: AVENIDA CENTRAL 1000
"""

# CREA-SP antigo: rótulos numa coluna, valores depois (o texto sai "descolado").
CREA_SP_ANTIGO_COLUNAS = """\
CERTIDAO DE ACERVO -CAT
CERTIDAO N°:
Profissional
CARLOS EDUARDO SILVA
Local dix obra/serviço Rua Exemplo, 10 - Centro
Cidade
Valor
Periodo
Contratante
Contratada
CREASP No
R$ 198.550,00 Uunho/2007).
04/06/2007 a 22/11/2007.
Laboratório Químico Central - !ndOstrias Qulmicas e Farmacêuticas Ltda.
Enterprise Vendor Hub Engenharia Ltda.
ATESTADO DE CAPACIDADE TECNICA
Atestamos Para os devidos fins e efeitos, que a empresa Enterprise Vendor Hub - Engenharia e
Projetos LTDA., corn sede no rnunicIpio de São José dos Campos, inscrita no CNPJ sob o
n 2. 22.333.444/0001-92
LABORATORIO QUIMICO CENTRAL - INDUSTRIAS QUIMICAS E FARMACEUTICAS LTDA
"""

ATESTADO_CONSORCIO = """\
ATESTADO DE CAPACIDADE TÉCNICA
Atestamos a quem possa Interessar que o Consórcio Gama, sediado em São José dos Campos - SP
composto pela ENTERPRISE VENDOR HUB ENGENHARIA LTDA com participação de 35%, através dos \
responsáveis técnicos abaixo relacionados:
Engenheiro Industrial-Mecânico: Carlos Eduardo Silva
Contrato nº20/2017 assinado com FUNDACAO NACIONAL DE SAUDE PUBLICA, através da unidade COMPLEXO FARMACEUTICO.
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
    assert triagem.formatar_cnpj("66.777.88810001-36") == "66.777.888/0001-36"
    assert triagem.formatar_cnpj("77888999000147") == "77.888.999/0001-47"
    assert triagem.formatar_cnpj("123") is None


# --- CREA-SP novo -----------------------------------------------------------------


def test_crea_sp_novo_campos_estruturados():
    md = _md(CREA_SP_NOVO)
    assert md.tipo.valor == "CAT"
    assert (md.numero_cat.valor, md.numero_cat.confianca) == ("2620240000101", ALTA)
    assert md.orgao.valor == "Centro Nacional de Biotecnologia" and md.orgao.confianca == ALTA
    assert md.contratante_cnpj.valor == "44.555.666/0001-14"
    assert md.executante_grupo.valor == "Enterprise Vendor Hub" and md.executante_grupo.confianca == ALTA
    assert md.responsavel_tecnico.valor == "Roberto Almeida Santos"
    assert md.periodo.valor == "15/08/2012 a 27/01/2013"
    assert "Carnpinas/SP" in md.local.valor
    assert "1541,70" in md.objeto.valor


def test_crea_sp_novo_numero_so_no_cabecalho_com_ocr_trocando_zero():
    texto = CREA_SP_NOVO.replace("Certidão de Acervo Tecnico No.2620240000101\n", "")
    md = _md(texto)
    assert md.numero_cat.valor == "2620240000101"
    assert md.numero_cat.confianca == MEDIA


# --- CAU -----------------------------------------------------------------------------


def test_cau_principal_executante_e_datas_iso():
    md = _md(CAU)
    assert md.numero_cat.valor == "100300"  # zeros à esquerda removidos
    assert md.orgao.valor == "Laboratório Químico Central"
    assert md.executante_grupo.valor == "Pharma Operations"
    assert md.executante_cnpj.valor == triagem.EMPRESA_PRINCIPAL_CNPJ
    assert md.contratante_cnpj.valor == "55.666.777/0001-25"
    assert md.periodo.valor == "22/01/2018 a 20/05/2019"
    assert md.local.valor.endswith("RIO DE JANEIRO/RJ")
    assert md.objeto.valor.startswith("Construção do Centro de Manipulação")
    assert md.responsavel_tecnico.valor == "Ana Paula Oliveira"


def test_carimbo_cau_numero_com_ano():
    md = _md("Certidão nº 100200/2020 - 01/09/2020, 18:04 - Chave de Impressão")
    assert md.numero_cat.valor == "100200/2020"


# --- CREA-RJ antigo ------------------------------------------------------------------


def test_crea_rj_antigo_fnsp_criogenia():
    md = _md(CREA_RJ_ANTIGO)
    assert md.numero_cat.valor == "100012024"
    assert md.orgao.valor == "Fundação Nacional de Saúde Pública"
    assert md.executante_grupo.valor == "Enterprise Vendor Hub"
    assert "CABINE DE CRIOGENIA" in md.objeto.valor


def test_crea_rj_numero_com_ocr_lendo_n_como_m():
    md = _md("CERTIDAO DE ACERVO TECNICO\nCERTIDAO Mo. 1305/2024\n")
    assert md.numero_cat.valor == "1305/2024"


# --- CREA-SP antigo (colunas) ---------------------------------------------------------


def test_crea_sp_antigo_nao_confunde_rotulo_com_valor():
    md = _md(CREA_SP_ANTIGO_COLUNAS)
    assert md.tipo.valor == "CAT com atestado"
    assert md.numero_cat.confianca == NAO  # "CERTIDAO N°:" vazio no original
    # "Contratante" é seguido do rótulo "Contratada": não pode virar valor.
    assert md.contratante.valor is None
    assert md.orgao.valor == "Laboratório Químico Central" and md.orgao.confianca == MEDIA
    assert md.executante_grupo.valor == "Enterprise Vendor Hub"
    assert md.periodo.valor == "04/06/2007 a 22/11/2007"
    assert md.responsavel_tecnico.valor == "Carlos Eduardo Silva"
    assert "Valor" not in (md.local.valor or "")


# --- atestado ---------------------------------------------------------------------------


def test_atestado_consorcio_com_coligada():
    md = _md(ATESTADO_CONSORCIO)
    assert md.tipo.valor == "atestado de capacidade técnica"
    assert md.executante.valor.startswith("Consórcio Gama")
    assert md.executante_grupo.valor == "consórcio com Enterprise Vendor Hub"
    assert md.orgao.valor == "Fundação Nacional de Saúde Pública"
    assert md.responsavel_tecnico.valor == "Carlos Eduardo Silva"
    assert md.periodo.valor == "17/04/2017 a 17/06/2018"
    assert md.objeto.valor.startswith("os serviços de projeto executivo")


def test_classificar_executante():
    assert triagem.classificar_executante("PHARMA OPERATIONS ENGENHARIA LTDA") == "Pharma Operations"
    assert triagem.classificar_executante("Enterprise Vendor Hub") == "Enterprise Vendor Hub"
    assert triagem.classificar_executante("MPD Engenharia Ltda") is None


def test_texto_vazio_nao_quebra():
    md = _md("")
    assert md.tipo.valor == "outro"
    assert md.titulo_sugerido.valor is None


# --- título sugerido ----------------------------------------------------------------------


def test_titulo_sugerido_vem_do_conteudo():
    md = _md(CREA_SP_NOVO)
    titulo = md.titulo_sugerido.valor
    assert titulo.startswith("CAT 2620240000101 — Centro Nacional de Biotecnologia — ")
    assert titulo.endswith("(executante: Enterprise Vendor Hub)")


# --- nome do arquivo x conteúdo --------------------------------------------------------------


def test_analisar_nome():
    r = triagem.analisar_nome("BIOPHARMA CAT SJC-02542 Implantação planta industrial Rev00.pdf")
    assert r == {"orgaos": ["Instituto BioPharma"], "numero_cat": "SJC-02542"}
    r = triagem.analisar_nome("FNSP CAT 1000-2024 Cabine de criogenia Rev00.pdf")
    assert r["numero_cat"] == "1000-2024"


def test_numeros_batem():
    assert triagem.numeros_batem("SJC-10002", "SJC-10002")
    assert not triagem.numeros_batem("SJC-02542", "SJC-10002")
    assert triagem.numeros_batem("0000000100302", "100302")
    assert triagem.numeros_batem("1305-2024", "1305/2024")
    assert triagem.numeros_batem("100200", "100200/2020")
    assert triagem.numeros_batem("1000-2024", "100012024")
    assert not triagem.numeros_batem("10669-2024", "100012024")
    assert not triagem.numeros_batem("ABC-01916", "2620240000103")


def test_confrontar_nome_detecta_troca():
    # Caso de troca: arquivo "CNBIO ..." com conteúdo do BioPharma.
    md = _md(
        CREA_SP_ANTIGO_COLUNAS.replace("Laboratório Químico Central", "Instituto BioPharma").replace(
            "LABORATORIO QUIMICO CENTRAL", "INSTITUTO BIOPHARMA"
        )
    )
    r = triagem.confrontar_nome("CNBIO CAT 2620240000101 Construção prédio Bloco B.pdf", md)
    assert r["veredito"] == "trocado"


def test_confrontar_nome_bate():
    md = _md(CREA_SP_NOVO)
    r = triagem.confrontar_nome("CNBIO CAT 2620240000101 Construção prédio Bloco B.pdf", md)
    assert r["veredito"] == "bate"
    assert len(r["motivos"]) == 2


def test_confrontar_nome_inconclusivo_sem_nada_comparavel():
    md = _md(ATESTADO_CONSORCIO)
    r = triagem.confrontar_nome("ATESTADO_DE_CAPACIDADE_TECNICA_VESTIARIO.pdf", md)
    assert r["veredito"] == "inconclusivo"


def test_faps_e_fnsp_sao_compativeis():
    md = _md(CREA_RJ_ANTIGO.replace("100012024", "10669/2024"))
    r = triagem.confrontar_nome("FAPS FNSP CAT 10669-2024 Planta.pdf", md)
    assert r["veredito"] == "bate"
