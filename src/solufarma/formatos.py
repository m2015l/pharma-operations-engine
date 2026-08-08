"""
formatos.py — Descoberta do formato real e renderização das páginas.

INVARIANTE 1 do CLAUDE.md: extensão de arquivo mente. O `.pdf` do SENAI é,
nos bytes, um ZIP com 60 JPEGs. Confiar no sufixo faz o PyMuPDF levantar
exceção — ou pior, num container diferente, retornar zero páginas em silêncio.

Saída de `carregar_paginas`: [(jpeg_bytes, texto_nativo, area_px), ...] em
ordem de página. `area_px` é o denominador do teste de densidade do roteamento.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image

from solufarma import config

# Magic numbers. Ordem importa: alguns formatos compartilham prefixo curto.
ASSINATURAS: list[tuple[bytes, str]] = [
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip_imagens"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
]

EXTENSOES_IMAGEM = (".jpeg", ".jpg", ".png")


class FormatoNaoSuportado(ValueError):
    pass


def sniff(caminho: Path) -> str:
    """
    Descobre o formato real pelos primeiros bytes.

    Retorna: 'pdf' | 'zip_imagens' | 'jpeg' | 'png' | 'desconhecido'.
    """
    with open(caminho, "rb") as f:
        cabecalho = f.read(8)
    for prefixo, nome in ASSINATURAS:
        if cabecalho.startswith(prefixo):
            return nome
    return "desconhecido"


def _normaliza_imagem(img: Image.Image) -> tuple[bytes, int]:
    """Converte para JPEG no tamanho alvo. Retorna (bytes, area_px)."""
    img = img.convert("RGB")
    largura, altura = img.size
    escala = config.LADO_MAIOR_PX / max(largura, altura)
    if escala < 1:
        img = img.resize((int(largura * escala), int(altura * escala)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=config.JPEG_QUALIDADE, optimize=True)
    return buf.getvalue(), img.size[0] * img.size[1]


def _ordem_numerica(nome: str) -> int:
    """
    Ordena 'pagina_2.jpg' antes de 'pagina_10.jpg'.

    Ordenação alfabética do zipfile colocaria a 10 antes da 2 e embaralharia o
    documento inteiro — sem erro, sem log. O carry-over entre páginas passaria
    contexto da página errada e as tabelas costuradas ficariam sem sentido.
    """
    digitos = re.sub(r"\D", "", Path(nome).stem)
    return int(digitos) if digitos else 0


def _carregar_pdf(caminho: Path) -> list[tuple[bytes, str, int]]:
    doc = pymupdf.open(caminho)
    try:
        saida = []
        for pagina in doc:
            maior = max(pagina.rect.width, pagina.rect.height)
            zoom = config.LADO_MAIOR_PX / maior if maior else 1.0
            pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            jpeg, area = _normaliza_imagem(img)
            saida.append((jpeg, pagina.get_text() or "", area))
        return saida
    finally:
        doc.close()


def _carregar_zip(caminho: Path) -> list[tuple[bytes, str, int]]:
    with zipfile.ZipFile(caminho) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith(EXTENSOES_IMAGEM)]
        if not nomes:
            raise FormatoNaoSuportado(
                f"{caminho.name}: container ZIP sem imagens "
                f"({len(z.namelist())} entradas, nenhuma {EXTENSOES_IMAGEM})"
            )
        nomes.sort(key=_ordem_numerica)

        disponiveis = set(z.namelist())
        saida = []
        for nome in nomes:
            img = Image.open(io.BytesIO(z.read(nome)))
            jpeg, area = _normaliza_imagem(img)
            # O ZIP pode trazer um .txt irmão com o texto nativo da página.
            irmao = str(Path(nome).with_suffix(".txt"))
            texto = z.read(irmao).decode("utf-8", "replace") if irmao in disponiveis else ""
            saida.append((jpeg, texto, area))
        return saida


def carregar_paginas(caminho: Path, formato: str) -> list[tuple[bytes, str, int]]:
    """Retorna [(jpeg_bytes, texto_nativo, area_px), ...] em ordem de página."""
    if formato == "pdf":
        return _carregar_pdf(caminho)
    if formato == "zip_imagens":
        return _carregar_zip(caminho)
    if formato in ("jpeg", "png"):
        jpeg, area = _normaliza_imagem(Image.open(caminho))
        return [(jpeg, "", area)]
    raise FormatoNaoSuportado(
        f"{caminho.name}: formato real '{formato}' não suportado. "
        f"Suportados: pdf, zip_imagens, jpeg, png."
    )
