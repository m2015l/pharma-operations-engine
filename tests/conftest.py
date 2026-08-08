"""
Fixtures dos quatro invariantes do CLAUDE.md.

São SINTÉTICAS por ora — o `SENAI_CETIQT_CAT_576640.pdf` ainda não está no
repositório. Cada uma reproduz numericamente a condição descrita no CLAUDE.md
(347 caracteres de carimbo em área A4, tabela sem cabeçalho na página seguinte,
etc.), mas nenhuma prova que o documento REAL se comporta como esperado.

Quando o PDF chegar, trocar por extratos reais e reconferir os números.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

# A4 renderizada com lado maior = 1500px (config.LADO_MAIOR_PX).
A4_ALTURA_PX = 1500
A4_LARGURA_PX = 1061  # 1500 / 1.414
AREA_A4_PX = A4_ALTURA_PX * A4_LARGURA_PX  # ~1,59M px²

# O carimbo do CAU embutido nas págs. 3-60: 347 caracteres idênticos.
# Passa em MIN_CARACTERES_UTEIS (220) e reprova em MIN_DENSIDADE — que é
# exatamente o ponto do invariante 2.
CARIMBO_CAU = (
    "Certidão nº 576640/2020 - 01/09/2020, 18:04 - Chave de Impressão: 3035566A189DW5W2DWBZ "
    "O atestado neste ato registrado foi emitido em 01/09/2020, e contém 60 folhas vinculado "
    "à Certidão De Acervo Técnico Com Atestado nº 576640, emitida em 01/09/2020 "
    "Este documento encontra-se registrado no Conselho de Arquitetura e Urbanismo do Brasil,"
)


@pytest.fixture
def zip_disfarcado(tmp_path: Path) -> Path:
    """
    INVARIANTE 1 — extensão mente.

    Arquivo com sufixo `.pdf` cujos bytes são um ZIP com 3 JPEGs, igual ao
    documento do SENAI. Nomes fora de ordem alfabética (2, 10, 1) para o teste
    também cobrir a ordenação numérica.
    """
    destino = tmp_path / "documento.pdf"
    with zipfile.ZipFile(destino, "w") as z:
        for numero in (2, 10, 1):
            buf = io.BytesIO()
            Image.new("RGB", (400, 560), "white").save(buf, format="JPEG")
            z.writestr(f"pagina_{numero}.jpg", buf.getvalue())
    return destino


@pytest.fixture
def pdf_verdadeiro(tmp_path: Path) -> Path:
    """Controle: um `.pdf` que é de fato um PDF."""
    destino = tmp_path / "real.pdf"
    destino.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    return destino


@pytest.fixture
def paginas_marca_dagua() -> list[str]:
    """
    INVARIANTE 2 — texto nativo pode ser só marca d'água.

    60 páginas: as duas primeiras com texto real (o PDF nativo do SICCAU), as
    58 seguintes só com o carimbo. É o formato exato do CAT do SENAI.
    """
    reais = [
        "CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO\n" + ("conteúdo real da página. " * 120),
        "DADOS DO PROFISSIONAL\n" + ("conteúdo real da página. " * 120),
    ]
    return reais + [CARIMBO_CAU] * 58


@pytest.fixture
def tabela_dividida() -> list[dict]:
    """
    INVARIANTE 3 — página não é fronteira semântica.

    Tabela começa na pág. 44 com cabeçalho e continua na 45 sem repeti-lo.
    O OCR marcou a continuação com `<!-- TABELA_CONTINUA -->` e reimprimiu o
    cabeçalho herdado — que a costura precisa descartar.
    """
    return [
        {
            "numero": 44,
            "markdown": (
                "| Descrição | Unidade | Quantidade |\n"
                "|---|---|---|\n"
                "| #2,5MM2 COR PRETO (FASE) | M | 19.541,00 |\n"
                "| #2,5MM2 COR AZUL CLARO (NEUTRO) | M | 16.250,00 |"
            ),
        },
        {
            "numero": 45,
            "markdown": (
                "<!-- TABELA_CONTINUA -->\n"
                "| Descrição | Unidade | Quantidade |\n"
                "|---|---|---|\n"
                "| #4MM2 COR PRETO (FASE) | M | 3.050,00 |\n"
                "| #240MM2 COR VERDE (TERRA) | M | 300,00 |"
            ),
        },
    ]


@pytest.fixture
def paragrafo_dividido() -> list[dict]:
    """INVARIANTE 3, outra face: parágrafo cortado pela paginação física."""
    return [
        {"numero": 8, "markdown": "As mantas vinílicas atendem às rígidas requisições de"},
        {
            "numero": 9,
            "markdown": "<!-- PARAGRAFO_CONTINUA -->\nresistência química e de abrasão.",
        },
    ]


@pytest.fixture
def prosa_hierarquica() -> list[dict]:
    """
    INVARIANTE 4 — a saída do OCR é Markdown estruturado.

    Hierarquia `A.` / `A.1` / `A.1.1` como aparece no memorial descritivo.
    O caminho de seção do chunk depende inteiramente destes headings.
    """
    return [
        {
            "numero": 8,
            "markdown": (
                "## A. Arquitetura\n"
                "Descrição geral do partido arquitetônico adotado na reforma.\n\n"
                "### A.1 acabamentos de pisos\n"
                "Em geral, o mais significativo neste caso é a especificação.\n\n"
                "#### A.1.1 vinílicos\n"
                "As mantas vinílicas atendem às rígidas requisições de resistência."
            ),
        }
    ]


@pytest.fixture
def documento_extraido(prosa_hierarquica, tabela_dividida) -> dict:
    """JSON de extração completo, no formato que o chunking consome."""
    return {
        "arquivo": "SENAI_CETIQT_CAT_576640.pdf",
        "hash_documento": "abc123def456",
        "n_paginas": 3,
        "formato_detectado": "zip_imagens",
        "paginas": prosa_hierarquica + tabela_dividida,
    }
