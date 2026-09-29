"""
classificacao.py — Classificação e sumarização de documentos do acervo via LLM
(escopo 1 do contrato; item 19 do PLANO_PROJETO).

Entrada: os CHUNKS já indexados de um documento (texto extraído, com página),
não o PDF. Saída: um JSON estruturado e VALIDADO EM CÓDIGO + um resumo curto.

Divisão de trabalho (mesma filosofia do resto do pipeline):
  - o LLM lê o texto ruidoso e preenche o formulário;
  - o código decide o que entra no banco: vocabulário fechado, página citada
    dentro do documento, trecho de evidência conferido contra o texto, e
    confronto com a triagem por regex (`solufarma.triagem`), que é grátis e
    determinística. Divergência não é descartada em silêncio: vira `avisos`.

Regra de ouro: campo que não está no texto é null. O prompt pede isso e o
código reforça — valor sem evidência localizável é marcado `verificado: false`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from solufarma import triagem

VERSAO_SCHEMA = 1

# --------------------------------------------------------------------------
# Vocabulário fechado
# --------------------------------------------------------------------------

TIPOS_DOCUMENTO = {
    "cat": "Certidão de Acervo Técnico (CREA/CAU), com ou sem atestado anexo",
    "atestado": "atestado de capacidade técnica emitido pelo contratante, sem CAT",
    "edital": "edital de licitação ou termo de referência",
    "ata": "ata de sessão, de registro de preços ou de julgamento",
    "resultado": "resultado/homologação/adjudicação de licitação",
    "outro": "qualquer outro documento",
}

GRUPOS_EXECUTANTE = {
    "solufarma": "a executante/contratada é a Solufarma",
    "tep": "a executante/contratada é a TEP (Tecnologia em Projetos de Engenharia / "
    "TEP Tecnologia em Engenharia)",
    "consorcio": "a executante é um consórcio (liste os membros em consorcio_membros)",
    "outra": "outra empresa identificada, nem Solufarma nem TEP",
}

DISCIPLINAS = {
    "civil": "obras civis, estrutura, alvenaria, acabamentos, reforma predial",
    "arquitetura": "projeto arquitetônico, layout",
    "eletrica": "instalações elétricas, força, iluminação, SPDA, subestação, quadros",
    "hvac": "ar condicionado, ventilação, exaustão, climatização, tratamento de ar",
    "refrigeracao": "câmara fria, frio industrial",
    "hidraulica": "hidrossanitário, água fria/quente predial, esgoto, drenagem",
    "incendio": "prevenção e combate a incêndio, sprinklers, detecção",
    "agua_purificada": "utilidade água purificada: PW, WFI, osmose reversa, loops sanitários",
    "vapor": "vapor puro, vapor industrial, geradores de vapor, caldeiras",
    "gases": "gases especiais/medicinais/industriais, ar comprimido, nitrogênio, CO2",
    "mecanica": "montagem mecânica, tubulação industrial, equipamentos de processo",
    "automacao_instrumentacao": "automação, CLP, supervisório, instrumentação, controle",
    "sala_limpa": "salas limpas/áreas classificadas: painéis, forros, portas, pisos técnicos",
}

ATIVIDADES = {
    "projeto": "elaboração de projeto (básico, executivo)",
    "execucao": "execução/obra/instalação",
    "fornecimento": "fornecimento de materiais ou equipamentos",
    "montagem": "montagem",
    "comissionamento": "comissionamento, start-up, testes",
    "qualificacao_validacao": "qualificação (DQ/IQ/OQ/PQ), validação",
    "manutencao": "manutenção preventiva/corretiva",
    "gerenciamento_fiscalizacao": "gerenciamento, fiscalização, supervisão de obra",
    "consultoria": "consultoria, laudos, estudos",
}

TIPOS_INSTALACAO = {
    "farmaceutica": "indústria/planta farmacêutica, medicamentos",
    "biotecnologia": "vacinas, imunobiológicos, biofármacos",
    "laboratorio": "laboratório (controle de qualidade, pesquisa, ensino)",
    "hospitalar": "hospital, clínica, centro cirúrgico",
    "pesquisa": "centro de pesquisa/tecnologia, universidade",
    "industrial": "indústria não farmacêutica",
    "alimenticia": "alimentos e bebidas",
    "predial": "edificação administrativa/comercial",
    "outro": "outro tipo",
}

# Campos escalares com página + trecho de evidência.
CAMPOS_ESCALARES = (
    "tipo_documento",
    "numero_documento",
    "orgao_contratante",
    "executante",
    "executante_grupo",
    "tipo_instalacao",
)
LISTAS = ("disciplinas", "atividades", "classificacao_iso")
MAX_QUANTITATIVOS = 8

# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------


def _vocab(d: dict[str, str]) -> str:
    return "\n".join(f"  - {k}: {v}" for k, v in d.items())


SYSTEM_PROMPT = f"""\
Você cataloga o acervo técnico da Solufarma Engenharia (engenharia para indústria \
farmacêutica, laboratórios e salas limpas). Recebe o texto extraído de UM documento \
(CAT, atestado, edital, ata...), dividido em trechos marcados com [p. N] ou [p. N-M]. \
O texto muitas vezes é OCR antigo, com ruído.

