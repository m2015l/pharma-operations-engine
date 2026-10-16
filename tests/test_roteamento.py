"""
INVARIANTE 2 — texto nativo pode ser só marca d'água.

Este é o teste mais importante do M1. A falha que ele cobre é silenciosa:
sem a dupla condição, 58 páginas escaneadas passam por digitais, o OCR é
pulado e o documento final tem o mesmo carimbo repetido 58 vezes. Nenhuma
exceção é levantada em lugar nenhum.
"""

from __future__ import annotations

from pharma_ops import extracao
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
    assert any("100200" in linha for linha in boilerplate)


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
        (
            "Certidão nº 100200/2020 - 01/09/2020, 18:04 - "
            "Chave de Impressão: 0000000A000AA0A0AAA0"
        )
    }
    assinaturas = extracao.extrair_assinaturas(boilerplate)
    assert "0000000A000AA0A0AAA0" in assinaturas

    variantes = [
        "Chave de Impressão: 0000000A000AA0A0AAA0",
        (
            "A autenticidade desta Certidão pode ser verificada em: "
            "https://siccau.caubr.gov.br/app/view/sight/externo?form=Servicos, "
            "com a chave: 0000000A000AA0A0AAA0"
        ),
    ]
    for variante in variantes:
        assert extracao.limpar(variante, boilerplate, assinaturas) == ""


def test_assinatura_nao_engole_codigo_de_material():
    """
    O acervo é cheio de identificadores legítimos. Nenhum pode ser confundido
    com assinatura de carimbo — apagar uma linha de planilha seria pior que
    deixar o carimbo passar.
    """
    boilerplate = {"Certidão nº 100200 - Chave de Impressão: 0000000A000AA0A0AAA0"}
    assinaturas = extracao.extrair_assinaturas(boilerplate)

    linhas_reais = [
        "| #240MM2 COR VERDE (FASE) | M | 900,00 |",
        "| QDC-4P-PIL | CJ | 1,00 |",
        "| ESTRUTURA METALICA ASTM A-588 GRB | KG | 2.821,00 |",
        "Número do RRT: 1002001 Tipo do RRT: SIMPLES",
        "CNPJ: 11.222.333/0001-81",
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


# --------------------------------------------------------------------------
# OCR antigo embutido — texto que passa na dupla condição e não presta
# --------------------------------------------------------------------------
#
# A dupla condição mede quanto texto a página tem, não de onde ele veio. A
# camada de OCR que o scanner embute no PDF tem volume e densidade de texto
# digitado: passava por nativa e chegava ao acervo como "Carlos Eduardo Silva"
# (Indústria Odontológica) e "Roberto Almeida Santos" (pág. 2 do HUC).


def test_pagina_escaneada_com_ocr_embutido_vai_para_o_vlm():
    rotas = ["nativo", "nativo", "vlm", "nativo"]
    ajustadas, desviadas = extracao.desviar_ocr_embutido(rotas, escaneadas={1, 2})
    assert ajustadas == ["nativo", "vlm", "vlm", "nativo"]
    assert desviadas == 1


def test_pagina_digital_continua_nativa():
    """As 142 páginas do Complexo Farmacêutico Industrial Obra II não podem virar custo de OCR."""
    rotas = ["nativo"] * 5
    ajustadas, desviadas = extracao.desviar_ocr_embutido(rotas, escaneadas=set())
    assert ajustadas == rotas
    assert desviadas == 0


def _pdf_de_teste(tmp_path):
    """Pág. 1 digital; pág. 2 folha escaneada com OCR embutido; pág. 3 digital com logotipo."""
    import pymupdf

    figura = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80), False)
    figura.clear_with(200)
    doc = pymupdf.open()

    digital = doc.new_page()
    digital.insert_text((72, 100), "Certidão de Acervo Técnico digitada")

    escaneada = doc.new_page()
    escaneada.insert_image(escaneada.rect, pixmap=figura)
    escaneada.insert_text((72, 100), "Atestarnos para os devldos fins", render_mode=3)

    com_logo = doc.new_page()
    com_logo.insert_image(pymupdf.Rect(40, 40, 160, 120), pixmap=figura)
    com_logo.insert_text((72, 200), "Página digital com logotipo no topo")

    caminho = tmp_path / "misto.pdf"
    doc.save(caminho)
    doc.close()
    return caminho


def test_detecta_so_a_folha_que_e_imagem_inteira(tmp_path):
    from pharma_ops import formatos

    assert formatos.paginas_escaneadas(_pdf_de_teste(tmp_path)) == {1}


def test_logotipo_nao_faz_a_pagina_contar_como_escaneada(tmp_path):
    from pharma_ops import formatos

    assert 2 not in formatos.paginas_escaneadas(_pdf_de_teste(tmp_path))
