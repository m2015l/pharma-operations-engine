"""
triagem.py — Metadados de CAT/atestado extraídos do CONTEÚDO, sem LLM.

Motivo (diário, 28/09): os PDFs do Drive vieram com o nome de arquivo trocado em
relação ao conteúdo (4 de 4 conferidos). O pipeline usava o nome do arquivo como
título. Este módulo lê o texto nativo do PDF (camada de texto que já vem no
arquivo — muitas vezes um OCR antigo, ruidoso) e extrai, só com regex:

    tipo, nº da CAT, contratante (+ CNPJ), executante (+ CNPJ), responsável
    técnico, objeto, local, período, título sugerido

e confronta órgão/nº da CAT do NOME do arquivo com os do CONTEÚDO.

Tudo aqui é determinístico e grátis. Nenhuma chamada paga, nenhum OCR/VLM:
página sem texto nativo útil é só marcada como "precisa OCR".

As regex rodam sobre uma versão "dobrada" do texto (maiúsculas, sem acento, com o
MESMO comprimento do original) e os valores são recortados do texto original —
assim o casamento tolera acento/caixa e o valor devolvido mantém a grafia real.

Confiança por campo:
    alta           rótulo estruturado encontrado ("Contratante: X", "Nº 2620...")
    media          inferido (dicionário de órgãos, contagem, texto do atestado)
    nao_encontrado nada casou — conferir no PDF
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field

ALTA, MEDIA, NAO = "alta", "media", "nao_encontrado"

# --------------------------------------------------------------------------
# Normalização
# --------------------------------------------------------------------------

_CONTROLE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\u200b\\ufeff]")


def limpar_texto(texto: str) -> str:
    """Remove caracteres de controle (há PDF com NUL no meio do texto)."""
    return _CONTROLE.sub("", texto or "")


def dobrar(texto: str) -> str:
    """Maiúsculas sem acento, preservando o comprimento (1 char -> 1 char)."""
    saida = []
    for ch in texto:
        base = unicodedata.normalize("NFKD", ch)[:1] or ch
        saida.append(base.upper()[:1] or base)
    return "".join(saida)


_LIDER = re.compile(r"(?:\s*[.·…]\s*){3,}")  # "........" e ". . . ." de formulário
_ESPACOS = re.compile(r"[ \t]+")


def limpar_valor(valor: str, max_len: int = 240) -> str:
    """Tira pontilhado de formulário, espaço duplicado e lixo nas pontas."""
    v = _LIDER.sub(" ", valor)
    v = _ESPACOS.sub(" ", v.replace("\n", " ")).strip(" .:;,-–—_'\"|*•")
    if len(v) > max_len:
        corte = v.rfind(" ", 0, max_len)
        v = v[: corte if corte > 40 else max_len].rstrip(" ,;") + " …"
    return v


# --------------------------------------------------------------------------
# Dicionários de entidades
# --------------------------------------------------------------------------

# Órgãos/contratantes que aparecem no acervo (nomes de arquivo + conteúdo).
# Regex sobre texto DOBRADO. A ordem importa: o primeiro que casar no trecho do
# contratante vence, então os específicos vêm antes dos genéricos.
ORGAOS: dict[str, list[str]] = {
    "Fundação de Apoio à Pesquisa em Saúde": [
        r"\bFAPS\b",
        r"DESENVOLVIMENTO\s+CIENTIFICO\s+E\s+TECNOLOGICO\s+EM\s+SAUDE",
    ],
    "Fundação Nacional de Saúde Pública": [
        r"\bFNSP\b",
        r"FUNDACAO\s+NACIONAL\s+DE\s+SAUDE\s+PUBLICA",
        r"IMUNOBIOLOGICOS",
    ],
    "Instituto BioPharma": [
        r"BIOPHARMA\b",
        r"(?:INSTITUTO|FUNDACAO)\s*BIOPH\w{2,6}",
    ],
    "Centro Nacional de Biotecnologia": [
        r"\bCNBIO\b",
        r"CENTRO\s+NACIONAL\s+DE\s+BIOTECNOLOGIA",
    ],
    "Complexo Farmacêutico Industrial": [r"COMPLEXO\s+FARMACEUTICO"],
    "Laboratório Químico Central": [r"LABORATORIO\s+QUIMICO\s+CENTRAL", r"\bLQC\b"],
    "Instituto de Imunobiológicos": [r"INSTITUTO\s+DE\s+IMUNOBIOLOGICOS"],
    "Laboratório Farmacêutico Estadual": [r"\bLFE\b", r"FARMACEUTICO\s+ESTADUAL"],
    "Centro de Tecnologia Industrial": [
        r"\bCTI\b",
        r"CENTRO\s+DE\s+TECNOLOGIA\s+INDUSTRIAL",
    ],
    "Hospital Universitário Central": [
        r"HOSPITAL\s+UNIVERSITARIO\s+CENTRAL",
        r"\bHUC\b",
    ],
    "Unidade Técnica Especial": [r"^UNIDADE\s+TECNICA", r"UNIDADE\s+TECNICA\s+ESPECIAL"],
}

# Nomes de arquivo usam apelidos que não são o contratante.
ORGAOS_SO_NO_NOME = {"Unidade Técnica Especial"}

EMPRESA_PRINCIPAL_CNPJ = os.getenv("EMPRESA_PRINCIPAL_CNPJ", "11.222.333/0001-81")
EMPRESA_COLIGADA_CNPJ = os.getenv("EMPRESA_COLIGADA_CNPJ", "22.333.444/0001-92")
EMPRESA_PRINCIPAL_NOME = os.getenv("EMPRESA_PRINCIPAL_NOME", "Pharma Operations Platform")
EMPRESA_COLIGADA_NOME = os.getenv("EMPRESA_COLIGADA_NOME", "Enterprise Vendor Hub")

_RX_COLIGADA = re.compile(
    os.getenv(
        "EMPRESA_COLIGADA_REGEX",
        r"ENTERPRISE\s+VENDOR|VENDOR\s+HUB\s+ENGENHARIA|COLIGADA\s+ENGENHARIA",
    )
)
_RX_PRINCIPAL = re.compile(
    os.getenv(
        "EMPRESA_PRINCIPAL_REGEX",
        r"PHARMA\s+OPERATIONS|PHARMA\s+ENGENHARIA",
    )
)
_RX_CONSORCIO = re.compile(r"\bCONSORCIO\b")


# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------


@dataclass
class Campo:
    valor: str | None = None
    confianca: str = NAO
    fonte: str = ""  # qual regra achou — ajuda a depurar sem abrir o PDF

    def como_dict(self) -> dict:
        return {"valor": self.valor, "confianca": self.confianca, "fonte": self.fonte}


def _achou(valor: str | None, confianca: str, fonte: str) -> Campo:
    if not valor:
        return Campo()
    return Campo(valor, confianca, fonte)


@dataclass
class Metadados:
    tipo: Campo = field(default_factory=Campo)
    numero_cat: Campo = field(default_factory=Campo)
    contratante: Campo = field(default_factory=Campo)
    orgao: Campo = field(default_factory=Campo)  # contratante canônico (dicionário)
    contratante_cnpj: Campo = field(default_factory=Campo)
    executante: Campo = field(default_factory=Campo)
    executante_grupo: Campo = field(default_factory=Campo)  # Enterprise Vendor Hub | Pharma Operations | ...
    executante_cnpj: Campo = field(default_factory=Campo)
    responsavel_tecnico: Campo = field(default_factory=Campo)
    objeto: Campo = field(default_factory=Campo)
    local: Campo = field(default_factory=Campo)
    periodo: Campo = field(default_factory=Campo)
    titulo_sugerido: Campo = field(default_factory=Campo)

    def como_dict(self) -> dict:
        return {k: v.como_dict() for k, v in self.__dict__.items()}


# --------------------------------------------------------------------------
# Utilitários de casamento (dobrado -> original)
# --------------------------------------------------------------------------


class Texto:
    """Par (original, dobrado) com o mesmo comprimento."""

    def __init__(self, original: str):
        self.o = limpar_texto(original)
        self.d = dobrar(self.o)

    def busca(self, padrao: str, inicio: int = 0, flags: int = re.MULTILINE):
        return re.compile(padrao, flags).search(self.d, inicio)

    def todos(self, padrao: str, flags: int = re.MULTILINE):
        return list(re.compile(padrao, flags).finditer(self.d))

    def fatia(self, a: int, b: int) -> str:
        return self.o[a:b]


def _linha_apos(t: Texto, fim_rotulo: int, max_linhas: int = 2) -> tuple[str, int]:
    """
    Valor depois de um rótulo: resto da linha; se vazio (só pontilhado/ruído),
    a próxima linha não vazia. Devolve (valor_original, posição_final).
    """
    pos = fim_rotulo
    for _ in range(max_linhas):
        fim_linha = t.d.find("\n", pos)
        fim_linha = len(t.d) if fim_linha < 0 else fim_linha
        bruto = t.fatia(pos, fim_linha)
        if len(re.sub(r"[\W_]", "", bruto)) >= 3:
            return bruto, fim_linha
        pos = fim_linha + 1
        if pos >= len(t.d):
            break
    return "", pos


def _cortar_em(valor: str, rotulos: str) -> str:
    """Corta o valor no primeiro rótulo seguinte da mesma linha (ex. 'CNPJ')."""
    m = re.search(rotulos, dobrar(valor))
    return valor[: m.start()] if m else valor


def canonizar_orgao(texto: str, incluir_so_nome: bool = False) -> list[str]:
    """Órgãos do dicionário que casam no texto (na ordem do dicionário)."""
    d = dobrar(texto)
    achados = []
    for nome, padroes in ORGAOS.items():
        if nome in ORGAOS_SO_NO_NOME and not incluir_so_nome:
            continue
        if any(re.search(p, d, re.MULTILINE) for p in padroes):
            achados.append(nome)
    return achados


# --------------------------------------------------------------------------
# Extratores por campo
# --------------------------------------------------------------------------

_RX_CNPJ = r"(\d{2}\s?\.?\s?\d{3}\s?\.?\s?\d{3}\s?[/1]?\s?\d{4}\s?-?\s?\d{2})"


def formatar_cnpj(bruto: str) -> str | None:
    dig = re.sub(r"\D", "", bruto)
    if len(dig) == 15 and dig[8] == "1":  # "/" lido como "1" pelo OCR antigo
        dig = dig[:8] + dig[9:]
    if len(dig) != 14:
        return None
    return f"{dig[:2]}.{dig[2:5]}.{dig[5:8]}/{dig[8:12]}-{dig[12:]}"


def _cnpj_perto(t: Texto, inicio: int, janela: int = 260) -> str | None:
    m = t.busca(r"CNPJ\W{0,12}" + _RX_CNPJ, inicio)
    if m and m.start() - inicio <= janela:
        return formatar_cnpj(m.group(1))
    return None


def extrair_tipo(t: Texto) -> Campo:
    cat = t.busca(
        r"AC\w?RVO\s+T\w{0,2}[CT]\w{0,4}|CERTID\w{1,3}\s+D\w?\s+AC\w?RVO|CAT\s+COM\s+REGISTRO"
    )
    atestado = t.busca(r"ATESTADO\s+DE\s+(?:CAPACIDADE|EXECUCAO)|\bATESTAMOS\b")
    if cat and atestado:
        return Campo("CAT com atestado", ALTA, "cabeçalho CAT + texto de atestado")
    if cat:
        return Campo("CAT", ALTA, "cabeçalho de certidão de acervo técnico")
    if atestado:
        return Campo("atestado de capacidade técnica", ALTA, "texto de atestado")
    return Campo("outro", MEDIA, "nenhum cabeçalho de CAT/atestado")


def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s.replace("O", "0").replace("o", "0"))


def extrair_numero_cat(t: Texto) -> Campo:
    # 1. Rodapé do CREA-SP novo: "Certidão de Acervo Tecnico No.2620000000001"
    m = t.busca(r"CERTIDAO\s+DE\s+ACERVO\s+TECNICO\s*-?\s*N\s?[O0º°]\.?\s*([\dO ]{10,16}\d)")
    if m:
        dig = _so_digitos(m.group(1))
        if 10 <= len(dig) <= 14:
            return Campo(dig, ALTA, "rodapé 'Certidão de Acervo Técnico No.'")
    # 2. CAU: "CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO\nNº 0000000100200"
    m = t.busca(r"ACERVO\s+TECNICO\s+COM\s+ATESTADO\s*N\s?[º°O]\.?\s*(\d{6,13})")
    if m:
        return Campo(m.group(1).lstrip("0") or "0", ALTA, "CAU 'com atestado Nº'")
    # 3. "nº/ano": CREA-RJ ("CERTIDÃO DE ACERVO TÉCNICO Nº 10001/2020",
    #    "CERTIDAO Mo. 1000/2010" — OCR lê N como M) e carimbo do CAU
    #    ("Certidão nº 100200/2020").
    m = t.busca(
        r"CERTIDAO\s+(?:DE\s+ACERVO\s+TECNICO\s+)?[NM][º°O]?\.?\s*:?\s*"
        r"(\d{3,8})\s*/\s*((?:19|20)\d{2})\b"
    )
    if m:
        return Campo(f"{m.group(1)}/{m.group(2)}", ALTA, "'Certidão nº X/AAAA'")
    # 4. CREA-SP antigo: "CERTIDAO N°: SJC-00001"
    m = t.busca(r"CERTID\w{1,3}\s*N\W{0,3}\s*:?\s*([A-Z]{3})\s*-\s*(\d{4,6})\b")
    if m:
        return Campo(f"{m.group(1)}-{m.group(2)}", ALTA, "CREA-SP antigo 'CERTIDÃO Nº'")
    # 5. CREA-RJ antigo: "CERTIDAO No. 100012010"
    m = t.busca(r"CERTIDAO\s+N[O0º°]\.?\s*:?\s*(\d{6,12})\b")
    if m:
        return Campo(m.group(1), ALTA, "CREA-RJ 'CERTIDÃO No.'")
    # 6. Cabeçalho do CREA-SP novo, número solto logo abaixo (OCR troca 0 por O)
    m = t.busca(r"CAT\s+COM\s+REGISTRO\s+DE\s+ATESTADO")
    if m:
        m2 = t.busca(r"\b[I1l]?(2\s?6\s?2\s?[O0](?:\s?[\dO]){9})\b", m.end())
        if m2 and m2.start() - m.end() < 250:
            return Campo(_so_digitos(m2.group(1)), MEDIA, "número solto sob o cabeçalho CAT")
    return Campo()


_ROTULOS_FIM_CONTRATANTE = r"CNPJ|CPF|\bRUA\b|ENDERECO|TIPO\s+D"


def extrair_contratante(t: Texto) -> tuple[Campo, Campo, Campo]:
    """Devolve (contratante bruto, órgão canônico, CNPJ do contratante)."""
    bruto, fonte, conf, pos = "", "", NAO, None
    for rotulo, nome_regra in (
        (r"^\W{0,4}CONTRAT\w{0,4}N\w{0,2}T\w{0,2}\W{0,3}\s*:?", "rótulo 'Contratante'"),
        (r"^\W{0,4}PROPRIETARIO\W{0,3}\s*:", "rótulo 'Proprietário'"),
    ):
        for m in t.todos(rotulo):
            valor, _ = _linha_apos(t, m.end(), max_linhas=2)
            valor = limpar_valor(_cortar_em(valor, _ROTULOS_FIM_CONTRATANTE), 160)
            # Layout antigo do CREA-SP: rótulos numa coluna, valores depois.
            # O "valor" vira o próximo rótulo — descarta.
            if valor and not re.match(
                r"CON\s?T\w{0,4}TAD|CREA|CPF|CNPJ|RESPONSA|TIPO", dobrar(valor)
            ):
                bruto, fonte, conf, pos = valor, nome_regra, ALTA, m.start()
                break
        if bruto:
            break

    orgaos = canonizar_orgao(bruto) if bruto else []
    if orgaos:
        orgao = Campo(orgaos[0], conf, f"dicionário sobre {fonte}")
    else:
        # Fallback: órgão do dicionário mais citado no texto do documento.
        contagem: dict[str, int] = {}
        for nome, padroes in ORGAOS.items():
            if nome in ORGAOS_SO_NO_NOME:
                continue
            n = sum(len(t.todos(p)) for p in padroes if not p.startswith("^"))
            if n:
                contagem[nome] = n
        if contagem:
            melhor = max(contagem, key=contagem.get)
            orgao = Campo(melhor, MEDIA, f"órgão mais citado no texto ({contagem[melhor]}x)")
        else:
            orgao = Campo()

    cnpj = _cnpj_perto(t, pos) if pos is not None else None
    return (
        _achou(bruto, conf, fonte),
        orgao,
        _achou(cnpj, ALTA if cnpj else NAO, "CNPJ na linha do contratante"),
    )


def classificar_executante(texto: str) -> str | None:
    d = dobrar(texto)
    coligada, principal = bool(_RX_COLIGADA.search(d)), bool(_RX_PRINCIPAL.search(d))
    if _RX_CONSORCIO.search(d) and (coligada or principal):
        return (
            "consórcio com Enterprise Vendor Hub"
            if coligada
            else "consórcio com Pharma Operations"
        )
    if coligada and principal:
        return "Enterprise Vendor Hub e Pharma Operations"
    if coligada:
        return "Enterprise Vendor Hub"
    if principal:
        return "Pharma Operations"
    return None


def extrair_executante(t: Texto) -> tuple[Campo, Campo, Campo]:
    """Devolve (executante bruto, grupo Enterprise Vendor Hub/Pharma Operations/outra, CNPJ)."""
    bruto, fonte, conf, pos = "", "", NAO, None
    regras = (
        (r"(?:EMPRESA\s+)?CONTRATADA\W{0,3}\s*:?", "rótulo 'Contratada'"),
        (r"EXECUTANTE\W{0,3}\s*:?", "rótulo 'Executante'"),
    )
    for rotulo, nome_regra in regras:
        for m in t.todos(r"^\W{0,4}" + rotulo):
            valor, _ = _linha_apos(t, m.end(), max_linhas=2)
            valor = limpar_valor(_cortar_em(valor, r"CNPJ|REG\w*\s*[.:]|REGISTRO|CREA"), 120)
            if valor and not re.match(r"CREA|CNPJ|CONTRATANTE", dobrar(valor)):
                bruto, fonte, conf, pos = valor, nome_regra, ALTA, m.start()
                break
        if bruto:
            break

    if not bruto:
        # Atestado: "... que a empresa X, com sede ..."
        m = t.busca(
            r"(?:QUE\s+A\s+EMPRESA|QUE\s+A|QUE\s+O)\s+(.{5,200}?)"
            r"(?:,?\s+CO\w{0,2}\s+SEDE|,?\s+SEDIAD|,?\s+INSCRIT|,\s*CNPJ)",
            flags=re.DOTALL,
        )
        if m:
            bruto = limpar_valor(t.fatia(m.start(1), m.end(1)), 160)
            bruto = re.sub(
                r"^E\w{2,4}SA\s+", "", bruto, flags=re.IGNORECASE
            )  # "empresa" com OCR ruim
            fonte, conf, pos = "texto do atestado ('que a empresa X, com sede')", MEDIA, m.start()

    lt = re.search(r"L\s?[TI]\s?D\s?A\.?", dobrar(bruto))
    if lt:  # a razão social termina em LTDA; o resto é endereço
        bruto = bruto[: lt.end()]
    contexto = bruto
    if bruto and _RX_CONSORCIO.search(dobrar(bruto)) and pos is not None:
        # "o Consórcio X, ... composto pela ... e pela coligada ..." — as
        # consorciadas vêm depois do nome do consórcio.
        contexto = t.fatia(pos, pos + 600)
    grupo = classificar_executante(contexto) if bruto else None
    fonte_grupo = f"classificação sobre {fonte}" if grupo else ""
    if bruto and not grupo:
        grupo, fonte_grupo = "outra", f"{fonte} sem empresa principal/coligada"
    if not grupo:
        # Sem rótulo: CNPJ conhecido em qualquer lugar do texto.
        cnpjs_texto = {formatar_cnpj(c) for c in re.findall(_RX_CNPJ, t.d)}
        tem_coligada = EMPRESA_COLIGADA_CNPJ in cnpjs_texto
        tem_principal = EMPRESA_PRINCIPAL_CNPJ in cnpjs_texto
        if tem_coligada != tem_principal:
            grupo = "Enterprise Vendor Hub" if tem_coligada else "Pharma Operations"
            fonte_grupo = "CNPJ conhecido no texto"
        else:
            grupo = classificar_executante(t.o)
            fonte_grupo = "menção no texto" if grupo else ""
    conf_grupo = conf if conf == ALTA and fonte_grupo.startswith("classificação") else MEDIA

    cnpj = _cnpj_perto(t, pos, 400) if pos is not None else None
    return (
        _achou(bruto, conf, fonte),
        _achou(grupo, conf_grupo, fonte_grupo),
        _achou(cnpj, ALTA if cnpj else NAO, "CNPJ perto da executante"),
    )


_RX_NOME = re.compile(r"[A-Za-zÀ-ÿ!'´`]{2,}(?:\s+[A-Za-zÀ-ÿ!'´`]{1,}){1,6}")


_NAO_NOME = re.compile(
    r"\b(?:REGISTRO|TITULO|CREA|RNP|ABAI\w*|RELACIONAD\w*|ENG\w*HEIR\w*|PROJETO|EXECU\w*|"
    r"RESPONSAV\w*|TECNIC\w*|ELETRICISTA|MECANIC\w*|CIVIL|ARQUITET\w*|AREA)\b"
)


def _limpar_nome(bruto: str) -> str | None:
    bruto = _cortar_em(bruto, r"\bREFERENT|\bCREA|\bREGISTRO")
    if ":" in bruto:  # "Engenheiro Industrial-Mecânico: Nome Sobrenome"
        bruto = bruto.rsplit(":", 1)[1]
    bruto = re.sub(
        r"^\W*(?:ENG\.?|ENGENHEIR[OA]\W+[\w-]*:?|ARQ\.?)\s*", "", bruto, flags=re.IGNORECASE
    )
    m = _RX_NOME.search(bruto)
    if not m:
        return None
    nome = m.group(0).replace("!", "I").strip()
    palavras = nome.split()
    if len(palavras) < 2 or _NAO_NOME.search(dobrar(nome)):
        return None
    return " ".join(p.capitalize() if len(p) > 2 else p.lower() for p in palavras)


def extrair_responsavel(t: Texto) -> Campo:
    for m in t.todos(r"^\W{0,4}PRO[FJ]\w{0,2}SS?I\w{0,3}N\w{0,2}L\s*:?"):
        valor, _ = _linha_apos(t, m.end(), max_linhas=2)
        nome = _limpar_nome(valor)
        if nome:
            return Campo(nome, ALTA, "rótulo 'Profissional'")
    m = t.busca(r"RESPONSAVE(?:L|IS)\s+TECNICOS?\s*(?:ABAIXO\s+RELACIONADOS?)?\s*:?")
    if m:
        valor, _ = _linha_apos(t, m.end(), max_linhas=3)
        nome = _limpar_nome(re.sub(r"^\W+", "", valor))
        if nome:
            return Campo(nome, MEDIA, "texto do atestado ('responsável técnico')")
    m = t.busca(r"ACERVO\s+TECNICO\s+DO\s+PROFISSIONAL\s+([A-Z ]{8,60}?)\s+REFERENTE")
    if m:
        nome = _limpar_nome(t.fatia(m.start(1), m.end(1)))
        if nome:
            return Campo(nome, ALTA, "'Acervo Técnico do profissional X'")
    return Campo()


_FIM_OBJETO = (
    r"INFORMA\w{0,3}\s*(?:ES\s*)?COMPLEMENTAR|ENDERECO\s+DA\s+OBRA|QUAN\w{1,4}FIC|"
    r"^\W{0,3}LOCAL\s+D|NO\.?\s+CONTRATO|DADOS\s+DO\s+CONTRATO|EMPRESA\s+CONTRATADA|"
    r"CARACTERIZACAO|VALOR\s+CONTRATUAL|CUMPRINDO|CONFORME\s+(?:DESCRI|DETALHE|EXECU)"
)


def _trecho_ate(t: Texto, inicio: int, fim_padrao: str, max_chars: int = 500) -> str:
    m = t.busca(fim_padrao, inicio)
    fim = m.start() if m and m.start() - inicio <= max_chars * 2 else inicio + max_chars
    return t.fatia(inicio, fim)


def extrair_objeto(t: Texto) -> Campo:
    regras = (
        (r"^\W{0,3}DESCRI\w{2,4}\s*:", "CAU 'Descrição'", ALTA),
        (r"ATIVIDADE\s+TECNICA\s+REALIZADA", "CAU 'Atividade técnica realizada'", ALTA),
        (r"OBS\s*:", "CREA 'Obs:' da atividade técnica", ALTA),
        (r"^\W{0,3}A\w{1,3}V\w{0,2}DADE\s+T\w{1,3}CNICA\s*:", "CREA 'Atividade Técnica:'", ALTA),
        (r"INF\w{1,5}ACAO\s*COMPLEMENTAR\W*\n", "CREA-RJ 'Informação complementar'", ALTA),
        (r"^\W{0,3}OBRA\s*:", "atestado 'OBRA:'", MEDIA),
        (r"RESPONSAVEL\W{0,2}\s*T\w{1,3}CNICO\W{0,2}\s*P\w{0,2}R\s", "CREA-SP antigo", MEDIA),
        (r"EXECUTOU\b|PRESTOU\b|OS\s+SERVICOS\s+DE\b", "texto do atestado", MEDIA),
    )
    for padrao, fonte, conf in regras:
        m = t.busca(padrao)
        if not m:
            continue
        inicio = m.end()
        if "EXECUTOU" in padrao:
            # Pula o preâmbulo "executou no período X, pelo valor Y," até o serviço.
            ms = t.busca(r"(?:OS\s+)?SERVICOS\s+D|AS\s+OBRAS\s+D|\bOBRAS?\s+DE\b|PROJETO", m.end())
            inicio = ms.start() if ms and ms.start() - m.end() < 400 else m.start()
        trecho = limpar_valor(_trecho_ate(t, inicio, _FIM_OBJETO), 300)
        trecho = re.sub(r"\bn\w{0,2}ca\(s\)\s*Rea\w*\(\w*\)?", "", trecho).strip(" -–")
        if len(re.sub(r"\W", "", trecho)) >= 20:
            return Campo(trecho, conf, fonte)
    return Campo()


def extrair_local(t: Texto) -> Campo:
    endereco, fonte = "", ""
    m = t.busca(r"ENDERE\w{1,3}\s*D\w\s+OBRA\W{0,2}\s*(?:SERVICO|SERVICO)?\w*\s*:?")
    if m:
        endereco = t.fatia(m.end(), t.d.find("\n", m.end()) if "\n" in t.d[m.end() :] else None)
        fonte = "rótulo 'Endereço da obra'"
    if not endereco.strip():
        m = t.busca(r"^\W{0,3}LOCAL\s+D\w{1,3}\s+OB\w{1,4}\W{0,3}\w*\s*")
        if m:
            endereco, _ = _linha_apos(t, m.end(), 1)
            fonte = "rótulo 'Local da obra'"
    endereco = limpar_valor(_cortar_em(endereco, r"COMPLEMENTO|BAIRRO|CEP"), 100)

    cidade = ""
    inicio = m.end() if m else 0
    # Cidade e UF podem estar na mesma linha (CREA) ou em linhas diferentes (CAU).
    padrao_cidade = r"^\W{0,3}CIDADE\W{0,3}\s*:?[ \t]*([A-Z][^\n]{2,60})"
    # Procura depois do endereço da obra (a cidade da OBRA, não a do contratante);
    # no CAU ela pode vir antes do rótulo do endereço.
    mc = t.busca(padrao_cidade, inicio) or t.busca(padrao_cidade)
    if mc:
        nome_cidade = limpar_valor(_cortar_em(t.fatia(mc.start(1), mc.end(1)), r"U\s?F\b"), 40)
        uf = t.busca(r"\bU\s?F\W{0,2}\s*:?\s*([A-Z]{2})\b", mc.start(1))
        uf_txt = f"/{uf.group(1)}" if uf and uf.start() - mc.start(1) < 150 else ""
        # Layout antigo do CREA-SP: rótulos numa coluna — o "valor" é outro rótulo.
        eh_rotulo = re.match(r"VALOR|PER\w{0,2}ODO|ESTADO|CONTRAT|V\w?LIDA", dobrar(nome_cidade))
        if len(re.sub(r"\W", "", nome_cidade)) >= 3 and not eh_rotulo:
            cidade = f"{nome_cidade}{uf_txt}"
    valor = " — ".join(p for p in (endereco, cidade) if p)
    if not valor:
        return Campo()
    return Campo(valor, ALTA if endereco and cidade else MEDIA, fonte or "cidade/UF")


_DATA = r"(\d{2})\s?[./1l]\s?(\d{2})\s?[./1l]\s?((?:19|20)\d{2})"
_MES = r"(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\w*\s*/\s*((?:19|20)\d{2})"


def _data(m, a: int = 1) -> str | None:
    dia, mes, ano = int(m.group(a)), int(m.group(a + 1)), m.group(a + 2)
    if 1 <= dia <= 31 and 1 <= mes <= 12:
        return f"{dia:02d}/{mes:02d}/{ano}"
    return None


def extrair_periodo(t: Texto) -> Campo:
    ini = t.busca(r"DATA\s+DE\s+IN\w{1,3}IO\s*:?\s*" + _DATA)
    fim = t.busca(
        r"(?:DATA\s+DE\s+FIM|CONCLUS\w{2}\s+EFE\w{2,4}A|CONCLUSAO\s+EM|DATA\s+DE\s+CONCLUSAO)"
        r"\s*:?\s*" + _DATA
    )
    if ini and fim and _data(ini) and _data(fim):
        return Campo(f"{_data(ini)} a {_data(fim)}", ALTA, "rótulos 'Data de início'/'Conclusão'")
    iso = t.busca(r"DATA\s+DE\s+TERMINO[\w ]{0,20}:\s*((?:19|20)\d{2})-(\d{2})-(\d{2})")
    if ini and _data(ini) and iso:
        fim_iso = f"{iso.group(3)}/{iso.group(2)}/{iso.group(1)}"
        return Campo(
            f"{_data(ini)} a {fim_iso}", ALTA, "rótulos 'Data de início'/'Data de término'"
        )
    m = t.busca(_DATA + r"\s*(?:A|ATE|À)\s*" + _DATA)
    if m and _data(m) and _data(m, 4):
        return Campo(f"{_data(m)} a {_data(m, 4)}", MEDIA, "intervalo 'dd/mm/aaaa a dd/mm/aaaa'")
    m = t.busca(_MES + r"\s*(?:A|ATE|À)\s*" + _MES)
    if m:
        return Campo(
            f"{m.group(1).lower()}/{m.group(2)} a {m.group(3).lower()}/{m.group(4)}",
            MEDIA,
            "intervalo 'mês/aaaa a mês/aaaa'",
        )
    if ini and _data(ini):
        return Campo(f"início {_data(ini)}", MEDIA, "só 'Data de início'")
    return Campo()


def _objeto_curto(objeto: str | None, max_len: int = 70) -> str:
    if not objeto:
        return ""
    o = re.sub(r"^\W*\d\)\s*", "", objeto)
    o = re.sub(r"\s+", " ", o).strip(" -–:")
    if len(o) <= max_len:
        return o
    corte = o.rfind(" ", 0, max_len)
    return o[: corte if corte > 20 else max_len].rstrip(" ,;.-") + "…"


def montar_titulo(md: Metadados) -> Campo:
    tipo = md.tipo.valor or "Documento"
    rotulo = (
        "CAT" if tipo.startswith("CAT") else ("Atestado" if "atestado" in tipo else "Documento")
    )
    partes = [f"{rotulo} {md.numero_cat.valor}" if md.numero_cat.valor else rotulo]
    quem = md.orgao.valor or md.contratante.valor
    if quem:
        partes.append(quem)
    obj = _objeto_curto(md.objeto.valor)
    if obj:
        partes.append(obj)
    titulo = " — ".join(partes)
    if md.executante_grupo.valor:
        titulo += f" (executante: {md.executante_grupo.valor})"
    confs = [md.numero_cat.confianca, md.orgao.confianca, md.objeto.confianca]
    conf = ALTA if all(c == ALTA for c in confs) else (MEDIA if quem else NAO)
    if len(partes) == 1:
        return Campo()
    return Campo(titulo, conf, "montado de nº CAT + órgão + objeto + executante")


def extrair_metadados(paginas: list[str]) -> Metadados:
    """Metadados de um documento a partir do texto nativo das páginas."""
    t = Texto("\n".join(paginas))
    md = Metadados()
    md.tipo = extrair_tipo(t)
    md.numero_cat = extrair_numero_cat(t)
    md.contratante, md.orgao, md.contratante_cnpj = extrair_contratante(t)
    md.executante, md.executante_grupo, md.executante_cnpj = extrair_executante(t)
    md.responsavel_tecnico = extrair_responsavel(t)
    md.objeto = extrair_objeto(t)
    md.local = extrair_local(t)
    md.periodo = extrair_periodo(t)
    md.titulo_sugerido = montar_titulo(md)
    return md


# --------------------------------------------------------------------------
# Nome do arquivo x conteúdo
# --------------------------------------------------------------------------


def analisar_nome(nome_arquivo: str) -> dict:
    """Órgãos e nº de CAT que o NOME do arquivo afirma ter."""
    stem = re.sub(r"\.[A-Za-z]{3,4}$", "", nome_arquivo).replace("_", " ")
    orgaos = canonizar_orgao(stem, incluir_so_nome=True)
    m = re.search(r"\bCAT\s+([A-Za-z]{3}-\d{3,6}|\d[\d-]*\d)", stem)
    return {"orgaos": orgaos, "numero_cat": m.group(1).upper() if m else None}


def numeros_batem(do_nome: str, do_conteudo: str) -> bool:
    """
    Compara nº de CAT do nome com o do conteúdo, tolerando formatação.

    'SJC-00001' == 'SJC-00001'; '0000000100200' == '100200';
    '1000-2010' == '1000/2010'; '100200' == '100200/2020' (ano só num lado);
    '1000-2010' ~ '100012010' (CREA-RJ antigo grava 'nº/ano' com dígito no
    meio: cada grupo do nome precisa aparecer, em ordem, no do conteúdo).
    """
    a, b = do_nome.upper().replace(" ", ""), do_conteudo.upper().replace(" ", "")
    pa, pb = re.match(r"[A-Z]*", a).group(0), re.match(r"[A-Z]*", b).group(0)
    if pa and pb and pa != pb:
        return False
    da, db = re.sub(r"\D", "", a).lstrip("0"), re.sub(r"\D", "", b).lstrip("0")
    if not da or not db:
        return False
    if da == db:
        return True
    grupos = [g.lstrip("0") for g in re.findall(r"\d+", a) if g.lstrip("0")]
    grupos_b = [g.lstrip("0") for g in re.findall(r"\d+", b) if g.lstrip("0")]
    if grupos and grupos_b and grupos[0] == grupos_b[0]:
        return len(grupos) < 2 or len(grupos_b) < 2 or grupos[1] == grupos_b[1]
    if len(grupos) < 2 or not db.startswith(grupos[0]):
        return False
    pos = 0
    for g in grupos:
        achou = db.find(g, pos)
        if achou < 0:
            return False
        pos = achou + len(g)
    return True


_FAMILIA_ORGAO = {
    "Fundação de Apoio à Pesquisa em Saúde": {"Fundação Nacional de Saúde Pública"},
    "Fundação Nacional de Saúde Pública": {"Fundação de Apoio à Pesquisa em Saúde"},
}


def confrontar_nome(nome_arquivo: str, md: Metadados) -> dict:
    """Veredito 'bate' | 'trocado' | 'inconclusivo' com os motivos."""
    nome = analisar_nome(nome_arquivo)
    motivos, divergencias, conferidos = [], 0, 0

    if nome["numero_cat"] and md.numero_cat.valor:
        conferidos += 1
        if numeros_batem(nome["numero_cat"], md.numero_cat.valor):
            motivos.append(f"nº CAT bate ({nome['numero_cat']})")
        else:
            divergencias += 1
            motivos.append(
                f"nº CAT: nome diz {nome['numero_cat']}, conteúdo diz {md.numero_cat.valor}"
            )

    orgaos_nome = [o for o in nome["orgaos"] if o not in ORGAOS_SO_NO_NOME]
    if orgaos_nome and md.orgao.valor:
        conferidos += 1
        # Fundação de apoio e órgão principal: tratar como compatíveis.
        compativeis = set(orgaos_nome) | {f for o in orgaos_nome for f in _FAMILIA_ORGAO.get(o, ())}
        if md.orgao.valor in compativeis:
            motivos.append(f"órgão bate ({md.orgao.valor})")
        else:
            divergencias += 1
            motivos.append(
                f"órgão: nome diz {'/'.join(orgaos_nome)}, conteúdo diz {md.orgao.valor}"
            )

    if not conferidos:
        veredito = "inconclusivo"
        motivos.append("nada comparável entre nome e conteúdo")
    elif divergencias:
        veredito = "trocado"
    else:
        veredito = "bate"
    return {
        "orgaos_no_nome": nome["orgaos"],
        "numero_cat_no_nome": nome["numero_cat"],
        "veredito": veredito,
        "motivos": motivos,
    }
