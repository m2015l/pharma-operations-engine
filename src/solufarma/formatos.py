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
import logging
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

_log = logging.getLogger(__name__)

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


# --------------------------------------------------------------------------
# Reconstrução de tabela em página NATIVA
# --------------------------------------------------------------------------
#
# `page.get_text()` devolve os fragmentos na ordem em que foram desenhados, e a
# grade da tabela some: o código do item, a descrição, a quantidade e a unidade
# viram linhas soltas, às vezes separadas por sete linhas de texto. Para prosa
# isso é irrelevante; para uma planilha de quantitativos destrói o dado, porque
# o que importa é justamente a ligação entre as células.
#
# `find_tables()` recupera a grade quando a tabela tem linhas gráficas. Quando
# não tem, devolve zero tabelas — e aí a página precisa do VLM (ver
# `extracao.refinar_rotas`).

# Unidades de medida típicas de planilha de obra. Servem para identificar a
# coluna de unidade e, em `extracao`, para suspeitar que a página é planilha.
UNIDADES_PLANILHA = {
    "vb", "pç", "pc", "cj", "cjto", "un", "und", "unid", "m", "m2", "m²",
    "m3", "m³", "kg", "ml", "l", "mes", "mês", "h", "hora", "t", "km", "par",
    "jg", "gl", "sc", "dia",
}

# Número em formato pt-BR: "2.169,20", "1,00", "28".
RE_NUMERO_PTBR = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^-?\d+(?:,\d+)?$")
# Código hierárquico de item: "6.3.1", "31.1.15", "2".
RE_CODIGO_ITEM = re.compile(r"^\d+(?:\.\d+)*$")


def _celula_markdown(valor: str | None) -> str:
    """Achata a célula para caber numa linha de tabela markdown."""
    texto = (valor or "").replace("|", r"\|")
    return " ".join(texto.split())


def _proporcao(valores: list[str], teste) -> float:
    """Fração das células NÃO VAZIAS que passam no teste."""
    preenchidas = [v for v in valores if v]
    if not preenchidas:
        return 0.0
    return sum(1 for v in preenchidas if teste(v)) / len(preenchidas)


def inferir_cabecalho(linhas: list[list[str]]) -> tuple[list[str], bool]:
    """
    Nomeia as colunas por heurística. Retorna (nomes, algum_nome_inferido).

    NÃO usa o `header` do `find_tables()`: em página de continuação de planilha
    não existe linha de cabeçalho, e ele devolve a PRIMEIRA LINHA DE DADOS como
    se fosse cabeçalho. Emitir isso como cabeçalho faria `extrair_linhas_tabela`
    descartar um item real — o mesmo modo de falha do bug corrigido em 07/08,
    ao contrário.

    A inferência é deliberadamente conservadora: rotula só o que é inequívoco e
    cai para "Coluna N" no resto. Rótulo errado é pior que rótulo genérico,
    porque vai para o cabeçalho contextual do chunk e portanto para o embedding.
    """
    n_col = max((len(ln) for ln in linhas), default=0)
    colunas = [[(ln[i] if i < len(ln) else "") for ln in linhas] for i in range(n_col)]

    def e_unidade(v: str) -> bool:
        return v.strip().lower() in UNIDADES_PLANILHA

    def e_numero(v: str) -> bool:
        return bool(RE_NUMERO_PTBR.match(v.strip()))

    def e_codigo(v: str) -> bool:
        return bool(RE_CODIGO_ITEM.match(v.strip()))

    numericas = [i for i, col in enumerate(colunas) if _proporcao(col, e_numero) >= 0.6]
    nomes: list[str] = []
    inferiu = False
    for i, col in enumerate(colunas):
        preenchidas = [v for v in col if v]
        media = sum(len(v) for v in preenchidas) / len(preenchidas) if preenchidas else 0
        if _proporcao(col, e_unidade) >= 0.6:
            nome = "Unidade"
        elif i == 0 and _proporcao(col, e_codigo) >= 0.6:
            nome = "Item"
        elif media > 25:
            nome = "Descrição"
        elif i in numericas and len(numericas) == 1:
            # Só rotula "Quantidade" quando há UMA coluna numérica. Com duas ou
            # mais (quantidade, valor unitário, total) qualquer escolha é chute,
            # e um chute aqui vira número com rótulo errado no banco.
            nome = "Quantidade"
        else:
            nome = f"Coluna {i + 1}"
        inferiu = inferiu or not nome.startswith("Coluna")
        nomes.append(nome)
    return nomes, inferiu


