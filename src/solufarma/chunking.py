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

# Títulos que são DADO, não seção (Cristália Obra II, 29/09): em memorial de
# cabos o "#" é o símbolo de bitola — "# 1,0 mm²   1", "# 70mm²  VBC-Y4",
# "# 115" — e o RE_HEADING os lia como heading markdown. Cada um abria uma
# "seção" nova, o chunk seguinte herdava o rótulo absurdo e o resto numérico
# entre dois deles ("50 \nm \n42.5") virava chunk próprio, pequeno demais até
# para receber embedding.
_UNIDADES = (
    "mm", "mm²", "mm2", "cm", "m", "m²", "m2", "m³", "m3", "kg", "kv", "kva", "kw",
    "hp", "cv", "tr", "pç", "pc", "pcs", "un", "und", "vb", "br", "cj", "sh", "ml", "l",
)
RE_NUMERO_COM_UNIDADE = re.compile(
    r"^\d+([.,]\d+)?\s*(" + "|".join(re.escape(u) for u in _UNIDADES) + r")(?![A-Za-zÀ-ÿ])",
    re.IGNORECASE,
)
RE_PALAVRA = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")

# Resto de chunk sem nenhuma palavra de verdade ("50 \nm \n42.5", "42 \npç \n33.25")
# é continuação numérica do chunk anterior, não conteúdo próprio.
MAX_CHARS_RESIDUO = 80
RE_RODAPE_PAGINA = re.compile(r"p[áa]gina\s+\d+\s+de\s+\d+", re.IGNORECASE)


def _titulo_e_dado(titulo: str) -> bool:
    """O "título" é célula numérica/unidade, e não nome de seção?

    Verdadeiro quando começa com número colado a unidade ("35 mm²", "70mm² VBC")
    ou quando não sobra nenhuma palavra de 3+ letras além de unidades ("115",
    "1,5 mm² +SH  2"). Um título de seção real sempre tem ao menos uma palavra.
    """
    texto = titulo.strip().strip("*").strip()
    if not texto or RE_NUMERO_COM_UNIDADE.match(texto):
        return True
    palavras = [
        p for p in RE_PALAVRA.findall(texto) if len(p) >= 3 and p.lower() not in _UNIDADES
    ]
    return not palavras


def _e_residuo(texto: str) -> bool:
    """Trecho curto sem nenhuma palavra de 4+ letras (fora rodapé de página)."""
    if len(texto) > MAX_CHARS_RESIDUO:
        return False
    sem_rodape = RE_RODAPE_PAGINA.sub(" ", texto)
    return not any(len(p) >= 4 for p in RE_PALAVRA.findall(sem_rodape))


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
    if not texto.isupper() or _titulo_e_dado(texto):
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
    buffer_pags: list[int] = []  # página de cada linha do buffer
    tipo_atual = "prosa"
    pag_ini = fluxo[0][1]
    pag_fim = pag_ini  # última página com conteúdo REALMENTE no buffer

    def caminho() -> list[str]:
        return [titulo for _, titulo in pilha]

    def fechar() -> None:
        nonlocal buffer, buffer_pags
        if any(linha.strip() for linha in buffer):
            blocos.append(
                Bloco(tipo_atual, buffer, caminho(), pag_ini, pag_fim, buffer_pags)
            )
        buffer, buffer_pags = [], []

    for linha, pag in fluxo:
        heading = RE_HEADING.match(linha)
        if heading and _titulo_e_dado(heading.group(2)):
            # "# 1,0 mm²" é bitola de cabo, não heading: segue como conteúdo.
            heading = None

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
        buffer_pags.append(pag)
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


class _LocalizadorPaginas:
    """Acha as páginas de cada pedaço de um bloco longo.

    Compara sem espaço em branco nenhum: `_partir_prosa` refaz as junções
    (parágrafos com "\\n\\n", frases com " ", overlap), então o pedaço não é
    substring literal do bloco — mas é, tirando os espaços. Os pedaços saem em
    ordem, e o cursor só avança pelo INÍCIO de cada um (o overlap faz o próximo
    começar antes do fim do anterior). Não achou: cai na faixa do bloco inteiro.
    """

    def __init__(self, bloco: Bloco):
        self.bloco = bloco
        chars: list[str] = []
        pags: list[int] = []
        if len(bloco.paginas_linhas) == len(bloco.linhas):
            for linha, pag in zip(bloco.linhas, bloco.paginas_linhas):
                for ch in linha:
                    if not ch.isspace():
                        chars.append(ch)
                        pags.append(pag)
        self.texto = "".join(chars)
        self.pags = pags
        self.cursor = 0

    def paginas(self, pedaco: str) -> tuple[int, int]:
        compacto = "".join(pedaco.split())
        pos = self.texto.find(compacto[:60], self.cursor) if compacto and self.pags else -1
        if pos < 0:
            return self.bloco.pag_ini, self.bloco.pag_fim
        self.cursor = pos + 1
        fim = min(pos + len(compacto), len(self.pags)) - 1
        return self.pags[pos], self.pags[fim]


