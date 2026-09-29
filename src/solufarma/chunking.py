"""
chunking.py — Transforma o markdown do OCR em chunks prontos para embedding.

A ideia central: NÃO existe um chunker bom para o documento inteiro. Existem
regimes de conteúdo, e cada um quebra de um jeito.

    prosa hierárquica       -> quebra por seção, respeitando a árvore de headings
    tabela de planilha      -> janelas de N linhas, cabeçalho repetido em cada
    metadados (chave-valor) -> filtro exato em coluna, não busca vetorial

Todo chunk sai com um CABEÇALHO CONTEXTUAL determinístico. É a diferença entre
embedar "QDC-4P-PIL | CJ | 1,00" (vetor sem significado) e embedar o mesmo com
"Planilha de instalações elétricas, CAT 576640, SENAI CETIQT" na frente.
"""

from __future__ import annotations

import re
import unicodedata

from solufarma import config
from solufarma.modelos import Bloco, Chunk

RE_SEPARADOR_TABELA = re.compile(r"^\s*\|[\s:\-\|]+\|\s*$")
RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
RE_MARCA_CONTINUACAO = re.compile(r"<!--\s*\w+\s*-->")
RE_ENFASE_MARKDOWN = re.compile(r"^\*{1,2}(.+?)\*{1,2}$")

# I7 (PRECISÃO.md): sentinela de nível para as pseudo-seções de tabela — maior
# que qualquer nível real de heading markdown (1-6), então um heading de
# verdade sempre estoura a pilha e remove as pseudo-seções acumuladas; e uma
# nova pseudo-seção substitui a anterior em vez de aninhar (ver
# _pseudo_heading_tabela / parsear_blocos).
NIVEL_PSEUDO_SECAO = 900
MAX_CHARS_PSEUDO_SECAO = 40

# I6/P6 (PRECISÃO.md): rótulos de seção em CAIXA ALTA soltos na prosa da folha
# de rosto de CAT/atestado ("DADOS DO CONTRATO", "ATIVIDADE TÉCNICA
# REALIZADA"...), que o OCR não emite como heading markdown. Dois níveis
# sentinela, ambos acima dos headings reais (1-6) e abaixo da pseudo-seção de
# tabela (I7, 900):
#   - PARTE (800): divisão de documento ("ATESTADO DE CAPACIDADE TÉCNICA"),
#     que abre uma parte nova dentro da CAT;
#   - SEÇÃO (850): bloco da certidão/atestado ("DADOS DO CONTRATO"). Aninha
#     sob a PARTE e substitui a seção-irmã anterior.
# Um heading markdown real sempre estoura as duas.
NIVEL_ROTULO_PARTE = 800
NIVEL_ROTULO_SECAO = 850
MAX_CHARS_ROTULO_SECAO = 60