def tabela_para_markdown(linhas: list[list[str]]) -> str:
    """Monta a tabela markdown com cabeçalho inferido e separador."""
    if not linhas:
        return ""
    nomes, _ = inferir_cabecalho(linhas)
    n_col = len(nomes)

    def formata(celulas: list[str]) -> str:
        completas = [_celula_markdown(c) for c in celulas[:n_col]]
        completas += [""] * (n_col - len(completas))
        return "| " + " | ".join(completas) + " |"

    saida = [formata(nomes), "|" + "---|" * n_col]
    saida.extend(formata(ln) for ln in linhas)
    return "\n".join(saida)




# Uma "tabela" de uma linha só costuma ser uma caixa de texto com borda, não
# dado tabular. Reconstruí-la trocaria prosa boa por uma tabela de uma linha.
MIN_LINHAS_TABELA = 2
MIN_COLUNAS_TABELA = 2


def _linhas_uteis(tabela) -> list[list[str]]:
    return [
        [(c or "") for c in linha]
        for linha in tabela.extract()
        if any((c or "").strip() for c in linha)
    ]


def _tabela_vale(linhas: list[list[str]]) -> bool:
    return (
        len(linhas) >= MIN_LINHAS_TABELA
        and max((len(ln) for ln in linhas), default=0) >= MIN_COLUNAS_TABELA
    )


def reconstruir_pagina(pagina) -> str | None:
    """
    Remonta a página nativa preservando a ordem vertical de prosa e tabelas.

    Devolve None quando não há tabela aproveitável — a página segue pela rota
    nativa comum.

    A prosa em volta da tabela É PRESERVADA. Trocar a página inteira pela tabela
    apagaria o texto de abertura e o de fecho: no acervo, a página de assinatura
    do atestado tem uma tabela de 5 linhas seguida da frase que diz quem assinou
    e quando — e essa frase responde uma das perguntas do golden set.
    """
    try:
        tabelas = [t for t in pagina.find_tables().tables if _tabela_vale(_linhas_uteis(t))]
    except Exception as exc:  # noqa: BLE001 — layout patológico não derruba o lote
        _log.warning("find_tables falhou na página %d: %s", pagina.number + 1, exc)
        return None
    if not tabelas:
        return None

    areas = [pymupdf.Rect(t.bbox) for t in tabelas]
    pecas: list[tuple[float, str]] = []

    for bloco in pagina.get_text("blocks"):
        x0, y0, x1, y1, texto = bloco[0], bloco[1], bloco[2], bloco[3], bloco[4]
        if not texto.strip():
            continue
        retangulo = pymupdf.Rect(x0, y0, x1, y1)
        # Um bloco cuja maior parte cai dentro da tabela já foi capturado pelo
        # extract() — repetí-lo duplicaria o conteúdo no chunk e no embedding.
        dentro = any(
            (retangulo & area).get_area() > 0.5 * retangulo.get_area()
            for area in areas
            if retangulo.intersects(area)
        )
        if not dentro:
            pecas.append((y0, texto.strip()))

    for tabela, area in zip(tabelas, areas):
        pecas.append((area.y0, tabela_para_markdown(_linhas_uteis(tabela))))

    pecas.sort(key=lambda par: par[0])
    return "\n\n".join(texto for _, texto in pecas).strip() or None


def tabelas_nativas(caminho: Path, indices: list[int]) -> dict[int, str]:
    """
    Reconstrói as páginas nativas pedidas (índices 0-based).

    Retorna {indice: markdown} só para as páginas em que alguma tabela foi
    aproveitada. Página ausente do resultado ou não tem tabela, ou tem uma sem
    grade gráfica — e nesse caso quem decide o destino é `extracao.refinar_rotas`.
    """
    if not indices:
        return {}
    encontradas: dict[int, str] = {}
    doc = pymupdf.open(caminho)
    try:
        for i in indices:
            if i >= doc.page_count:
                continue
            markdown = reconstruir_pagina(doc[i])
            if markdown:
                encontradas[i] = markdown
    finally:
        doc.close()
    return encontradas