Devolva SOMENTE um objeto JSON, sem comentários, no formato do exemplo abaixo.

REGRAS
1. Use APENAS o que está escrito no texto. Se a informação não aparece, use null \
(ou lista vazia). Nunca deduza valor, data, área, cidade ou empresa que não esteja escrita.
2. Em cada campo, "pagina" é o número da página do marcador [p. N] de onde você tirou \
a informação (se o marcador é [p. 2-3], use 2 ou 3, a que contém o trecho).
3. "trecho" é uma cópia LITERAL e curta (até 80 caracteres) do texto que comprova o \
valor, com o ruído de OCR como está. Ele será conferido contra o documento.
4. OCR ruidoso: pode corrigir a grafia óbvia de nomes próprios em "valor" (ex.: \
"Buthntari" -> "Butantan"), mas se um NÚMERO está ilegível ou ambíguo, use null.
5. "executante" é quem EXECUTOU o serviço (a contratada/empresa atestada), nunca o \
contratante, nem o conselho (CREA/CAU), nem o profissional pessoa física.
6. Vocabulários fechados — use só as chaves listadas:
tipo_documento:
{_vocab(TIPOS_DOCUMENTO)}
executante_grupo:
{_vocab(GRUPOS_EXECUTANTE)}
disciplinas (inclua só as que o texto DESCREVE como serviço executado/projetado):
{_vocab(DISCIPLINAS)}
atividades:
{_vocab(ATIVIDADES)}
tipo_instalacao (a principal):
{_vocab(TIPOS_INSTALACAO)}
7. classificacao_iso: só classes de limpeza escritas no texto (ex.: "ISO 7", "ISO 8", \
"Classe A"). Não deduza pela natureza da obra.
8. periodo: datas no formato AAAA-MM-DD, AAAA-MM ou AAAA, conforme a precisão do texto.
9. valor_contrato: número em reais (ponto decimal, sem separador de milhar) e o texto \
original em "texto". Só se o valor estiver escrito.
10. quantitativos_chave: até {MAX_QUANTITATIVOS} quantidades que caracterizam o porte \
(área em m², capacidade, número de equipamentos...). Quantidade como escrita no texto.
11. resumo: 3 a 5 frases em português, factuais, só com o que está no texto: o que \
foi feito, para quem, por quem, onde, quando e o porte. Sem adjetivos promocionais.

Você também recebe "pistas" extraídas por expressões regulares — podem estar erradas \
ou incompletas. Use-as só como ponto de partida; o texto manda.