# Vocabulário FECHADO, casado contra a linha inteira já normalizada (sem
# acento, caixa alta, espaços colapsados, sem ":" final). Não há padrão
# genérico de "linha em caixa alta" de propósito: nos 3 documentos do lote de
# 28/09 (OCR de CATs do CREA-SP/RJ escaneadas) as linhas isoladas em caixa
# alta são, na maioria, conteúdo — "CELSO C. HOJAI", "GERENTE INDUSTRIAL",
# "FIOCRUZ", "INSTITUTO BUTANTAN", "RIO DE JANEIRO RJ" — e virariam seção.
# Os padrões toleram plural/singular, preposição (DO/DA/DOS/DAS) e o erro de
# OCR mais comum no acervo ("ESCOPO DOS SERVIOS").
# Ficam de fora de propósito, apesar de parecerem rótulo: "CONTRATANTE",
# "CONTRATADA" e "RESPONSÁVEL TÉCNICO" soltos em caixa alta são, em minuta de
# contrato e em atestado, a legenda da ASSINATURA — virariam seção no rodapé.
# (Quando são seção de verdade, o OCR já emitiu heading: "## 1. CONTRATANTE:".)
# Também fica de fora "CERTIDÃO DE ACERVO TÉCNICO...": é o título do
# documento e se repete como cabeçalho de TODA página na CAT do CAU — virar
# seção faria cada virada de página abrir uma seção vazia de conteúdo.
_ROTULOS_PARTE = (r"ATESTADO DE CAPACIDADE TECNICA( OPERACIONAL| PROFISSIONAL)?",)
_ROTULOS_SECAO = (
    r"DADOS D[OA]S? [A-Z][A-Z /\-]{2,55}",  # DADOS DO CONTRATO / DO PROFISSIONAL / DOS REGISTROS...
    r"DADOS CONTRATUAIS",
    r"ATIVIDADES? TECNICAS?( REALIZADAS?)?",
    r"ENDERECO( D[AO]S? (OBRA|SERVICO|CONTRATANTE)S?(/SERVICOS?)?)?",
    r"DESCRICAO( D[AO]S? [A-Z][A-Z /\-]{2,40})?",
    r"INFORMACOES (IMPORTANTES|COMPLEMENTARES)|INFORMACAO COMPLEMENTAR",
    r"OBSERVACOES( GERAIS)?",
    r"OBJETO( D[OA] (CONTRATO|SERVICO|OBRA))?",
    r"ESCOPO( D[OA]S? SERVI[A-Z]*| D[OA]S? (FORNECIMENTO|OBRAS?))?",
    r"(SERVICOS|OBRAS) EXECUTAD[OA]S",
)
# Numeração opcional na frente: "2. DADOS CONTRATUAIS:", "1.0 - OBJETO".
_PREFIXO_NUMERACAO = r"(\d+(\.\d+)*\.?\s*[-–]?\s*)?"
RE_ROTULO_PARTE = re.compile(_PREFIXO_NUMERACAO + "(" + "|".join(_ROTULOS_PARTE) + ")")
RE_ROTULO_SECAO = re.compile(_PREFIXO_NUMERACAO + "(" + "|".join(_ROTULOS_SECAO) + ")")


# --------------------------------------------------------------------------
# 1. Costura entre páginas — antes de qualquer corte
# --------------------------------------------------------------------------


def costurar(paginas: list[dict]) -> list[tuple[str, int]]:
    """
    Junta o markdown das páginas num fluxo único de (linha, n_pagina),
    resolvendo as marcas de continuação que o OCR emitiu.

    Sem esse passo, todo corte de página vira um corte de chunk — e um
    parágrafo cortado ao meio pela paginação física do PDF vira dois chunks
    ruins. Página é um acidente de impressão, não uma fronteira semântica.
    """
    fluxo: list[tuple[str, int]] = []

    for pag in sorted(paginas, key=lambda p: p["numero"]):
        md = (pag.get("markdown") or "").strip()
        if not md:
            continue

        continua_paragrafo = "<!-- PARAGRAFO_CONTINUA -->" in md
        continua_tabela = "<!-- TABELA_CONTINUA -->" in md
        md = RE_MARCA_CONTINUACAO.sub("", md).strip()
        linhas = md.splitlines()

        if continua_tabela and fluxo:
            # Descarta o cabeçalho reimpresso: a linha de header e o separador.
            # Sem isso a tabela costurada ganha um cabeçalho no meio do corpo e
            # a janela de linhas do chunk_tabela desalinha.
            while linhas and linhas[0].strip().startswith("|"):
                era_separador = bool(RE_SEPARADOR_TABELA.match(linhas[0]))
                linhas.pop(0)
                if era_separador:
                    break

        if continua_paragrafo and fluxo and linhas:
            texto_anterior, pag_anterior = fluxo[-1]
            emenda = linhas.pop(0).lstrip()
            fluxo[-1] = (texto_anterior.rstrip() + " " + emenda, pag_anterior)

        fluxo.extend((linha, pag["numero"]) for linha in linhas)

    return fluxo


# --------------------------------------------------------------------------
# 2. Parsing em blocos com caminho de seção
# --------------------------------------------------------------------------


