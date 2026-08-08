"""
INVARIANTE 2 — texto nativo pode ser só marca d'água.

Este é o teste mais importante do M1. A falha que ele cobre é silenciosa:
sem a dupla condição, 58 páginas escaneadas passam por digitais, o OCR é
pulado e o documento final tem o mesmo carimbo repetido 58 vezes. Nenhuma
exceção é levantada em lugar nenhum.
"""

from __future__ import annotations

from solufarma import extracao
from tests.conftest import AREA_A4_PX, CARIMBO_CAU


def test_carimbo_do_cau_e_roteado_para_vlm():
    """
    O caso exato do CLAUDE.md: ~347 caracteres em folha A4.

    Passa em MIN_CARACTERES_UTEIS (220) — é por isso que `len(texto) > 50`
    falha — e reprova em MIN_DENSIDADE.
    """
    assert len(CARIMBO_CAU) > 220, "a fixture precisa passar na primeira condição"
    assert extracao.precisa_vlm(CARIMBO_CAU, AREA_A4_PX) is True


def test_pagina_com_texto_denso_de_verdade_e_nativa():
    texto = "conteúdo real da página do memorial descritivo. " * 60  # ~2.800 chars
    assert extracao.precisa_vlm(texto, AREA_A4_PX) is False


def test_pagina_quase_vazia_vai_para_vlm():
    assert extracao.precisa_vlm("Página 12", AREA_A4_PX) is True


def test_area_zero_nao_divide_por_zero():
    """Fallback: sem área conhecida, decide só pela contagem de caracteres."""
    texto = "x" * 500
    assert extracao.precisa_vlm(texto, 0) is False


def test_boilerplate_detecta_o_carimbo_repetido(paginas_marca_dagua):
    """
    O carimbo aparece em 58 de 60 páginas (96%) — acima do limiar de 55%.
    Precisa ser detectado ANTES do roteamento.
    """
    boilerplate = extracao.detectar_boilerplate(paginas_marca_dagua)
    assert boilerplate, "o carimbo repetido deveria ter sido detectado"
    assert any("576640" in linha for linha in boilerplate)


def test_boilerplate_nao_remove_conteudo_de_pagina_unica(paginas_marca_dagua):
    """Linha que aparece em 2 de 60 páginas não é boilerplate."""
    boilerplate = extracao.detectar_boilerplate(paginas_marca_dagua)
    assert not any("DADOS DO PROFISSIONAL" in linha for linha in boilerplate)


def test_pipeline_completo_de_roteamento(paginas_marca_dagua):
    """
    Ponta a ponta: limpar boilerplate -> rotear.

    Critério de aceite do M1: 2 páginas nativas, 58 via VLM.
    """
    boilerplate = extracao.detectar_boilerplate(paginas_marca_dagua)
    rotas = [
        "vlm" if extracao.precisa_vlm(extracao.limpar(t, boilerplate), AREA_A4_PX) else "nativo"
        for t in paginas_marca_dagua
    ]
    assert rotas.count("nativo") == 2
    assert rotas.count("vlm") == 58


def test_sem_remover_boilerplate_o_roteamento_erra(paginas_marca_dagua):
    """
    Prova de que a ordem importa.

    Com o carimbo AINDA no texto e usando só a contagem de caracteres — a
    heurística ingênua que o CLAUDE.md descreve — as 58 páginas escaneadas
    passariam por digitais.
    """
    ingenuo = [len(t) > 50 for t in paginas_marca_dagua]
    assert all(ingenuo), "a heurística ingênua classifica todas como digitais"


def test_assinatura_pega_variante_de_diagramacao_do_carimbo():
    """
    Regressão do M1 (2026-08-08): o CAU imprime a mesma chave em três formatos
    no mesmo documento. Só a versão das págs. 3-60 se repete o bastante para a
    detecção por repetição; as das págs. 1-2 aparecem 1 vez cada e sobreviviam.
    """
    boilerplate = {
        "Certidão nº 576640/2020 - 01/09/2020, 18:04 - "
        "Chave de Impressão: 3035566A189DW5W2DWBZ"
    }
    assinaturas = extracao.extrair_assinaturas(boilerplate)
    assert "3035566A189DW5W2DWBZ" in assinaturas

    variantes = [
        "Chave de Impressão: 3035566A189DW5W2DWBZ",
        "A autenticidade desta Certidão pode ser verificada em: "
        "https://siccau.caubr.gov.br/app/view/sight/externo?form=Servicos, "
        "com a chave: 3035566A189DW5W2DWBZ",
    ]
    for variante in variantes:
        assert extracao.limpar(variante, boilerplate, assinaturas) == ""


def test_assinatura_nao_engole_codigo_de_material():
    """
    O acervo é cheio de identificadores legítimos. Nenhum pode ser confundido
    com assinatura de carimbo — apagar uma linha de planilha seria pior que
    deixar o carimbo passar.
    """
    boilerplate = {"Certidão nº 576640 - Chave de Impressão: 3035566A189DW5W2DWBZ"}
    assinaturas = extracao.extrair_assinaturas(boilerplate)

    linhas_reais = [
        "| #240MM2 COR VERDE (FASE) | M | 900,00 |",
        "| QDC-4P-PIL | CJ | 1,00 |",
        "| ESTRUTURA METALICA ASTM A-588 GRB | KG | 2.821,00 |",
        "Número do RRT: 8014430 Tipo do RRT: SIMPLES",
        "CNPJ: 07.746.677/0001-12",
    ]
    for linha in linhas_reais:
        assert extracao.limpar(linha, boilerplate, assinaturas) == linha, (
            f"linha legítima foi removida: {linha}"
        )


def test_blocos_contiguos_preservam_a_ordem_do_carry_over():
    """
    INVARIANTE 3 — o carry-over exige ordem dentro do bloco.

    Páginas VLM contíguas formam um bloco só; um trecho nativo no meio parte
    o bloco em dois, que podem rodar em paralelo entre si.
    """
    rotas = ["nativo", "nativo", "vlm", "vlm", "vlm", "nativo", "vlm", "vlm"]
    blocos = extracao._montar_blocos(rotas)
    assert blocos == [[2, 3, 4], [6, 7]]


def test_documento_todo_escaneado_vira_um_bloco_unico():
    blocos = extracao._montar_blocos(["vlm"] * 58)
    assert len(blocos) == 1
    assert len(blocos[0]) == 58