EXEMPLO DE FORMATO (valores fictícios):
{{
  "tipo_documento": {{"valor": "cat", "pagina": 1, "trecho": "CERTIDAO DE ACERVO TECNICO"}},
  "numero_documento": {{"valor": "SJC-00000", "pagina": 1, "trecho": "CERTIDAO N°: SJC-00000"}},
  "orgao_contratante": {{"valor": "Fundação Exemplo", "pagina": 2, "trecho": "FUNDACAO EXEMPLO"}},
  "executante": {{"valor": "Empresa X Ltda.", "pagina": 2, "trecho": "que a empresa X LTDA"}},
  "executante_grupo": {{"valor": "outra", "pagina": 2, "trecho": "que a empresa X LTDA"}},
  "consorcio_membros": [],
  "disciplinas": [{{"valor": "hvac", "pagina": 2}}, {{"valor": "eletrica", "pagina": 3}}],
  "atividades": [{{"valor": "execucao", "pagina": 2}}],
  "tipo_instalacao": {{"valor": "laboratorio", "pagina": 2, "trecho": "laboratorio de controle"}},
  "classificacao_iso": [{{"valor": "ISO 7", "pagina": 3}}],
  "periodo": {{"inicio": "2010-03", "fim": "2010-11", "pagina": 2, "trecho": "Março a Novembro/2010"}},
  "valor_contrato": {{"valor": 123456.78, "texto": "R$ 123.456,78", "pagina": 2}},
  "quantitativos_chave": [{{"descricao": "área climatizada", "quantidade": "1.200", \
"unidade": "m²", "pagina": 3}}],
  "local": {{"municipio": "Cidade", "uf": "SP", "pagina": 1, "trecho": "Cidade - SP"}},
  "resumo": "..."
}}
"""


# --------------------------------------------------------------------------
# Entrada: chunks -> texto marcado por página
# --------------------------------------------------------------------------


@dataclass
class ChunkEntrada:
    chunk_index: int
    conteudo: str
    pagina_inicio: int | None = None
    pagina_fim: int | None = None
    secao: str | None = None
    content_hash: str = ""


_CABECALHO = re.compile(r"^\[[^\]\n]{0,300}\]\s*\n")


def remover_cabecalho(conteudo: str) -> str:
    """Tira o cabeçalho contextual `[Título | seção | p. N]` que o chunker põe
    em todo chunk: repetido N vezes, só gastaria token."""
    return _CABECALHO.sub("", conteudo, count=1)


def _marcador(c: ChunkEntrada) -> str:
    if c.pagina_inicio is None:
        pag = "p. ?"
    elif c.pagina_fim and c.pagina_fim != c.pagina_inicio:
        pag = f"p. {c.pagina_inicio}-{c.pagina_fim}"
    else:
        pag = f"p. {c.pagina_inicio}"
    return f"[{pag} | {c.secao}]" if c.secao else f"[{pag}]"


def _orcamento_por_chunk(tamanhos: list[int], limite: int) -> list[int]:
    """Divide `limite` caracteres entre os chunks por "enchimento de água":
    chunk pequeno entra inteiro, a sobra vai para os grandes. Assim um documento
    enorme ainda mostra TODAS as seções (disciplinas aparecem no meio), só
    que cada uma mais curta."""
    n = len(tamanhos)
    if sum(tamanhos) <= limite:
        return list(tamanhos)
    cotas = [0] * n
    restantes = sorted(range(n), key=lambda i: tamanhos[i])
    sobra = limite
    while restantes:
        fatia = sobra // len(restantes)
        i = restantes[0]
        if tamanhos[i] <= fatia:
            cotas[i] = tamanhos[i]
            sobra -= tamanhos[i]
            restantes.pop(0)
        else:
            for j in restantes:
                cotas[j] = fatia
            break
    return cotas


def montar_contexto(chunks: list[ChunkEntrada], max_chars: int) -> tuple[str, bool]:
    """Texto do documento com marcadores de página. Devolve (texto, truncado?)."""
    ordenados = sorted(chunks, key=lambda c: c.chunk_index)
    corpos = [remover_cabecalho(c.conteudo).strip() for c in ordenados]
    cotas = _orcamento_por_chunk([len(b) for b in corpos], max_chars)
    partes, truncado = [], False
    for c, corpo, cota in zip(ordenados, corpos, cotas, strict=True):
        if cota < len(corpo):
            corpo = corpo[:cota].rstrip() + " [...]"
            truncado = True
        partes.append(f"{_marcador(c)}\n{corpo}")
    return "\n\n".join(partes), truncado


def hash_conteudo(chunks: list[ChunkEntrada]) -> str:
    """Impressão digital do texto classificado: se o documento for rechunkado,
    o hash muda e a classificação fica marcada como desatualizada."""
    base = "|".join(
        c.content_hash or hashlib.sha256(c.conteudo.encode()).hexdigest()
        for c in sorted(chunks, key=lambda c: c.chunk_index)
    )
    return hashlib.sha256(base.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Pistas da triagem por regex (grátis)
# --------------------------------------------------------------------------

_GRUPO_TRIAGEM = {
    "TEP": "tep",
    "Solufarma": "solufarma",
    "consórcio com TEP": "consorcio",
    "consórcio com Solufarma": "consorcio",
    "TEP e Solufarma": "consorcio",
    "outra": "outra",
}


def pistas_triagem(chunks: list[ChunkEntrada]) -> dict:
    """Roda `triagem.extrair_metadados` sobre o texto dos chunks. Só os campos
    que a regex achou; o grupo já no vocabulário daqui."""
    ordenados = sorted(chunks, key=lambda c: c.chunk_index)
    md = triagem.extrair_metadados([remover_cabecalho(c.conteudo) for c in ordenados])
    pistas = {}
    for nome in ("tipo", "numero_cat", "orgao", "contratante", "executante", "periodo", "local"):
        campo = getattr(md, nome)
        if campo.valor:
            pistas[nome] = {"valor": campo.valor, "confianca": campo.confianca}
    grupo = md.executante_grupo.valor
    if grupo:
        pistas["executante_grupo"] = {
            "valor": _GRUPO_TRIAGEM.get(grupo, "outra"),
            "confianca": md.executante_grupo.confianca,
        }
    return pistas


def montar_mensagem(titulo: str | None, contexto: str, pistas: dict, truncado: bool) -> str:
    aviso = (
        "\n(Documento longo: alguns trechos foram encurtados e terminam em [...].)"
        if truncado
        else ""
    )
    return (
        f"TÍTULO NO CADASTRO: {titulo or '(sem título)'}\n"
        f"PISTAS (regex, podem estar erradas): {json.dumps(pistas, ensure_ascii=False)}\n"
        f"{aviso}\n\nTEXTO DO DOCUMENTO:\n{contexto}"
    )


# --------------------------------------------------------------------------
# Custo
# --------------------------------------------------------------------------

# pt-BR com ruído de OCR tokeniza pior que inglês: ~3 caracteres por token é
# conservador (superestima um pouco, que é o lado certo para orçamento).
CHARS_POR_TOKEN = 3.0
TOKENS_SAIDA_ESTIMADOS = 1500


def estimar_tokens(texto: str) -> int:
    return int(len(texto) / CHARS_POR_TOKEN) + 1


def estimar_custo(
    tokens_entrada: int,
    preco_entrada: float,
    preco_saida: float,
    tokens_saida: int = TOKENS_SAIDA_ESTIMADOS,
) -> float:
    """Preços em US$ por milhão de tokens."""
    return (tokens_entrada * preco_entrada + tokens_saida * preco_saida) / 1_000_000


# --------------------------------------------------------------------------
# Saída: parse + validação
# --------------------------------------------------------------------------


class RespostaInvalida(ValueError):
    """O LLM não devolveu um objeto JSON utilizável."""


def extrair_json(texto: str) -> dict:
    """Aceita JSON puro, cercado por ```json ... ``` ou com texto em volta."""
    bruto = (texto or "").strip()
    cerca = re.search(r"```(?:json)?\s*(.*?)```", bruto, re.DOTALL)
    if cerca:
        bruto = cerca.group(1).strip()
    if not bruto.startswith("{"):
        ini, fim = bruto.find("{"), bruto.rfind("}")
        if ini < 0 or fim <= ini:
            raise RespostaInvalida("resposta sem objeto JSON")
        bruto = bruto[ini : fim + 1]
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise RespostaInvalida(f"JSON inválido: {exc}") from exc
    if not isinstance(dados, dict):
        raise RespostaInvalida("o JSON não é um objeto")
    return dados


def _normalizar(s: str) -> str:
    """Para conferir trecho: maiúsculas, sem acento, só letras e dígitos."""
    return re.sub(r"[^A-Z0-9]", "", triagem.dobrar(s or ""))


@dataclass
class Validador:
    """Confere a saída do LLM contra o documento de onde ela saiu."""

    chunks: list[ChunkEntrada]
    avisos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        paginas = set()
        self._texto_pagina: dict[int, str] = {}
        for c in self.chunks:
            ini = c.pagina_inicio
            fim = c.pagina_fim or ini
            if ini is None:
                continue
            norm = _normalizar(remover_cabecalho(c.conteudo))
            for p in range(ini, fim + 1):
                paginas.add(p)
                self._texto_pagina[p] = self._texto_pagina.get(p, "") + norm
        self.paginas = paginas
        self._texto_total = "".join(_normalizar(remover_cabecalho(c.conteudo)) for c in self.chunks)
        self._dobrado = "\n".join(
            triagem.dobrar(remover_cabecalho(c.conteudo)) for c in self.chunks
        )

    # -- primitivas ---------------------------------------------------------

    def iso_no_texto(self, valor: str) -> bool:
        """A classe de limpeza aparece escrita? Aceita as grafias reais do
        acervo: "ISO 7", "ISO-7", "ISO classe 7", "classe ISO 7", "ISO
        classes B, C D" (GMP em letra)."""
        m = re.search(r"([1-9]|\b[A-D])\s*$", triagem.dobrar(valor.strip()))
        if not m:
            return False
        n = m.group(1).strip()
        sep = r"[\s\-:,.]{0,3}"
        padroes = (
            rf"ISO{sep}(?:CLASSES?{sep})?(?:[A-D1-9]{sep}(?:E{sep})?){{0,3}}{n}\b",
            rf"CLASSES?{sep}(?:ISO{sep})?{n}\b",
            rf"GRAU{sep}{n}\b",
        )
        return any(re.search(p, self._dobrado) for p in padroes)

    def pagina(self, bruto, campo: str) -> int | None:
        if bruto is None:
            return None
        try:
            p = int(bruto)
        except (TypeError, ValueError):
            self.avisos.append(f"{campo}: página inválida {bruto!r} descartada")
            return None
        if self.paginas and p not in self.paginas:
            self.avisos.append(f"{campo}: página {p} fora do documento, descartada")
            return None
        return p

    def trecho_ok(self, trecho: str | None, pagina: int | None) -> bool | None:
        """True se o trecho (normalizado) está no texto — na página citada ou,
        tolerando página errada, em qualquer ponto do documento. None se não
        veio trecho (ou é curto demais para provar alguma coisa)."""
        if not trecho:
            return None
        alvo = _normalizar(trecho)
        if len(alvo) < 4:
            return None
        if pagina is not None and alvo in self._texto_pagina.get(pagina, ""):
            return True
        return alvo in self._texto_total

    def escalar(self, bruto, campo: str, vocab: dict | None = None) -> dict | None:
        if not isinstance(bruto, dict):
            if bruto not in (None, "", {}):
                self.avisos.append(f"{campo}: formato inesperado, descartado")
            return None
        valor = bruto.get("valor")
        if isinstance(valor, str):
            valor = valor.strip() or None
        if valor is None:
            return None
        if vocab is not None:
            valor = str(valor).strip().lower()
            if valor not in vocab:
                self.avisos.append(f"{campo}: valor fora do vocabulário {valor!r}, descartado")
                return None
        pagina = self.pagina(bruto.get("pagina"), campo)
        trecho = bruto.get("trecho") if isinstance(bruto.get("trecho"), str) else None
        saida = {"valor": valor, "pagina": pagina}
        if trecho:
            saida["trecho"] = trecho[:120]
            saida["verificado"] = self.trecho_ok(trecho, pagina)
        return saida

    def lista(self, bruto, campo: str, vocab: dict | None = None) -> list[dict]:
        if not isinstance(bruto, list):
            return []
        saida, vistos = [], set()
        for item in bruto:
            if isinstance(item, str):
                item = {"valor": item}
            if not isinstance(item, dict) or not item.get("valor"):
                continue
            valor = str(item["valor"]).strip()
            if vocab is not None:
                valor = valor.lower()
                if valor not in vocab:
                    self.avisos.append(f"{campo}: {valor!r} fora do vocabulário, descartado")
                    continue
            if valor in vistos:
                continue
            vistos.add(valor)
            saida.append({"valor": valor, "pagina": self.pagina(item.get("pagina"), campo)})
        return saida


