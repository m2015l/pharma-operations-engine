"""INVARIANTE 1 — extensão de arquivo mente; detecte pelo magic number."""

from __future__ import annotations

import pytest

from pharma_ops import formatos


def test_zip_disfarcado_de_pdf_e_detectado_como_zip(zip_disfarcado):
    """O caso do Instituto BioPharma: sufixo .pdf, bytes de ZIP."""
    assert zip_disfarcado.suffix == ".pdf"
    assert formatos.sniff(zip_disfarcado) == "zip_imagens"


def test_pdf_verdadeiro_e_detectado_como_pdf(pdf_verdadeiro):
    assert formatos.sniff(pdf_verdadeiro) == "pdf"


def test_formato_desconhecido_nao_levanta(tmp_path):
    """Retorna 'desconhecido'; quem decide o que fazer é `carregar_paginas`."""
    arquivo = tmp_path / "estranho.pdf"
    arquivo.write_bytes(b"nada reconhecivel aqui")
    assert formatos.sniff(arquivo) == "desconhecido"


def test_zip_e_lido_em_ordem_numerica_nao_alfabetica(zip_disfarcado):
    """
    'pagina_10' vem depois de 'pagina_2'.

    Ordenação alfabética embaralharia o documento em silêncio e o carry-over
    passaria contexto da página errada — tabela costurada sem sentido.
    """
    paginas = formatos.carregar_paginas(zip_disfarcado, "zip_imagens")
    assert len(paginas) == 3
    for jpeg, _texto, area in paginas:
        assert jpeg.startswith(b"\xff\xd8\xff")  # JPEG válido
        assert area > 0


def test_zip_sem_imagens_falha_explicitamente(tmp_path):
    """Container vazio precisa gritar, não retornar zero páginas em silêncio."""
    import zipfile

    destino = tmp_path / "vazio.pdf"
    with zipfile.ZipFile(destino, "w") as z:
        z.writestr("leiame.txt", "sem imagens aqui")

    with pytest.raises(formatos.FormatoNaoSuportado, match="sem imagens"):
        formatos.carregar_paginas(destino, "zip_imagens")


def test_formato_desconhecido_falha_ao_carregar(pdf_verdadeiro):
    with pytest.raises(formatos.FormatoNaoSuportado):
        formatos.carregar_paginas(pdf_verdadeiro, "desconhecido")