def chunk_prosa(bloco: Bloco, doc_titulo: str, doc_id: str, seq: list[int]) -> list[Chunk]:
    texto = "\n".join(bloco.linhas).strip()
    saida: list[Chunk] = []
    localizador = _LocalizadorPaginas(bloco)

    for pedaco, por_tamanho in _partir_prosa(texto):
        seq[0] += 1
        pag_ini, pag_fim = localizador.paginas(pedaco)
        cab = cabecalho_contextual(doc_titulo, bloco.caminho, pag_ini)
        saida.append(
            Chunk(
                id=f"{doc_id}#c{seq[0]:04d}",
                texto=f"{cab}\n{pedaco}",
                texto_puro=pedaco,
                tipo="prosa",
                caminho_secao=bloco.caminho,
                pagina_inicio=pag_ini,
                pagina_fim=pag_fim,
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
    # Cada linha carrega a página de onde veio, para a janela saber o
    # intervalo REAL que cobre. Sem isso um chunk de 20 itens da página 40
    # citaria "páginas 15-143", que é o mesmo que não citar página nenhuma.
    paginas_bloco = bloco.paginas_linhas or [bloco.pag_ini] * len(bloco.linhas)
    pares = [(ln, pag) for ln, pag in zip(bloco.linhas, paginas_bloco) if ln.strip()]
    if not pares:
        return []
    linhas = [ln for ln, _ in pares]
    paginas = [pag for _, pag in pares]

    header: list[str] = []
    corpo, paginas_corpo = linhas, paginas
    if len(linhas) >= 2 and RE_SEPARADOR_TABELA.match(linhas[1]):
        header, corpo, paginas_corpo = linhas[:2], linhas[2:], paginas[2:]

    saida: list[Chunk] = []
    passo = config.LINHAS_POR_CHUNK_TABELA

    for i in range(0, len(corpo), passo):
        janela = corpo[i : i + passo]
        paginas_janela = paginas_corpo[i : i + passo] or [bloco.pag_ini]

        # Última janela órfã (1-3 linhas) volta para a anterior: um chunk de
        # duas linhas de planilha não tem sinal suficiente para recuperar.
        if len(janela) < 4 and saida:
            anterior = saida[-1]
            extra = "\n".join(janela)
            anterior.texto_puro += "\n" + extra
            anterior.texto += "\n" + extra
            anterior.n_chars = len(anterior.texto_puro)
            anterior.pagina_fim = max(anterior.pagina_fim, max(paginas_janela))
            continue

        seq[0] += 1
        corpo_md = "\n".join(header + janela)
        rotulo = f"itens {i + 1}-{i + len(janela)}"
        pag_ini_janela, pag_fim_janela = min(paginas_janela), max(paginas_janela)
        cab = cabecalho_contextual(doc_titulo, bloco.caminho, pag_ini_janela, rotulo)
        saida.append(
            Chunk(
                id=f"{doc_id}#c{seq[0]:04d}",
                texto=f"{cab}\n{corpo_md}",
                texto_puro=corpo_md,
                tipo="tabela",
                caminho_secao=bloco.caminho,
                pagina_inicio=pag_ini_janela,
                pagina_fim=pag_fim_janela,
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


# Código hierárquico de item citado numa observação do VLM: "2.1", "3.10".
# Exige ao menos um ponto: um número solto ("linha 2") é ruído demais.
# O sufixo de letras é o da planilha da Aeronáutica ("04.01.521.ac"): sem ele o
# código citado virava "04.01.521", que não casa com célula nenhuma, e as 7
# lacunas de carimbo do LAQFA/CEMFAR entraram no banco como "vazio" (07/10).
# O `(?![.,]\d)` final descarta valor em formato pt-BR: em "transcrito como
# '13.019,28'" o "13.019" não é código, e lido como tal impedia a oração de
# herdar o item de que ela fala.
RE_CODIGO_CITADO = re.compile(r"\b\d+(?:\.\d+)+(?:\.[A-Za-z]{1,3})?\b(?![.,]\d)")

# Divide a observação em frases. O lookbehind exige letra ou ")" antes do ponto,
# senão "2.1" seria partido ao meio e o código se perderia. O lookahead exige
# maiúscula ou dígito depois: "coluna UNIDADE/QUANT. está obscurecida" é uma
# frase só, e partida na abreviação o código ficava de um lado e o motivo do outro.
RE_FRASE = re.compile(r"(?<=[A-Za-zÀ-ÿ)\]])\.\s+(?=[A-ZÀ-Ý0-9(\"'])")
# Orações da mesma frase. A oração sem código fala do item da oração anterior:
# "o item 18.6.35 está obscurecido; foi inferido como '2,00'".
RE_ORACAO = re.compile(r";\s+")

# O modelo diz por que a célula está vazia, e o motivo muda o que fazer. Estas
# listas leem essa intenção. Foram derivadas das observações reais do acervo —
# CAT SJC-003369 (páginas 5, 7, 8, 10 e 23) e, em 08/10, as 65 observações com
# código citado dos 9 documentos do lote de OCR — não de suposição sobre como o
# modelo escreve.
#
# "o valor existe no papel e eu não consegui lê-lo":
MARCAS_ILEGIVEL = (
    "ilegív", "ilegiv", "em branco", "deixad", "não foi possível ler",
    "nao foi possivel ler", "não legível", "obstru", "encobr", "apagad",
    "impossibilit", "não está legív", "nao esta legiv",
    "não possui quantidade legív", "nao possui quantidade legiv",
)
# "está vazio no documento mesmo, não é perda":
MARCAS_LEGITIMO = (
    "no original", "título", "titulo", "subgrupo", "cabeçalho", "cabecalho",
    "heading", "ausente na numeração", "ausente na numeracao",
)
# "tem carimbo em cima, mas eu acho que li certo" — não é perda declarada nem
# vazio garantido. Merece olho humano, não preenchimento cego:
MARCAS_OBSTRUCAO = (
    "carimbo", "sobrepõe", "sobrepost", "selo", "rubrica", "marcas rotacionadas",
    "obscurec", "ocult", "cortad",
)
# "escrevi um valor, mas não garanto": o caso mais perigoso, porque a célula sai
# PREENCHIDA. Página 19 do Butantan hemoderivados: "foi inferido como '2,00' por
# consistência com o item seguinte". Sem isto a linha entra como "ok".
MARCAS_INCERTO = (
    "inferid", "pode estar incorret", "podem estar incorret", "incerteza",
    "interpreta", "possível confirmar", "possivel confirmar", "ler com certeza",
)
# ...a menos que o próprio modelo desfaça a dúvida na mesma oração: "leve
# incerteza de leitura, mas os valores numéricos permaneceram legíveis".
RE_REAFIRMA = re.compile(r"\bmas\b.*(?:leg[ií]ve|boa confian[çc]a)", re.IGNORECASE)

# Diagnóstico mais grave não é apagado por outro mais frouxo dito depois.
_GRAVIDADE = {"vazio": 0, "suspeita": 0, "incerta": 1, "ilegivel": 2}


def _intencao(oracao: str) -> str | None:
    """A classificação que uma oração da observação declara, ou None."""
    baixa = oracao.lower()
    # A ordem importa: "vazio no original" vence "tem carimbo na página",
    # porque é uma afirmação sobre a célula, não sobre a página.
    if any(m in baixa for m in MARCAS_LEGITIMO):
        return "vazio"
    if any(m in baixa for m in MARCAS_ILEGIVEL):
        return "ilegivel"
    if any(m in baixa for m in MARCAS_INCERTO) and not RE_REAFIRMA.search(oracao):
        return "incerta"
    if any(m in baixa for m in MARCAS_OBSTRUCAO):
        return "suspeita"
    return None


def sinais_da_observacao(observacoes: str) -> dict[str, str]:
    """
    Lê a observação do VLM e devolve {código do item: classificação}.

    Por que não basta achar os códigos: a intenção do texto muda tudo, e as duas
    frases abaixo são dos mesmos documentos do acervo.

        página 5  "carimbos ... nas linhas 2.1, 2.5 ... tornando alguns valores
                   ILEGÍVEIS - foram deixados em branco por fidelidade"
                   -> o valor existe no papel. Precisa ser preenchido.

        página 7  "células de UNIDADE/QUANTIDADE ficaram vazias NO ORIGINAL para
                   linhas que são apenas TÍTULOS DE SUBGRUPO (ex: 6.1, 6.3...)"
                   -> não há valor nenhum a recuperar. Mandar alguém procurar
                      esse número é mandar procurar o que não existe.

    Tratar as duas iguais — o que uma busca crua por código faria — produziria
    cinco pedidos de preenchimento falsos só na página 7 deste documento.

    Quatro classificações: "vazio", "ilegivel", "suspeita" (há obstrução, o
    modelo não disse que perdeu o valor) e "incerta" (o modelo escreveu um valor
    e declarou dúvida sobre ele — vale mesmo com a linha preenchida).
    """
    sinais: dict[str, str] = {}
    for frase in RE_FRASE.split(observacoes or ""):
        codigos: list[str] = []
        for oracao in RE_ORACAO.split(frase):
            # Oração sem código herda os da anterior, dentro da mesma frase.
            codigos = RE_CODIGO_CITADO.findall(oracao) or codigos
            classificacao = _intencao(oracao)
            if not codigos or classificacao is None:
                continue
            for codigo in codigos:
                # Uma frase que declara ilegibilidade não é apagada por outra
                # mais frouxa depois: fica o diagnóstico mais grave.
                if _GRAVIDADE[classificacao] >= _GRAVIDADE.get(sinais.get(codigo, ""), 0):
                    sinais[codigo] = classificacao
    return sinais


def codigos_citados(observacoes: str) -> set[str]:
    """Só os códigos que o modelo declarou ilegíveis. Atalho para os testes."""
    return {c for c, v in sinais_da_observacao(observacoes).items() if v == "ilegivel"}


def _sinal_da_linha(celulas: list[str], sinais: dict[str, str]) -> str | None:
    """
    O que a observação declarou sobre ESTA linha, ou None.

    O código nem sempre está sozinho na primeira coluna: há planilha com uma
    coluna de item vazia antes dele, a observação pode citar o código CPOS da
    segunda coluna, e há linha em que ele vem colado na descrição
    ('18.6.35 1/2"'). Fica o sinal mais grave entre os que casarem.
    """
    achados = [
        classificacao
        for celula in (str(c).strip() for c in celulas)
        for codigo, classificacao in sinais.items()
        if celula == codigo or celula.startswith(codigo + " ")
    ]
    return max(achados, key=_GRAVIDADE.__getitem__, default=None)


def classificar_lacuna(
    celulas: list[str], confianca: float, sinais: dict[str, str] | set[str]
) -> str:
    """
    Distingue "não consegui ler" de "está vazio mesmo". Quatro estados:

      ok        — linha completa, nada a fazer;
      vazio     — célula vazia sem sinal de problema. É o cabeçalho de seção
                  ("1 | SERVIÇOS TECNICOS | | "), que não tem quantidade por
                  natureza, ou uma linha que o modelo declarou vazia no original;
      ilegivel  — o modelo nomeou ESTA linha como ilegível. O valor existe no
                  papel e não foi capturado: é o que vale preencher à mão;
      suspeita  — há carimbo sobre a região, ou a página inteira veio abaixo do
                  limiar de confiança sem identificar quais linhas. Precisa de
                  olho humano, mas não se sabe se há valor a recuperar. Também
                  é o status da linha PREENCHIDA cujo valor o modelo declarou
                  ter inferido ou lido com dúvida.

    Sem essa distinção um SUM(quantidade) ignora as lacunas e devolve um total
    menor que o real, sem erro nenhum — número errado com cara de certo, que é
    exatamente o que este projeto existe para evitar.

    `sinais` vem de `sinais_da_observacao()`. Um `set` também é aceito, e aí todo
    código nele conta como ilegível — é a forma antiga, mantida para os testes.
    """
    if isinstance(sinais, set):
        sinais = dict.fromkeys(sinais, "ilegivel")

    declarado = _sinal_da_linha(celulas, sinais)

    if all(str(c).strip() for c in celulas):
        # Linha completa só deixa de ser "ok" quando o modelo duvidou do valor
        # que ele mesmo escreveu. Carimbo por perto não basta: ele leu.
        return "suspeita" if declarado == "incerta" else "ok"

    if declarado == "incerta":
        return "suspeita"
    if declarado:
        return declarado
    if sinais:
        # O modelo falou das linhas afetadas, e esta não está entre elas: a
        # lacuna é estrutural. Assumir o contrário marcaria todo cabeçalho de
        # seção da página para revisão — na página 5 do BUTANTAN seriam 60
        # linhas para conferir no lugar de 6.
        # A aposta é que a enumeração do modelo é completa; se um dia se provar
        # que não é, o caminho é o inverso (marcar tudo e filtrar depois).
        return "vazio"
    if confianca < config.LIMIAR_CONFIANCA_REVISAO:
        return "suspeita"
    return "vazio"


def extrair_linhas_tabela(
    blocos: list[Bloco], doc_id: str, paginas: list[dict] | None = None
) -> list[dict]:
    """
    Uma planilha de quantitativos precisa de SQL, não de busca vetorial.
    "Quanto de piso vinílico já fornecemos no total?" é um SUM, e RAG não soma.
    Estas linhas vão para `itens_planilha` no Supabase, em paralelo aos chunks —
    o agente decide entre buscar (vetor) e consultar (SQL).

    `paginas` são as páginas do JSON de extração. Delas vêm a confiança e a
    observação que permitem marcar a lacuna deixada por carimbo. Sem elas todas
    as linhas entram como se a página fosse confiável — é o comportamento
    antigo, mantido para os testes que não simulam extração.
    """
    qualidade: dict[int, tuple[float, str]] = {}
    for pag in paginas or []:
        qualidade[int(pag.get("numero", 0))] = (
            float(pag.get("confianca", 1.0)),
            pag.get("observacoes") or "",
        )

    itens: list[dict] = []

    for bloco in blocos:
        if bloco.tipo != "tabela":
            continue

        # Cada linha carrega a sua própria página. Numa planilha que atravessa
        # dezenas de páginas, usar `bloco.pag_ini` para todas mandaria o leitor
        # para a página errada ao clicar na fonte da citação.
        paginas_bloco = bloco.paginas_linhas or [bloco.pag_ini] * len(bloco.linhas)
        pares = [
            (ln, pag)
            for ln, pag in zip(bloco.linhas, paginas_bloco)
            if ln.strip().startswith("|")
        ]
        linhas = [ln for ln, _ in pares]
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
            pagina = pares[i][1]
            confianca, observacoes = qualidade.get(pagina, (1.0, ""))
            status = classificar_lacuna(celulas, confianca, sinais_da_observacao(observacoes))
            item = {
                "documento_id": doc_id,
                "pagina": pagina,
                "secao": " > ".join(bloco.caminho),
                "celulas": celulas,
                "status": status,
                "confianca": confianca,
            }
            # A observação só acompanha a linha que tem problema: ela é a mesma
            # para a página inteira, e repeti-la nas 28 linhas de uma planilha
            # completa só engordaria a tabela sem dizer nada.
            if status in ("ilegivel", "suspeita"):
                item["observacoes"] = observacoes
            itens.append(item)
    return itens


# --------------------------------------------------------------------------
# 6. Orquestração
# --------------------------------------------------------------------------


def _fundir_residuos(chunks: list[Chunk]) -> list[Chunk]:
    """Funde chunks curtos com o anterior.

    Duas regras:
      - curto (< MIN_CHARS) do mesmo tipo e mesma seção: funde, como sempre;
      - RESÍDUO (curto e sem nenhuma palavra, ver `_e_residuo`): funde com o
        anterior mesmo com seção diferente. É sobra numérica de tabela/lista
        ("50 
m 
42.5") e sozinho não tem sinal nem para o embedding — o
        indexador descarta, e o número some do acervo. Sem anterior, descarta.
    """
    fundidos: list[Chunk] = []
    for c in chunks:
        residuo = _e_residuo(c.texto_puro)
        if residuo and not fundidos:
            continue
        pode_fundir = fundidos and (
            residuo
            or (
                c.n_chars < config.MIN_CHARS
                and fundidos[-1].tipo == c.tipo
                and fundidos[-1].caminho_secao == c.caminho_secao
            )
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


def titulo_padrao(doc: dict) -> str:
    """Título derivado do nome do arquivo — só o último recurso."""
    from pathlib import Path

    return Path(doc["arquivo"]).stem.replace("_", " ")


def chunkar_documento(doc: dict, titulo: str | None = None) -> tuple[list[Chunk], list[dict]]:
    """
    Recebe o dict do JSON de extração. Retorna (chunks, itens_de_planilha).

    Separado do I/O para os testes poderem exercitar a lógica com um dict
    sintético, sem tocar em disco.

    O título vai para o cabeçalho contextual de CADA chunk (é o que aparece
    na citação). Precedência: `titulo` explícito > `doc["titulo"]` > nome do
    arquivo. O nome do arquivo é só fallback: em 28/09 os PDFs do Drive
    vieram com nome trocado em relação ao conteúdo (4 de 4 conferidos).
    """
    doc_titulo = (titulo or doc.get("titulo") or "").strip() or titulo_padrao(doc)
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

    return _fundir_residuos(chunks), extrair_linhas_tabela(blocos, doc_id, doc["paginas"])
