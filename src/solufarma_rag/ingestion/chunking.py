"""Chunking estrutural de documentos de licitação (docs/ARQUITETURA.md §4.6).

Estratégia:
1. **Estrutural primeiro** — o texto é quebrado por seções do edital detectadas
   via regex de cabeçalhos ("1. DO OBJETO", "ANEXO I – TERMO DE REFERÊNCIA",
   "CLÁUSULA SEGUNDA", ...). A seção vira metadado filtrável (`Chunk.secao`).
2. **Empacotamento por tamanho dentro da seção** — blocos (parágrafos) são
   agrupados em chunks de 500–1000 tokens com overlap de 10–15%, sem quebrar
   tabelas Markdown no meio (linhas iniciadas por "|" ficam juntas).
3. **Prefixo contextual** — cada chunk recebe o prefixo
   "[Edital PE 045/2023 – Órgão – Seção: X]" antes do conteúdo, para o
   embedding carregar o contexto do documento (contextual retrieval "barato").

A contagem de tokens usa a heurística `len(texto) // 4` (~4 caracteres/token em
PT-BR) — determinística e sem dependência de tokenizador externo. É estimativa
para dimensionamento de chunks, não para cobrança de API.
"""

from __future__ import annotations

import re

from ..db.models import Chunk, DocumentoParaChunking, PaginaDocumento

# Parâmetros de chunking (skill rag-licitacoes: 500–1000 tokens, overlap 10–15%)
TAMANHO_MAX_TOKENS = 1000
TAMANHO_ALVO_TOKENS = 800
OVERLAP_FRACAO = 0.12  # 12% — dentro da faixa de 10–15%
SECAO_PADRAO = "Preâmbulo"

# Cabeçalhos estruturais de editais/atas
_RE_ANEXO = re.compile(r"^\s*ANEXO\s+([IVXLCDM]+|\d+)\b.*$", re.IGNORECASE)
_RE_CLAUSULA = re.compile(r"^\s*CL[ÁA]USULA\s+\S+.*$", re.IGNORECASE)
_RE_TITULO = re.compile(r"^\s*(CAP[ÍI]TULO|T[ÍI]TULO|SE[ÇC][ÃA]O)\s+\S+.*$", re.IGNORECASE)
# Seção numerada: "1. DO OBJETO", "12.3 DAS SANÇÕES" — exige numeração + restante
# predominantemente maiúsculo (para não confundir com corpo de cláusula).
_RE_SECAO_NUMERADA = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})*)\s*[-–—.)]*\s+(\S.*)$")