_DATA = re.compile(r"^(19|20)\d{2}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
_UF = re.compile(r"^[A-Z]{2}$")


def _data(bruto) -> str | None:
    if not isinstance(bruto, str):
        return None
    s = bruto.strip()
    return s if _DATA.match(s) else None


def _numero(bruto) -> float | None:
    if isinstance(bruto, bool):
        return None
    if isinstance(bruto, int | float):
        return float(bruto) if bruto >= 0 else None
    if isinstance(bruto, str):
        s = re.sub(r"[^\d,.]", "", bruto)
        if "," in s:  # formato brasileiro 1.234,56
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def validar(
    dados: dict, chunks: list[ChunkEntrada], pistas: dict | None = None
) -> tuple[dict, str | None, list[str]]:
    """Normaliza a saída do LLM. Devolve (classificacao, resumo, avisos).

    Nada fora do vocabulário, nenhuma página fora do documento, nenhum número
    que não seja número. Divergências com a triagem por regex viram aviso.
    """
    v = Validador(chunks)
    cls: dict = {}
    cls["tipo_documento"] = v.escalar(
        dados.get("tipo_documento"), "tipo_documento", TIPOS_DOCUMENTO
    )
    cls["numero_documento"] = v.escalar(dados.get("numero_documento"), "numero_documento")
    cls["orgao_contratante"] = v.escalar(dados.get("orgao_contratante"), "orgao_contratante")
    cls["executante"] = v.escalar(dados.get("executante"), "executante")
    cls["executante_grupo"] = v.escalar(
        dados.get("executante_grupo"), "executante_grupo", GRUPOS_EXECUTANTE
    )
    membros = dados.get("consorcio_membros")
    cls["consorcio_membros"] = (
        [str(m).strip() for m in membros if str(m).strip()][:6] if isinstance(membros, list) else []
    )
    cls["disciplinas"] = v.lista(dados.get("disciplinas"), "disciplinas", DISCIPLINAS)
    cls["atividades"] = v.lista(dados.get("atividades"), "atividades", ATIVIDADES)
    cls["tipo_instalacao"] = v.escalar(
        dados.get("tipo_instalacao"), "tipo_instalacao", TIPOS_INSTALACAO
    )
    iso = v.lista(dados.get("classificacao_iso"), "classificacao_iso")
    cls["classificacao_iso"] = [i for i in iso if v.iso_no_texto(i["valor"])]
    for i in iso:
        if i not in cls["classificacao_iso"]:
            v.avisos.append(
                f"classificacao_iso: {i['valor']!r} não encontrada no texto, descartada"
            )

    # Período
    per = dados.get("periodo")
    if isinstance(per, dict) and (per.get("inicio") or per.get("fim")):
        ini, fim = _data(per.get("inicio")), _data(per.get("fim"))
        if (per.get("inicio") and not ini) or (per.get("fim") and not fim):
            v.avisos.append("periodo: data em formato inválido descartada")
        if ini and fim and fim < ini:
            v.avisos.append("periodo: fim antes do início — mantido, conferir")
        if ini or fim:
            pagina = v.pagina(per.get("pagina"), "periodo")
            cls["periodo"] = {"inicio": ini, "fim": fim, "pagina": pagina}
            if isinstance(per.get("trecho"), str) and per["trecho"]:
                cls["periodo"]["trecho"] = per["trecho"][:120]
                cls["periodo"]["verificado"] = v.trecho_ok(per["trecho"], pagina)
        else:
            cls["periodo"] = None
    else:
        cls["periodo"] = None

    # Valor do contrato: só aceito se os dígitos do texto original aparecem no
    # documento. É o campo onde alucinação custa mais caro.
    val = dados.get("valor_contrato")
    cls["valor_contrato"] = None
    if isinstance(val, dict) and val.get("valor") is not None:
        numero = _numero(val.get("valor"))
        texto = val.get("texto") if isinstance(val.get("texto"), str) else None
        pagina = v.pagina(val.get("pagina"), "valor_contrato")
        if numero is None:
            v.avisos.append("valor_contrato: não numérico, descartado")
        else:
            digitos = re.sub(r"\D", "", texto or "")
            achado = bool(digitos) and len(digitos) >= 3 and digitos in v._texto_total
            cls["valor_contrato"] = {
                "valor": numero,
                "texto": texto,
                "pagina": pagina,
                "verificado": achado,
            }
            if not achado:
                v.avisos.append("valor_contrato: dígitos não localizados no texto — conferir")

    # Quantitativos
    quants = []
    for q in dados.get("quantitativos_chave") or []:
        if not isinstance(q, dict) or not q.get("descricao") or q.get("quantidade") in (None, ""):
            continue
        quants.append(
            {
                "descricao": str(q["descricao"]).strip()[:120],
                "quantidade": str(q["quantidade"]).strip()[:40],
                "unidade": (str(q.get("unidade")).strip()[:20] if q.get("unidade") else None),
                "pagina": v.pagina(q.get("pagina"), "quantitativos_chave"),
            }
        )
    cls["quantitativos_chave"] = quants[:MAX_QUANTITATIVOS]

    # Local
    loc = dados.get("local")
    cls["local"] = None
    if isinstance(loc, dict) and (loc.get("municipio") or loc.get("uf")):
        uf = str(loc.get("uf") or "").strip().upper() or None
        if uf and not _UF.match(uf):
            v.avisos.append(f"local: UF inválida {uf!r} descartada")
            uf = None
        municipio = str(loc.get("municipio") or "").strip() or None
        if municipio or uf:
            cls["local"] = {
                "municipio": municipio,
                "uf": uf,
                "pagina": v.pagina(loc.get("pagina"), "local"),
            }

    # Confronto com a triagem por regex
    pistas = pistas or {}
    grupo_llm = (cls["executante_grupo"] or {}).get("valor")
    grupo_rx = (pistas.get("executante_grupo") or {}).get("valor")
    if grupo_rx and grupo_llm and grupo_rx != grupo_llm:
        v.avisos.append(
            f"executante_grupo: LLM disse {grupo_llm!r}, triagem por regex disse {grupo_rx!r}"
        )
    elif grupo_rx and not grupo_llm:
        v.avisos.append(f"executante_grupo: LLM não identificou; regex sugere {grupo_rx!r}")
    cat_rx = (pistas.get("numero_cat") or {}).get("valor")
    cat_llm = (cls["numero_documento"] or {}).get("valor")
    if (
        cat_rx
        and cat_llm
        and not triagem.numeros_batem(cat_rx, cat_llm)
        and not (triagem.numeros_batem(cat_llm, cat_rx))
    ):
        v.avisos.append(f"numero_documento: LLM {cat_llm!r} x regex {cat_rx!r}")

    resumo = dados.get("resumo")
    resumo = resumo.strip() if isinstance(resumo, str) and resumo.strip() else None
    if resumo is None:
        v.avisos.append("resumo ausente")
    return cls, resumo, v.avisos


# --------------------------------------------------------------------------
# Orquestração de um documento
# --------------------------------------------------------------------------

MAX_CHARS_PADRAO = 120_000


@dataclass
class Resultado:
    classificacao: dict
    resumo: str | None
    avisos: list[str]
    uso: dict


def preparar(
    chunks: list[ChunkEntrada], titulo: str | None, max_chars: int = MAX_CHARS_PADRAO
) -> tuple[str, dict, bool]:
    """Monta a mensagem do usuário. Devolve (mensagem, pistas, truncado)."""
    if not chunks:
        raise ValueError("documento sem chunks — indexe antes de classificar")
    contexto, truncado = montar_contexto(chunks, max_chars)
    pistas = pistas_triagem(chunks)
    return montar_mensagem(titulo, contexto, pistas, truncado), pistas, truncado


def classificar_documento(
    llm,
    chunks: list[ChunkEntrada],
    titulo: str | None = None,
    modelo: str = "",
    max_chars: int = MAX_CHARS_PADRAO,
    max_tokens: int = 3000,
) -> Resultado:
    """Uma chamada de LLM por documento (+1 nova tentativa se o JSON vier quebrado)."""
    mensagem, pistas, truncado = preparar(chunks, titulo, max_chars)
    mensagens = [{"role": "user", "content": mensagem}]
    usos = []
    dados = None
    for tentativa in range(2):
        texto = llm.completar(SYSTEM_PROMPT, mensagens, max_tokens=max_tokens)
        usos.append(dict(getattr(llm, "ultimo_uso", {}) or {}))
        try:
            dados = extrair_json(texto)
            break
        except RespostaInvalida:
            if tentativa == 1:
                raise
            mensagens = [
                *mensagens,
                {"role": "assistant", "content": texto},
                {"role": "user", "content": "Resposta inválida. Devolva SOMENTE o objeto JSON."},
            ]

    cls, resumo, avisos = validar(dados, chunks, pistas)
    if truncado:
        avisos.append(f"texto truncado em {max_chars} caracteres para caber no orçamento")
    custos = [u.get("custo_usd") for u in usos if u.get("custo_usd") is not None]
    uso = {
        "chamadas": len(usos),
        "tokens_entrada": sum(u.get("tokens_entrada") or 0 for u in usos),
        "tokens_saida": sum(u.get("tokens_saida") or 0 for u in usos),
        "custo_usd": round(sum(custos), 6) if custos else None,
    }
    cls["meta"] = {
        "versao_schema": VERSAO_SCHEMA,
        "modelo": modelo,
        "classificado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "hash_conteudo": hash_conteudo(chunks),
        "texto_truncado": truncado,
        "pistas_regex": pistas,
        "avisos": avisos,
        "uso": uso,
    }
    return Resultado(cls, resumo, avisos, uso)


# --------------------------------------------------------------------------
# Banco (psycopg) — fino, para o CLI
# --------------------------------------------------------------------------


def listar_documentos(conn) -> list[dict]:
    """Todos os documentos com o hash atual dos chunks e o da classificação."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select d.id::text, d.titulo, d.tipo,
                   d.classificacao is not null,
                   d.classificacao #>> '{meta,hash_conteudo}',
                   count(c.id)
              from documentos d
              left join doc_chunks c on c.documento_id = d.id
             group by d.id
             order by d.created_at
            """
        )
        return [
            {
                "id": r[0],
                "titulo": r[1],
                "tipo": r[2],
                "classificado": r[3],
                "hash_classificado": r[4],
                "n_chunks": r[5],
            }
            for r in cur.fetchall()
        ]


def carregar_chunks(conn, documento_id: str) -> list[ChunkEntrada]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select chunk_index, conteudo, pagina_inicio, pagina_fim, secao, content_hash
              from doc_chunks where documento_id = %s order by chunk_index
            """,
            (documento_id,),
        )
        return [ChunkEntrada(*r) for r in cur.fetchall()]


def salvar(conn, documento_id: str, classificacao: dict, resumo: str | None) -> None:
    """UPDATE só das duas colunas desta etapa — não toca no que outras etapas
    (cadastro, indexação) escrevem na mesma linha."""
    with conn.cursor() as cur:
        cur.execute(
            "update documentos set classificacao = %s::jsonb, resumo = %s where id = %s",
            (json.dumps(classificacao, ensure_ascii=False), resumo, documento_id),
        )
    conn.commit()