def _pseudo_heading_tabela(linha: str) -> str | None:
    """
    Detecta linha de TABELA que é, na prática, uma divisão de seção/subseção:
    só a primeira célula tem conteúdo, e ele está em caixa alta e é curto.
    Padrão real do documento (`.tmp/acervo_indexado.md`): `| GASES | | |`,
    `| **HIDRÁULICA** | | |`, `| VÁLVULAS/EQUIPAMENTOS - ( MDO ) | | |`.

    O OCR não emite heading markdown para essas divisões — são linhas de
    tabela soltas —, então sem este reconhecimento o bloco inteiro herda o
    heading anterior, que pode ser de uma seção completamente diferente do
    memorial (PRECISÃO.md P7/I7: o chunk que responde "quantos pontos de gás"
    ficou rotulado como quadro de distribuição elétrica).

    Limite de 40 caracteres (sugestão do próprio PRECISÃO.md): sem ele, uma
    descrição de item em caixa alta — comum nesta planilha — também dispararia
    o gatilho e viraria uma "seção" nova a cada linha.
    """
    if not linha.lstrip().startswith("|") or RE_SEPARADOR_TABELA.match(linha):
        return None

    celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
    if len(celulas) < 2:
        return None

    primeira, *resto = celulas
    if not primeira or any(resto):
        return None

    enfase = RE_ENFASE_MARKDOWN.match(primeira)
    texto = enfase.group(1).strip() if enfase else primeira
    if not texto or len(texto) > MAX_CHARS_PSEUDO_SECAO:
        return None
    if not texto.isupper():
        return None
    return texto


