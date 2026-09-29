"""Montagem de contexto numerado e parsing das citações [n] da resposta.

Fecha o ciclo de rastreabilidade [n] → chunk → documento → página
(docs/ARQUITETURA.md §5.4). O backend converte as `Citacao` resultantes em
cards clicáveis no Streamlit (título do doc + página + link assinado do PDF).
"""

from __future__ import annotations

import re

from ..db.models import Chunk, ChunkComScore, Citacao

_RE_MARCADOR = re.compile(r"\[(\d+)\]")
_TAMANHO_TRECHO_EXIBICAO = 200


def montar_contexto(resultados: list[ChunkComScore]) -> str:
    """Formata os chunks recuperados como trechos numerados para o prompt.

    O id numérico (1-based) é o que o modelo referencia como [n]. Os metadados
    (documento, seção, página) entram na tag para o modelo poder mencioná-los.
    Executante/grupo só entram quando o documento já foi classificado.
    """
    partes: list[str] = []
    for n, resultado in enumerate(resultados, start=1):
        c = resultado.chunk
        executante = ""
        if c.executante_grupo:
            executante = (
                f' executante="{c.executante or "—"}" executante_grupo="{c.executante_grupo}"'
            )
        partes.append(
            f'<trecho id="{n}" documento_id="{c.documento_id}" tipo="{c.tipo_documento}" '
            f'orgao="{c.orgao}" secao="{c.secao}" pagina="{c.pagina_inicio}-{c.pagina_fim}"'
            f"{executante}>\n"
            f"{c.conteudo}\n</trecho>"
        )
    return "\n\n".join(partes)


def extrair_citacoes(
    resposta: str, resultados: list[ChunkComScore]
) -> tuple[list[Citacao], list[int]]:
    """Resolve os marcadores [n] da resposta em citações rastreáveis.

    Retorna (citações válidas, marcadores inválidos). Um marcador é inválido
    quando referencia um id que não existe no contexto — sinal de alucinação
    de fonte, que o chamador deve tratar (logar/alertar), nunca ignorar.
    """
    citacoes: list[Citacao] = []
    invalidos: list[int] = []
    vistos: set[int] = set()

    for texto_n in _RE_MARCADOR.findall(resposta):
        n = int(texto_n)
        if n in vistos:
            continue
        vistos.add(n)
        if 1 <= n <= len(resultados):
            citacoes.append(_montar_citacao(n, resultados[n - 1].chunk))
        else:
            invalidos.append(n)

    citacoes.sort(key=lambda c: c.marcador)
    return citacoes, sorted(invalidos)


def _montar_citacao(marcador: int, chunk: Chunk) -> Citacao:
    # O conteúdo começa com o prefixo contextual "[Edital ... – Órgão – Seção: ...]",
    # que o usuário já vê nos metadados da citação. Exibi-lo aqui consumiria boa
    # parte dos 200 caracteres do trecho (órgãos têm nomes longos), então o corte
    # é feito sobre o corpo real do documento.
    corpo = chunk.conteudo.split("\n", 1)[-1] if "\n" in chunk.conteudo else chunk.conteudo
    trecho = corpo[:_TAMANHO_TRECHO_EXIBICAO]
    if len(corpo) > _TAMANHO_TRECHO_EXIBICAO:
        trecho += "…"
    return Citacao(
        marcador=marcador,
        chunk_chave=chunk.chave,
        documento_id=chunk.documento_id,
        tipo_documento=chunk.tipo_documento,
        orgao=chunk.orgao,
        secao=chunk.secao,
        pagina_inicio=chunk.pagina_inicio,
        pagina_fim=chunk.pagina_fim,
        trecho=trecho,
        executante=chunk.executante,
        executante_grupo=chunk.executante_grupo,
    )