def estimar_tokens(texto: str) -> int:
    """Estimativa determinística de tokens (~4 caracteres por token em PT-BR)."""
    return max(1, len(texto) // 4)


def _maiusculo_dominante(texto: str) -> bool:
    """True se as letras do texto forem predominantemente maiúsculas (cabeçalho)."""
    letras = [c for c in texto if c.isalpha()]
    if not letras:
        return False
    maiusculas = sum(1 for c in letras if c.isupper())
    return maiusculas / len(letras) >= 0.8


def _detectar_cabecalho(linha: str) -> str | None:
    """Retorna o título da seção se a linha for um cabeçalho estrutural."""
    linha_limpa = linha.strip()
    if not linha_limpa or len(linha_limpa) > 120:
        return None
    if _RE_ANEXO.match(linha_limpa) or _RE_CLAUSULA.match(linha_limpa) or _RE_TITULO.match(linha_limpa):
        return linha_limpa
    m = _RE_SECAO_NUMERADA.match(linha_limpa)
    if m and _maiusculo_dominante(m.group(2)):
        return linha_limpa
    return None


class _Bloco:
    """Unidade mínima de empacotamento: um parágrafo ou uma tabela inteira."""

    __slots__ = ("pagina", "secao", "texto")

    def __init__(self, secao: str, pagina: int, texto: str) -> None:
        self.secao = secao
        self.pagina = pagina
        self.texto = texto


def _extrair_blocos(paginas: list[PaginaDocumento]) -> list[_Bloco]:
    """Percorre as páginas produzindo blocos anotados com seção e página.

    Linhas de tabela Markdown (iniciadas por "|") consecutivas formam um único
    bloco, para nunca quebrar tabela no meio de um chunk.
    """
    blocos: list[_Bloco] = []
    secao_atual = SECAO_PADRAO

    def fechar(paragrafo: list[str], secao: str, numero_pagina: int) -> list[str]:
        """Materializa o parágrafo acumulado como bloco e devolve um novo vazio."""
        if paragrafo:
            blocos.append(_Bloco(secao, numero_pagina, "\n".join(paragrafo)))
        return []

    for pagina in paginas:
        paragrafo: list[str] = []
        em_tabela = False

        for linha in pagina.texto.splitlines():
            linha_strip = linha.strip()
            if not linha_strip:
                paragrafo = fechar(paragrafo, secao_atual, pagina.numero)
                em_tabela = False
                continue

            titulo = _detectar_cabecalho(linha_strip)
            if titulo is not None:
                # Fecha sob a seção ANTERIOR antes de trocar — o texto acumulado
                # pertence à seção que está terminando, não à que começa.
                paragrafo = fechar(paragrafo, secao_atual, pagina.numero)
                em_tabela = False
                secao_atual = titulo
                # O próprio cabeçalho abre o primeiro bloco da seção.
                paragrafo = [linha_strip]
                continue

            linha_de_tabela = linha_strip.startswith("|")
            if paragrafo and linha_de_tabela != em_tabela:
                # Transição texto ↔ tabela: fecha o bloco anterior.
                paragrafo = fechar(paragrafo, secao_atual, pagina.numero)
            em_tabela = linha_de_tabela
            paragrafo.append(linha_strip)

        fechar(paragrafo, secao_atual, pagina.numero)
    return blocos


def _dividir_bloco_grande(bloco: _Bloco, max_chars: int) -> list[_Bloco]:
    """Divide um bloco maior que o orçamento por sentenças (último recurso).

    Orçamento em caracteres pelo mesmo motivo de `_orcamento_corpo_chars`.
    Uma sentença isolada maior que o orçamento é fatiada à força — melhor um
    corte no meio da frase do que um chunk acima do teto.
    """
    if len(bloco.texto) <= max_chars:
        return [bloco]

    partes: list[_Bloco] = []
    atual: list[str] = []
    chars_atual = 0

    def fechar() -> None:
        nonlocal atual, chars_atual
        if atual:
            partes.append(_Bloco(bloco.secao, bloco.pagina, " ".join(atual)))
        atual, chars_atual = [], 0

    for sentenca in re.split(r"(?<=[.;:!?])\s+", bloco.texto):
        while len(sentenca) > max_chars:
            fechar()
            partes.append(_Bloco(bloco.secao, bloco.pagina, sentenca[:max_chars]))
            sentenca = sentenca[max_chars:]
        if not sentenca:
            continue
        # +1 pelo espaço que unirá esta sentença à anterior.
        custo = len(sentenca) + (1 if atual else 0)
        if atual and chars_atual + custo > max_chars:
            fechar()
            custo = len(sentenca)
        atual.append(sentenca)
        chars_atual += custo
    fechar()
    return partes


def _montar_prefixo(doc: DocumentoParaChunking, secao: str) -> str:
    """Prefixo contextual do chunk, ex.: "[Edital PE 045/2023 – SES/GO – Seção: ...]"."""
    tipo = doc.tipo_documento.capitalize()
    identificacao = f"{tipo} {doc.numero_edital}" if doc.numero_edital else tipo
    return f"[{identificacao} – {doc.orgao} – Seção: {secao}]"


def _orcamento_corpo_chars(doc: DocumentoParaChunking, secao: str, teto_tokens: int) -> int:
    """Caracteres disponíveis para o CORPO, descontando o prefixo contextual.

    A contabilidade é feita em CARACTERES, não somando `estimar_tokens` de cada
    bloco: como o estimador usa divisão inteira (`len // 4`), somar por peça
    subestima o total (cada peça perde até 3 caracteres no arredondamento) e o
    erro acumula — era por isso que chunks estouravam o teto mesmo com a
    verificação de limite no lugar.

    O prefixo entra no `conteudo` (e portanto no `token_count` e no embedding),
    então também sai do orçamento; ele cresce com o nome do órgão e da seção.
    """
    chars_prefixo = len(_montar_prefixo(doc, secao)) + 1  # +1 pela quebra de linha
    return max(4, teto_tokens * 4 - chars_prefixo)


def _chars_corpo(pedacos: list[str]) -> int:
    """Comprimento exato do corpo montado — os pedaços são unidos por "\\n\\n"."""
    if not pedacos:
        return 0
    return sum(len(p) for p in pedacos) + 2 * (len(pedacos) - 1)


def _texto_de_overlap(corpo: str, tokens_overlap: int) -> str:
    """Retorna o final do corpo com aproximadamente `tokens_overlap` tokens."""
    caracteres = tokens_overlap * 4
    if caracteres <= 0 or len(corpo) <= caracteres:
        return ""
    cauda = corpo[-caracteres:]
    # Alinha no início de uma palavra para não cortar no meio.
    espaco = cauda.find(" ")
    if 0 <= espaco < len(cauda) - 1:
        cauda = cauda[espaco + 1 :]
    return cauda


def gerar_chunks(
    doc: DocumentoParaChunking,
    tamanho_max_tokens: int = TAMANHO_MAX_TOKENS,
    tamanho_alvo_tokens: int = TAMANHO_ALVO_TOKENS,
    overlap_fracao: float = OVERLAP_FRACAO,
) -> list[Chunk]:
    """Gera os chunks de um documento com metadados completos e content_hash.

    Determinístico: o mesmo documento produz sempre os mesmos chunks e hashes,
    o que garante a indexação incremental (chunks inalterados não são
    re-embeddados pelo pipeline de embeddings).
    """
    blocos_brutos = _extrair_blocos(doc.paginas)
    blocos: list[_Bloco] = []
    for b in blocos_brutos:
        blocos.extend(
            _dividir_bloco_grande(b, _orcamento_corpo_chars(doc, b.secao, tamanho_max_tokens))
        )

    chunks: list[Chunk] = []
    corpo_atual: list[str] = []
    paginas_atual: list[int] = []
    secao_atual: str | None = None
    tokens_overlap = int(tamanho_alvo_tokens * overlap_fracao)

    def fechar_chunk() -> None:
        nonlocal corpo_atual, paginas_atual
        if not corpo_atual:
            return
        corpo = "\n\n".join(corpo_atual)
        prefixo = _montar_prefixo(doc, secao_atual or SECAO_PADRAO)
        conteudo = f"{prefixo}\n{corpo}"
        chunks.append(
            Chunk(
                documento_id=doc.documento_id,
                chunk_index=len(chunks),
                tipo_documento=doc.tipo_documento,
                orgao=doc.orgao,
                data=doc.data,
                secao=secao_atual or SECAO_PADRAO,
                pagina_inicio=min(paginas_atual),
                pagina_fim=max(paginas_atual),
                conteudo=conteudo,
                token_count=estimar_tokens(conteudo),
                content_hash=Chunk.calcular_hash(conteudo),
            )
        )
        # Overlap: o próximo chunk (mesma seção) começa com a cauda deste.
        cauda = _texto_de_overlap(corpo, tokens_overlap)
        corpo_atual = [cauda] if cauda else []
        paginas_atual = [max(paginas_atual)] if cauda else []

    for bloco in blocos:
        if secao_atual is not None and bloco.secao != secao_atual:
            # Mudança de seção: fecha o chunk e descarta o overlap (não vaza
            # conteúdo de uma seção para outra).
            fechar_chunk()
            corpo_atual, paginas_atual = [], []
        secao_atual = bloco.secao

        teto_chars = _orcamento_corpo_chars(doc, bloco.secao, tamanho_max_tokens)
        alvo_chars = min(tamanho_alvo_tokens * 4, teto_chars)
        chars_com_bloco = _chars_corpo(corpo_atual + [bloco.texto])

        if corpo_atual and chars_com_bloco > alvo_chars:
            fechar_chunk()
            # O fecho reabre o chunk com a cauda de overlap. Se o bloco seguinte
            # ainda não couber ABAIXO DO TETO junto dessa cauda, descarta-se o
            # overlap: um chunk menor é melhor que um chunk acima do limite.
            if corpo_atual and _chars_corpo(corpo_atual + [bloco.texto]) > teto_chars:
                corpo_atual, paginas_atual = [], []
        corpo_atual.append(bloco.texto)
        paginas_atual.append(bloco.pagina)

    fechar_chunk()
    return chunks