def _normalizar_rotulo(texto: str) -> str:
    """Caixa alta, sem acento, espaços colapsados, sem ':' / '-' no fim."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    colapsado = re.sub(r"\s+", " ", sem_acento).strip().upper()
    return colapsado.rstrip(" :-–").strip()


def _rotulo_secao_prosa(linha: str) -> tuple[int, str] | None:
    """
    Detecta linha de PROSA que é, na prática, um rótulo de seção da folha de
    rosto de CAT/atestado — o análogo em prosa do `_pseudo_heading_tabela`
    (I7). Padrão real (CAT 576640 do CAU, `.tmp/acervo_indexado.md`, e os 3
    documentos do lote de 28/09): linha solta em caixa alta, às vezes com
    espaço nas pontas, sem heading markdown — ` DADOS DO CONTRATO `,
    ` ATIVIDADE TÉCNICA REALIZADA `, `ATESTADO DE CAPACIDADE TECNICA`,
    `ESCOPO DOS SERVIOS` (sic, erro de OCR).

    Sem isto, a folha de rosto inteira vira um bloco sem `caminho_secao`, e o
    trecho mais forte para licitação (área certificada, contrato, CNPJ) fica
    num chunk genérico cujo cabeçalho contextual não tem termo temático
    nenhum — P6: a área de 5.655 m² só aparecia na posição 7 da busca.

    Critérios, TODOS obrigatórios (ver comentário de _ROTULOS_SECAO):
      1. a linha inteira é o rótulo (fullmatch) — "CONTRATANTE: FULANO" é
         chave-valor, não seção; só aceita ":"/"-" no fim e numeração na frente;
      2. está em caixa alta no original (`isupper`);
      3. até 60 caracteres (o maior rótulo real tem 51);
      4. casa com o vocabulário fechado de rótulos de CAT/atestado — sem
         padrão genérico de caixa alta, que dispararia em nome de empresa,
         cargo e cidade.

    Retorna (nível sentinela, título como está no documento) ou None.
    """
    texto = linha.strip()
    if not texto or texto.startswith(("|", "#")):
        return None

    enfase = RE_ENFASE_MARKDOWN.match(texto)
    if enfase:
        texto = enfase.group(1).strip()
    if len(texto) > MAX_CHARS_ROTULO_SECAO or not texto.isupper():
        return None

    normalizado = _normalizar_rotulo(texto)
    titulo = re.sub(r"\s+", " ", texto).rstrip(" :-–").strip()
    if RE_ROTULO_PARTE.fullmatch(normalizado):
        return NIVEL_ROTULO_PARTE, titulo
    if RE_ROTULO_SECAO.fullmatch(normalizado):
        return NIVEL_ROTULO_SECAO, titulo
    return None


def parsear_blocos(fluxo: list[tuple[str, int]]) -> list[Bloco]:
    """Quebra o fluxo em blocos homogêneos, mantendo a pilha de headings."""
    if not fluxo:
        return []

    blocos: list[Bloco] = []
    pilha: list[tuple[int, str]] = []  # (nível do heading, título)
    buffer: list[str] = []
    tipo_atual = "prosa"
    pag_ini = fluxo[0][1]
    pag_fim = pag_ini  # última página com conteúdo REALMENTE no buffer

    def caminho() -> list[str]:
        return [titulo for _, titulo in pilha]

    def fechar() -> None:
        nonlocal buffer
        if any(linha.strip() for linha in buffer):
            blocos.append(Bloco(tipo_atual, buffer, caminho(), pag_ini, pag_fim))
        buffer = []

    for linha, pag in fluxo:
        heading = RE_HEADING.match(linha)

        if heading:
            fechar()
            nivel, titulo = len(heading.group(1)), heading.group(2).strip()
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            pilha.append((nivel, titulo))
            tipo_atual, pag_ini, pag_fim = "prosa", pag, pag
            continue

        pseudo_titulo = _pseudo_heading_tabela(linha)
        if pseudo_titulo:
            fechar()
            # Substitui a pseudo-seção anterior (não aninha): duas divisões
            # consecutivas de tabela ("GASES" seguido de "HIDRÁULICA") são
            # irmãs, não uma dentro da outra. Um heading real de verdade
            # (nível 1-6) sempre estoura esta também, porque NIVEL_PSEUDO_SECAO
            # é maior que qualquer nível real.
            while pilha and pilha[-1][0] >= NIVEL_PSEUDO_SECAO:
                pilha.pop()
            pilha.append((NIVEL_PSEUDO_SECAO, pseudo_titulo))
            tipo_atual, pag_ini, pag_fim = "tabela", pag, pag
            continue

        rotulo = _rotulo_secao_prosa(linha)
        if rotulo:
            fechar()
            # I6: mesmo idioma do I7. O nível sentinela faz a PARTE
            # ("ATESTADO DE CAPACIDADE TÉCNICA") conter as SEÇÕES que vêm
            # depois, uma SEÇÃO substituir a irmã anterior, e as duas
            # derrubarem pseudo-seções de tabela pendentes. Headings markdown
            # reais (1-6) ficam na pilha como ancestrais.
            nivel, titulo = rotulo
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            pilha.append((nivel, titulo))
            tipo_atual, pag_ini, pag_fim = "prosa", pag, pag
            continue

        novo_tipo = "tabela" if linha.lstrip().startswith("|") else "prosa"
        if novo_tipo != tipo_atual:
            fechar()
            tipo_atual, pag_ini = novo_tipo, pag
        if not buffer:
            pag_ini = pag
        buffer.append(linha)
        if linha.strip():
            pag_fim = pag

    fechar()
    return blocos


# --------------------------------------------------------------------------
# 3. Cabeçalho contextual
# --------------------------------------------------------------------------


def cabecalho_contextual(
    doc_titulo: str, caminho: list[str], pagina: int, extra: str = ""
) -> str:
    """
    Prefixo determinístico e barato (zero chamadas de LLM) que resolve o
    problema clássico: o chunk fala de "o piso vinílico das salas dna e hts"
    sem nunca dizer de que obra, documento ou seção veio. A busca por
    "acabamento de piso SENAI CETIQT" não acha esse chunk sem isso.
    """
    partes = [doc_titulo]
    if caminho:
        partes.append(" > ".join(caminho))
    partes.append(f"p. {pagina}")
    if extra:
        partes.append(extra)
    return "[" + " | ".join(partes) + "]"


# --------------------------------------------------------------------------
# 4. Chunkers por regime
# --------------------------------------------------------------------------


def _partir_prosa(texto: str) -> list[tuple[str, bool]]:
    """
    Parte por parágrafo; só cai para frase se um parágrafo sozinho estourar.

    Retorna (pedaco, cortado_por_tamanho). O flag alimenta a métrica D do
    relatório de calibração: acima de 40% de chunks cortados por tamanho
    significa que as seções dos editais reais são maiores que as deste
    documento e ALVO_CHARS precisa subir.
    """
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    pedacos: list[tuple[str, bool]] = []
    atual = ""

    for paragrafo in paragrafos:
        if len(paragrafo) > config.ALVO_CHARS:
            if atual:
                pedacos.append((atual, True))
                atual = ""
            frases = re.split(r"(?<=[.!?])\s+", paragrafo)
            sub = ""
            for frase in frases:
                if len(sub) + len(frase) > config.ALVO_CHARS and sub:
                    pedacos.append((sub, True))
                    sub = sub[-config.OVERLAP_CHARS :] + " " + frase  # overlap só aqui
                else:
                    sub = (sub + " " + frase).strip()
            if sub:
                pedacos.append((sub, True))
        elif len(atual) + len(paragrafo) > config.ALVO_CHARS and atual:
            pedacos.append((atual, True))
            atual = paragrafo
        else:
            atual = (atual + "\n\n" + paragrafo).strip()

    if atual:
        # O último pedaço fecha por fim de seção, não por limite de tamanho.
        pedacos.append((atual, False))
    return pedacos


def chunk_prosa(bloco: Bloco, doc_titulo: str, doc_id: str, seq: list[int]) -> list[Chunk]:
    texto = "\n".join(bloco.linhas).strip()
    saida: list[Chunk] = []

    for pedaco, por_tamanho in _partir_prosa(texto):
        seq[0] += 1
        cab = cabecalho_contextual(doc_titulo, bloco.caminho, bloco.pag_ini)
        saida.append(
            Chunk(
                id=f"{doc_id}#c{seq[0]:04d}",
                texto=f"{cab}\n{pedaco}",
                texto_puro=pedaco,
                tipo="prosa",
                caminho_secao=bloco.caminho,
                pagina_inicio=bloco.pag_ini,
                pagina_fim=bloco.pag_fim,
                n_chars=len(pedaco),
                documento=doc_titulo,
                cortado_por_tamanho=por_tamanho,
            )
        )
    return saida


def chunk_tabela(bloco: Bloco, doc_titulo: str, doc_id: str, seq: list[int]) -> list[Chunk]:
    """
    Janela deslizante de linhas, com o cabeçalho REPETIDO em cada janela.

    Por que não 1 chunk por linha: o vetor de "#240MM2 COR VERDE (FASE) | M |
    900,00" é semanticamente vazio — não há sinal para casar com "quanto de
    cabo de 240mm² foi fornecido". A linha só significa algo junto do cabeçalho
    da coluna e do título da seção.

    Por que não a tabela inteira num chunk: 50 linhas heterogêneas produzem um
    vetor que é a média de tudo, e não casa bem com nada.
    """
    linhas = [ln for ln in bloco.linhas if ln.strip()]
    if not linhas:
        return []

    header: list[str] = []
    corpo = linhas
    if len(linhas) >= 2 and RE_SEPARADOR_TABELA.match(linhas[1]):
        header, corpo = linhas[:2], linhas[2:]

    saida: list[Chunk] = []
    passo = config.LINHAS_POR_CHUNK_TABELA

    for i in range(0, len(corpo), passo):
        janela = corpo[i : i + passo]

        # Última janela órfã (1-3 linhas) volta para a anterior: um chunk de
        # duas linhas de planilha não tem sinal suficiente para recuperar.
        if len(janela) < 4 and saida:
            anterior = saida[-1]
            extra = "\n".join(janela)
            anterior.texto_puro += "\n" + extra
            anterior.texto += "\n" + extra
            anterior.n_chars = len(anterior.texto_puro)
            continue

        seq[0] += 1
        corpo_md = "\n".join(header + janela)
        rotulo = f"itens {i + 1}-{i + len(janela)}"
        cab = cabecalho_contextual(doc_titulo, bloco.caminho, bloco.pag_ini, rotulo)
        saida.append(
            Chunk(
                id=f"{doc_id}#c{seq[0]:04d}",
                texto=f"{cab}\n{corpo_md}",
                texto_puro=corpo_md,
                tipo="tabela",
                caminho_secao=bloco.caminho,
                pagina_inicio=bloco.pag_ini,
                pagina_fim=bloco.pag_fim,
                n_chars=len(corpo_md),
                documento=doc_titulo,
                metadados={
                    "n_linhas": len(janela),
                    "colunas": header[0] if header else None,
                },
            )
        )
    return saida


# --------------------------------------------------------------------------
# 5. Linhas de tabela como dados relacionais (não só vetores)
# --------------------------------------------------------------------------


def extrair_linhas_tabela(blocos: list[Bloco], doc_id: str) -> list[dict]:
    """
    Uma planilha de quantitativos precisa de SQL, não de busca vetorial.
    "Quanto de piso vinílico já fornecemos no total?" é um SUM, e RAG não soma.
    Estas linhas vão para `itens_planilha` no Supabase, em paralelo aos chunks —
    o agente decide entre buscar (vetor) e consultar (SQL).
    """
    itens: list[dict] = []

    for bloco in blocos:
        if bloco.tipo != "tabela":
            continue

        linhas = [ln for ln in bloco.linhas if ln.strip().startswith("|")]
        # Índices a pular: o separador `|---|---|` e a linha IMEDIATAMENTE
        # ANTES dele, que é o cabeçalho de colunas. Sem isso, "Descrição |
        # Unidade | Quantidade" entra em itens_planilha como se fosse um item,
        # e o SUM(quantidade) tenta converter a palavra "Quantidade".
        ignorar: set[int] = set()
        for i, linha in enumerate(linhas):
            if RE_SEPARADOR_TABELA.match(linha):
                ignorar.add(i)
                if i > 0:
                    ignorar.add(i - 1)

        for i, linha in enumerate(linhas):
            if i in ignorar:
                continue
            celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
            if len(celulas) < 2 or not any(celulas):
                continue
            itens.append(
                {
                    "documento_id": doc_id,
                    "pagina": bloco.pag_ini,
                    "secao": " > ".join(bloco.caminho),
                    "celulas": celulas,
                }
            )
    return itens


# --------------------------------------------------------------------------
# 6. Orquestração
# --------------------------------------------------------------------------


def _fundir_residuos(chunks: list[Chunk]) -> list[Chunk]:
    """Funde chunks curtos com o anterior do mesmo tipo e mesma seção."""
    fundidos: list[Chunk] = []
    for c in chunks:
        pode_fundir = (
            fundidos
            and c.n_chars < config.MIN_CHARS
            and fundidos[-1].tipo == c.tipo
            and fundidos[-1].caminho_secao == c.caminho_secao
        )
        if pode_fundir:
            anterior = fundidos[-1]
            anterior.texto_puro += "\n\n" + c.texto_puro
            anterior.texto += "\n\n" + c.texto_puro
            anterior.n_chars = len(anterior.texto_puro)
            anterior.pagina_fim = c.pagina_fim
        else:
            fundidos.append(c)
    return fundidos


def chunkar_documento(doc: dict) -> tuple[list[Chunk], list[dict]]:
    """
    Recebe o dict do JSON de extração. Retorna (chunks, itens_de_planilha).

    Separado do I/O para os testes poderem exercitar a lógica com um dict
    sintético, sem tocar em disco.
    """
    from pathlib import Path

    doc_titulo = Path(doc["arquivo"]).stem.replace("_", " ")
    doc_id = doc["hash_documento"]

    fluxo = costurar(doc["paginas"])
    blocos = parsear_blocos(fluxo)

    seq = [0]
    chunks: list[Chunk] = []
    for bloco in blocos:
        if bloco.tipo == "tabela":
            chunks.extend(chunk_tabela(bloco, doc_titulo, doc_id, seq))
        else:
            chunks.extend(chunk_prosa(bloco, doc_titulo, doc_id, seq))

    return _fundir_residuos(chunks), extrair_linhas_tabela(blocos, doc_id)
