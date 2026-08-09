"""
extracao.py — Boilerplate, roteamento, chamada ao VLM e orquestração.

Fluxo por documento:
    sniff -> renderiza páginas -> detecta boilerplate global
    -> roteia cada página (nativo | vlm) -> chama o VLM com carry-over
    -> salva JSON (markdown por página + metadados)

Os dois invariantes que este módulo carrega sozinho:

INVARIANTE 2 — texto nativo pode ser só marca d'água. As págs. 3–60 do CAT do
SENAI têm 347 caracteres nativos idênticos (o carimbo do CAU). Uma heurística
`len(texto) > 50` classifica as 58 como digitais, pula o OCR e produz um
documento com o mesmo carimbo repetido — sem exceção nenhuma. Daí a DUPLA
condição (caracteres úteis E densidade) e a remoção do boilerplate ANTES.

INVARIANTE 3 — página não é fronteira semântica. Páginas VLM contíguas formam
um BLOCO processado em sequência (o carry-over exige ordem); blocos diferentes
rodam em paralelo entre si. Paralelizar DENTRO do bloco quebra o carry-over e
as tabelas das págs. 43–60 perdem cabeçalho.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import requests

from solufarma import config, formatos, prompts
from solufarma.modelos import Documento, Pagina

# Códigos que valem retry: throttling e indisponibilidade temporária.
STATUS_RETENTAVEIS = {408, 429, 500, 502, 503, 504, 529}


class FalhaExtracao(RuntimeError):
    """Falha irrecuperável em um documento. Não derruba o lote."""


# --------------------------------------------------------------------------
# 1. Boilerplate global — precisa rodar ANTES do roteamento
# --------------------------------------------------------------------------


def detectar_boilerplate(textos: list[str]) -> set[str]:
    """
    Linhas presentes em mais de LIMIAR_BOILERPLATE das páginas.

    Roda antes do roteamento de propósito: o carimbo do CAU é exatamente esse
    tipo de linha, e enquanto ele estiver no texto a contagem de caracteres
    úteis mente para cima e a página escaneada passa por digital.
    """
    if len(textos) < 3:
        return set()

    contagem: Counter[str] = Counter()
    for texto in textos:
        # `set` por página: uma linha repetida 5x na MESMA página conta 1.
        linhas_unicas = {ln.strip() for ln in texto.splitlines() if len(ln.strip()) > 12}
        contagem.update(linhas_unicas)

    corte = len(textos) * config.LIMIAR_BOILERPLATE
    return {linha for linha, n in contagem.items() if n >= corte}


def extrair_assinaturas(boilerplate: set[str]) -> set[str]:
    """
    Identificadores únicos presentes nas linhas de boilerplate.

    Motivo (descoberto no CAT do SENAI, 2026-08-08): o mesmo carimbo aparece em
    DUAS diagramações no mesmo documento. Nas págs. 3-60 vem como uma linha só,
    repetida 58 vezes — a detecção por repetição pega. Nas págs. 1-2 o CAU
    quebra o mesmo dado em outro texto ("A autenticidade desta Certidão pode ser
    verificada em: ... com a chave: X"), que aparece 1 vez e passa despercebido.

    O que as três formas compartilham é a chave de impressão. Extraindo esses
    identificadores das linhas JÁ confirmadas como boilerplate, pegamos as
    variantes sem baixar o limiar de repetição — que removeria conteúdo real.

    Critério: token com 12+ caracteres, alfanumérico, misturando letra e dígito.
    Descrições de material do acervo (`#240MM2`, `QDC-4P-PIL`) são mais curtas e
    não são capturadas — ver teste em test_roteamento.py.
    """
    import re

    assinaturas: set[str] = set()
    for linha in boilerplate:
        for token in re.findall(r"\b[A-Za-z0-9]{12,}\b", linha):
            tem_letra = any(c.isalpha() for c in token)
            tem_digito = any(c.isdigit() for c in token)
            if tem_letra and tem_digito:
                assinaturas.add(token)
    return assinaturas


def limpar(texto: str, boilerplate: set[str], assinaturas: set[str] | None = None) -> str:
    """
    Remove boilerplate do texto nativo.

    Duas passadas: linha idêntica ao boilerplate detectado, e linha que CONTÉM
    um identificador de boilerplate (pega as variantes de diagramação).
    """
    if assinaturas is None:
        assinaturas = extrair_assinaturas(boilerplate)

    linhas = []
    for ln in texto.splitlines():
        if ln.strip() in boilerplate:
            continue
        if any(a in ln for a in assinaturas):
            continue
        linhas.append(ln)
    return "\n".join(linhas).strip()


# --------------------------------------------------------------------------
# 2. Roteamento por página — a dupla condição
# --------------------------------------------------------------------------


def precisa_vlm(texto_limpo: str, area_px: int) -> bool:
    """
    True se a página precisa passar pelo VLM.

    As DUAS condições precisam passar para a página ser considerada digital:
      1. volume absoluto de caracteres úteis
      2. densidade (caracteres por pixel² da página)

    O carimbo do CAU tem 347 caracteres — passa em (1) com folga. Numa folha A4
    a 1500px isso dá ~0.00015 char/px², e reprova em (2).
    """
    n = len(texto_limpo)

    # As duas condições ficam separadas de propósito: o linter sugere fundir,
    # mas elas testam coisas diferentes e cada uma tem um limiar próprio que o
    # M2 vai calibrar. Fundidas, fica impossível saber qual reprovou a página.
    volume_insuficiente = n < config.MIN_CARACTERES_UTEIS
    densidade_insuficiente = bool(area_px) and (n / area_px) < config.MIN_DENSIDADE

    return volume_insuficiente or densidade_insuficiente


# --------------------------------------------------------------------------
# 3. Chamada ao OpenRouter
# --------------------------------------------------------------------------


def _extrair_json(bruto: str) -> dict:
    """Tolerante a cercas de código e preâmbulo antes do JSON."""
    import re

    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", bruto.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio >= 0 and fim > inicio:
            try:
                return json.loads(texto[inicio : fim + 1])
            except json.JSONDecodeError:
                pass
    # Último recurso: preserva o texto como markdown e marca confiança baixa,
    # para a página aparecer no relatório de revisão em vez de sumir.
    return {"markdown": bruto, "confianca": 0.4, "observacoes": "resposta não era JSON válido"}


def _assinatura_cache(jpeg: bytes, contexto_herdado: str) -> str:
    """
    Chave do cache: imagem + contexto herdado + slug do modelo + prompts.

    Os prompts entram porque mudar a regra de transcrição muda o resultado —
    sem isso, editar `prompts.py` deixaria o cache servindo respostas do prompt
    antigo em silêncio.
    """
    h = hashlib.sha256()
    h.update(jpeg)
    h.update(contexto_herdado.encode("utf-8"))
    h.update(config.OPENROUTER_MODELO.encode("utf-8"))
    h.update(prompts.SYSTEM_PROMPT.encode("utf-8"))
    h.update(prompts.USER_PROMPT.encode("utf-8"))
    return h.hexdigest()


def chamar_vlm(jpeg: bytes, contexto_herdado: str, chave_api: str) -> tuple[dict, bool]:
    """
    Transcreve uma página. Retorna (resultado, veio_do_cache).

    O flag de cache é o que permite provar a idempotência exigida pelo
    CLAUDE.md: segunda execução do mesmo documento deve custar US$ 0,00.
    """
    config.DIR_CACHE.mkdir(parents=True, exist_ok=True)
    arquivo_cache = config.DIR_CACHE / f"{_assinatura_cache(jpeg, contexto_herdado)}.json"
    if arquivo_cache.exists():
        return json.loads(arquivo_cache.read_text(encoding="utf-8")), True

    payload = {
        "model": config.OPENROUTER_MODELO,
        "temperature": 0,
        "max_tokens": 8000,
        "messages": [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,"
                            + base64.b64encode(jpeg).decode("ascii")
                        },
                    },
                    {
                        "type": "text",
                        "text": prompts.USER_PROMPT.format(contexto_herdado=contexto_herdado),
                    },
                ],
            },
        ],
    }
    cabecalhos = {
        "Authorization": f"Bearer {chave_api}",
        "Content-Type": "application/json",
    }

    ultimo_erro: Exception | None = None
    for tentativa in range(config.TENTATIVAS):
        try:
            r = requests.post(
                config.OPENROUTER_URL,
                headers=cabecalhos,
                json=payload,
                timeout=config.TIMEOUT_S,
            )
            if r.status_code in STATUS_RETENTAVEIS:
                time.sleep(2**tentativa + 1)
                continue
            # 401/402/404 não são retentáveis: chave inválida, crédito zerado
            # ou slug de modelo errado. Falhar rápido e com a mensagem da API.
            if not r.ok:
                raise FalhaExtracao(f"OpenRouter HTTP {r.status_code}: {r.text[:400]}")

            corpo = r.json()
            if "choices" not in corpo:
                raise FalhaExtracao(f"resposta sem 'choices': {json.dumps(corpo)[:400]}")

            resultado = _extrair_json(corpo["choices"][0]["message"]["content"])
            uso = corpo.get("usage") or {}
            resultado["_tokens_entrada"] = uso.get("prompt_tokens", 0)
            resultado["_tokens_saida"] = uso.get("completion_tokens", 0)

            arquivo_cache.write_text(
                json.dumps(resultado, ensure_ascii=False), encoding="utf-8"
            )
            return resultado, False

        except FalhaExtracao:
            raise  # erro de configuração: não adianta tentar de novo
        except Exception as e:  # noqa: BLE001 — rede/JSON; registra e tenta de novo
            ultimo_erro = e
            time.sleep(2**tentativa + 1)

    raise FalhaExtracao(
        f"OpenRouter falhou após {config.TENTATIVAS} tentativas: {ultimo_erro}"
    )


# --------------------------------------------------------------------------
# 4. Orquestração de um documento
# --------------------------------------------------------------------------


def _montar_blocos(rotas: list[str]) -> list[list[int]]:
    """Agrupa índices de páginas VLM contíguas. Cada bloco roda em sequência."""
    blocos: list[list[int]] = []
    atual: list[int] = []
    for i, rota in enumerate(rotas):
        if rota == "vlm":
            atual.append(i)
        elif atual:
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    return blocos


def processar(caminho: Path, saida_dir: Path, verboso: bool = True) -> Documento:
    """Extrai um documento. Levanta FalhaExtracao — o lote captura e segue."""
    chave_api = config.chave("OPENROUTER_API_KEY")
    formato = formatos.sniff(caminho)
    if verboso:
        print(f"[{caminho.name}] formato real: {formato}")

    brutas = formatos.carregar_paginas(caminho, formato)
    if not brutas:
        raise FalhaExtracao(f"{caminho.name}: nenhuma página carregada")

    textos = [t for _, t, _ in brutas]
    boilerplate = detectar_boilerplate(textos)
    if boilerplate and verboso:
        print(f"  boilerplate: {len(boilerplate)} linha(s) removida(s) do texto nativo")

    doc = Documento(
        arquivo=caminho.name,
        hash_documento=hashlib.sha256(caminho.read_bytes()).hexdigest()[:16],
        n_paginas=len(brutas),
        formato_detectado=formato,
        modelo=config.OPENROUTER_MODELO,
        boilerplate_removido=sorted(boilerplate),
    )

    # --- fase A: roteamento (sequencial, sem custo) ---
    # Calcula as assinaturas uma vez só e reusa nas 60 páginas.
    assinaturas = extrair_assinaturas(boilerplate)
    limpos = [limpar(texto, boilerplate, assinaturas) for _, texto, _ in brutas]
    rotas = [
        "vlm" if precisa_vlm(limpo, area) else "nativo"
        for limpo, (_, _, area) in zip(limpos, brutas)
    ]
    if verboso:
        print(f"  rotas: {rotas.count('nativo')} nativas, {rotas.count('vlm')} via VLM")

    paginas: list[Pagina | None] = [None] * len(brutas)

    # --- fase B: páginas nativas (instantâneo, custo zero) ---
    for i, (rota, limpo) in enumerate(zip(rotas, limpos)):
        if rota == "nativo":
            paginas[i] = Pagina(
                numero=i + 1,
                estrategia="nativo",
                markdown=limpo,
                confianca=1.0,
                area_px=brutas[i][2],
                caracteres_uteis=len(limpo),
            )

    # --- fase C: páginas VLM, em blocos contíguos ---
    def processa_bloco(indices: list[int]) -> list[Pagina]:
        resultado: list[Pagina] = []
        anterior: Pagina | None = None
        for i in indices:
            jpeg, _, area = brutas[i]
            bruto, do_cache = chamar_vlm(jpeg, prompts.montar_contexto(anterior), chave_api)
            p = Pagina(
                numero=i + 1,
                estrategia="vlm",
                markdown=(bruto.get("markdown") or "").strip(),
                secao_corrente=bruto.get("secao_corrente"),
                cabecalho_tabela_final=bruto.get("cabecalho_tabela_final"),
                tabela_aberta_no_fim=bool(bruto.get("tabela_aberta_no_fim")),
                confianca=float(bruto.get("confianca") or 0.0),
                observacoes=bruto.get("observacoes") or "",
                tokens_entrada=bruto.get("_tokens_entrada", 0),
                tokens_saida=bruto.get("_tokens_saida", 0),
                area_px=area,
                caracteres_uteis=len(limpos[i]),
            )
            if not p.markdown:
                p.estrategia = "vazia"
            if do_cache:
                doc.chamadas_cache += 1
            else:
                doc.chamadas_pagas += 1
            resultado.append(p)
            anterior = p
            if verboso:
                marca = "cache" if do_cache else f"conf {p.confianca:.2f}"
                print(f"    pág {p.numero}/{len(brutas)} ok ({marca})")
        return resultado

    blocos = _montar_blocos(rotas)
    if blocos:
        with ThreadPoolExecutor(max_workers=config.WORKERS) as pool:
            futuros = [pool.submit(processa_bloco, b) for b in blocos]
            for fut in as_completed(futuros):
                for p in fut.result():
                    paginas[p.numero - 1] = p

    doc.paginas = sorted([p for p in paginas if p is not None], key=lambda p: p.numero)

    # Tokens de páginas servidas pelo cache não são cobrados de novo, mas ficam
    # no JSON. Só o que saiu para a API entra no custo.
    if doc.chamadas_pagas:
        proporcao = doc.chamadas_pagas / max(doc.chamadas_pagas + doc.chamadas_cache, 1)
        entrada = doc.tokens_entrada * proporcao
        saida = doc.tokens_saida * proporcao
        doc.custo_estimado_usd = round(
            entrada / 1e6 * config.PRECO_ENTRADA_USD_MTOK
            + saida / 1e6 * config.PRECO_SAIDA_USD_MTOK,
            4,
        )

    saida_dir.mkdir(parents=True, exist_ok=True)
    destino = saida_dir / f"{caminho.stem}.json"
    destino.write_text(
        json.dumps(asdict(doc), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if verboso:
        print(f"  -> {destino.name}  (US$ {doc.custo_estimado_usd:.4f})")
        baixa = [
            p.numero for p in doc.paginas if p.confianca < config.LIMIAR_CONFIANCA_REVISAO
        ]
        if baixa:
            print(f"  ATENÇÃO: revisar manualmente as páginas {baixa}")

    return doc


# --------------------------------------------------------------------------
# 5. Lote com tolerância a falha
# --------------------------------------------------------------------------


def _registrar_falha(arquivo: str, estagio: str, erro: Exception) -> None:
    config.DIR_RELATORIOS.mkdir(parents=True, exist_ok=True)
    linha = {
        "arquivo": arquivo,
        "estagio": estagio,
        "erro": f"{type(erro).__name__}: {erro}",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with open(config.DIR_RELATORIOS / "falhas.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def relatorio_custo(documentos: list[Documento]) -> str:
    """Tabela Markdown de custo por documento. Obrigatória, não opcional."""
    cab = (
        "| arquivo | páginas | nativas | vlm | tokens_in | tokens_out | "
        "pagas | cache | custo_usd |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    linhas = [cab, sep]
    for d in documentos:
        linhas.append(
            f"| {d.arquivo} | {d.n_paginas} | {d.n_nativas} | {d.n_vlm} | "
            f"{d.tokens_entrada} | {d.tokens_saida} | {d.chamadas_pagas} | "
            f"{d.chamadas_cache} | {d.custo_estimado_usd:.4f} |"
        )
    total = sum(d.custo_estimado_usd for d in documentos)
    pagas = sum(d.chamadas_pagas for d in documentos)
    linhas.append(
        f"| **TOTAL ({len(documentos)} doc)** | | | | | | **{pagas}** | | **{total:.4f}** |"
    )
    return "\n".join(linhas)


def processar_lote(
    caminhos: list[Path], saida_dir: Path, verboso: bool = True
) -> tuple[list[Documento], list[str]]:
    """
    Processa vários documentos. Falha em um NÃO interrompe os demais.

    Retorna (documentos_ok, arquivos_que_falharam). As falhas vão para
    `data/relatorios/falhas.jsonl` com {arquivo, estagio, erro, timestamp}.
    """
    ok: list[Documento] = []
    falhos: list[str] = []

    for i, caminho in enumerate(caminhos, start=1):
        if verboso:
            print(f"\n({i}/{len(caminhos)}) {caminho.name}")
        try:
            ok.append(processar(caminho, saida_dir, verboso=verboso))
        except Exception as e:  # noqa: BLE001 — um documento ruim não derruba o lote
            falhos.append(caminho.name)
            _registrar_falha(caminho.name, "extracao", e)
            print(f"  FALHOU: {type(e).__name__}: {e}")

    if ok:
        tabela = relatorio_custo(ok)
        config.DIR_RELATORIOS.mkdir(parents=True, exist_ok=True)
        destino = config.DIR_RELATORIOS / "custo_extracao.md"
        destino.write_text(
            f"# Custo de extração\n\n"
            f"Modelo: `{config.OPENROUTER_MODELO}` "
            f"(${config.PRECO_ENTRADA_USD_MTOK}/${config.PRECO_SAIDA_USD_MTOK} por MTok)\n"
            f"Gerado em: {datetime.now(UTC).isoformat()}\n\n"
            f"{tabela}\n",
            encoding="utf-8",
        )
        if verboso:
            print(f"\n{tabela}\n\nRelatório: {destino}")

    if falhos:
        print(
            f"\n{len(falhos)} documento(s) falharam: {', '.join(falhos)}\n"
            f"Detalhes em {config.DIR_RELATORIOS / 'falhas.jsonl'}"
        )

    return ok, falhos
