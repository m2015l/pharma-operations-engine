#!/usr/bin/env python
"""
tools/triar_documentos.py — Triagem de PDFs do acervo pelo CONTEÚDO (camada 3 do WAT).

Para cada PDF, sem nenhuma chamada paga (sem LLM, sem OCR/VLM, sem Supabase):
  - roteia cada página como o pipeline faria (texto nativo x precisa OCR),
    reaproveitando `extracao.precisa_vlm` e a remoção de boilerplate;
  - extrai do texto nativo, só com regex (`solufarma.triagem`): tipo, nº da CAT,
    contratante/órgão (+CNPJ), executante (TEP/Solufarma/outra), responsável
    técnico, objeto, local, período e um título sugerido;
  - confronta órgão/nº CAT do NOME do arquivo com os do conteúdo;
  - estima o custo de OCR das páginas que não têm texto nativo útil;
  - aponta duplicatas (mesmo hash ou mesmo nº de CAT no conteúdo).

Só LÊ os PDFs. Não move, não renomeia, não apaga nada.

    uv run python tools/triar_documentos.py                      # data/*.pdf + data/brutos/*.pdf
    uv run python tools/triar_documentos.py "data/x.pdf" --saida .tmp

Saída: <saida>/triagem_documentos.json e <saida>/triagem_documentos.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import pymupdf

from solufarma import config, extracao, formatos, triagem

for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

# Metadados de CAT/atestado ficam nas primeiras páginas (folha de rosto + início
# do atestado). Ler o documento inteiro só traz ruído de planilha/anexo.
PAGINAS_PARA_METADADOS = 8

# Estimativa de custo de OCR por página (VLM via OpenRouter, ADR-005).
# Não há medição real ainda (o único relatório de custo em data/relatorios/ é de
# um documento 100% nativo). Premissas:
#   entrada: imagem A4 a 1500px (~1061x1500 px / 750 ~= 2.100 tokens) + prompt
#            (~2.000 chars ~= 600 tokens) + contexto herdado (~300) ~= 3.000
#   saída:   markdown de uma página densa ~= 1.000 tokens
TOKENS_ENTRADA_POR_PAGINA = 3000
TOKENS_SAIDA_POR_PAGINA = 1000


def custo_ocr_por_pagina(
    preco_entrada: float | None = None, preco_saida: float | None = None
) -> float:
    entrada = config.PRECO_ENTRADA_USD_MTOK if preco_entrada is None else preco_entrada
    saida = config.PRECO_SAIDA_USD_MTOK if preco_saida is None else preco_saida
    return (TOKENS_ENTRADA_POR_PAGINA * entrada + TOKENS_SAIDA_POR_PAGINA * saida) / 1_000_000


def rotear_paginas(caminho: Path) -> tuple[list[str], list[str], int]:
    """
    Texto nativo e rota ('nativo' | 'ocr') de cada página, sem renderizar.

    Mesma regra do pipeline (`extracao.processar`, fase A): remove boilerplate
    repetido entre páginas (carimbo do CAU/CREA) e aplica a dupla condição de
    `precisa_vlm` (volume E densidade). A área é a da página renderizada com o
    lado maior em `config.LADO_MAIOR_PX` — igual a `formatos._carregar_pdf`.
    Devolve (textos_brutos, rotas, paginas_com_imagem).
    """
    doc = pymupdf.open(caminho)
    try:
        textos, areas, com_imagem = [], [], 0
        for pagina in doc:
            textos.append(triagem.limpar_texto(pagina.get_text() or ""))
            larg, alt = pagina.rect.width, pagina.rect.height
            zoom = config.LADO_MAIOR_PX / max(larg, alt) if max(larg, alt) else 1.0
            areas.append(int(larg * zoom) * int(alt * zoom))
            if pagina.get_images():
                com_imagem += 1
    finally:
        doc.close()

    boilerplate = extracao.detectar_boilerplate(textos)
    assinaturas = extracao.extrair_assinaturas(boilerplate)
    rotas = [
        "ocr" if extracao.precisa_vlm(extracao.limpar(t, boilerplate, assinaturas), a) else "nativo"
        for t, a in zip(textos, areas)
    ]
    return textos, rotas, com_imagem


def triar(caminho: Path) -> dict:
    registro: dict = {
        "arquivo": caminho.name,
        "caminho": str(caminho),
        "sha256": hashlib.sha256(caminho.read_bytes()).hexdigest(),
    }
    formato = formatos.sniff(caminho)
    registro["formato"] = formato
    if formato != "pdf":
        registro["erro"] = f"formato real '{formato}' — triagem só lê PDF com texto nativo"
        return registro

    textos, rotas, com_imagem = rotear_paginas(caminho)
    n_ocr = rotas.count("ocr")
    registro.update(
        paginas=len(rotas),
        paginas_nativas=len(rotas) - n_ocr,
        paginas_ocr=n_ocr,
        paginas_com_imagem=com_imagem,
        situacao_texto=(
            "nativo" if n_ocr == 0 else "escaneado" if n_ocr == len(rotas) else "parcial"
        ),
        # Texto "nativo" em página que também é imagem quase sempre é um OCR
        # antigo embutido pelo scanner — serve para triagem, mas é ruidoso.
        camada_ocr_embutida=com_imagem > 0 and len(rotas) - n_ocr > 0,
        custo_ocr_estimado_usd=round(n_ocr * custo_ocr_por_pagina(), 4),
        paginas_que_precisam_ocr=[i + 1 for i, r in enumerate(rotas) if r == "ocr"],
    )

    primeiras = textos[:PAGINAS_PARA_METADADOS]
    registro["_assinatura"] = assinatura_conteudo(textos[:3])
    md = triagem.extrair_metadados(primeiras)
    registro["metadados"] = md.como_dict()
    registro["nome_vs_conteudo"] = triagem.confrontar_nome(caminho.name, md)
    if not any(len(t.strip()) > 50 for t in primeiras):
        registro["nome_vs_conteudo"]["veredito"] = "sem texto (precisa OCR)"
    return registro


def assinatura_conteudo(textos: list[str]) -> set[str]:
    """Trigramas de palavras (>=4 letras, dobradas) — para achar quase-duplicatas."""
    palavras = re.findall(r"[A-Z]{4,}", triagem.dobrar(" ".join(textos)))
    return {" ".join(palavras[i : i + 3]) for i in range(len(palavras) - 2)}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


LIMIAR_QUASE_DUPLICATA = 0.5


def marcar_duplicatas(registros: list[dict]) -> None:
    """
    Três sinais: bytes idênticos, mesmo nº de CAT extraído do conteúdo, e texto
    das 3 primeiras páginas muito parecido (Jaccard de trigramas) — este pega o
    caso em que o nº da CAT está ilegível no OCR antigo de um dos arquivos.
    """
    por_hash: dict[str, list[str]] = {}
    por_cat: dict[str, list[str]] = {}
    for r in registros:
        por_hash.setdefault(r["sha256"], []).append(r["arquivo"])
        num = (r.get("metadados") or {}).get("numero_cat", {}).get("valor")
        if num:
            por_cat.setdefault(num.lstrip("0"), []).append(r["arquivo"])
    for r in registros:
        dup = set(por_hash[r["sha256"]]) - {r["arquivo"]}
        num = (r.get("metadados") or {}).get("numero_cat", {}).get("valor")
        mesmo_cat = set(por_cat.get((num or "").lstrip("0"), [])) - {r["arquivo"]}
        parecidos = []
        for outro in registros:
            if outro is r:
                continue
            # Formulários do CAU/CREA compartilham muito texto fixo: dois
            # documentos com nº de CAT diferentes e legíveis NÃO são duplicata.
            num_outro = (outro.get("metadados") or {}).get("numero_cat", {}).get("valor")
            if num and num_outro and num.lstrip("0") != num_outro.lstrip("0"):
                continue
            sim = jaccard(r.get("_assinatura", set()), outro.get("_assinatura", set()))
            if sim >= LIMIAR_QUASE_DUPLICATA:
                parecidos.append({"arquivo": outro["arquivo"], "similaridade": round(sim, 2)})
        r["duplicatas"] = {
            "mesmo_arquivo": sorted(dup),
            "mesmo_numero_cat_no_conteudo": sorted(mesmo_cat),
            "conteudo_parecido": parecidos,
        }
    for r in registros:
        r.pop("_assinatura", None)


# --------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------


def _v(r: dict, campo: str) -> str:
    c = (r.get("metadados") or {}).get(campo) or {}
    valor = c.get("valor")
    if not valor:
        return "—"
    marca = "" if c.get("confianca") == triagem.ALTA else " (?)"
    return str(valor).replace("|", "/").replace("\n", " ") + marca


def relatorio_md(registros: list[dict], preco_pagina: float) -> str:
    n = len(registros)
    validos = [r for r in registros if "erro" not in r]
    cont = lambda chave, valor: sum(1 for r in validos if r.get(chave) == valor)
    veredito = lambda v: sum(1 for r in validos if r["nome_vs_conteudo"]["veredito"] == v)
    grupos: dict[str, int] = {}
    for r in validos:
        g = r["metadados"]["executante_grupo"]["valor"] or "não encontrada"
        grupos[g] = grupos.get(g, 0) + 1
    pags_ocr = sum(r.get("paginas_ocr", 0) for r in validos)
    custo = sum(r.get("custo_ocr_estimado_usd", 0) for r in validos)

    embutida = sum(1 for r in validos if r.get("camada_ocr_embutida"))
    linha_texto = (
        f"- Texto: **{cont('situacao_texto', 'nativo')} nativos**, "
        f"**{cont('situacao_texto', 'parcial')} parciais**, "
        f"**{cont('situacao_texto', 'escaneado')} escaneados** "
        f"({embutida} com camada de OCR antiga embutida)"
    )
    linha_nome = (
        f"- Nome do arquivo x conteúdo: **{veredito('bate')} batem**, "
        f"**{veredito('trocado')} trocados**, {veredito('inconclusivo')} inconclusivos, "
        f"{veredito('sem texto (precisa OCR)')} sem texto"
    )
    linha_custo = (
        f"- OCR pendente: **{pags_ocr} páginas**, custo estimado **US$ {custo:.2f}** "
        f"(US$ {preco_pagina:.4f}/página — premissa de {TOKENS_ENTRADA_POR_PAGINA} tokens de "
        f"entrada e {TOKENS_SAIDA_POR_PAGINA} de saída a US$ {config.PRECO_ENTRADA_USD_MTOK}/"
        f"US$ {config.PRECO_SAIDA_USD_MTOK} por MTok; não medido)"
    )
    linhas_tabela_preco = []
    if (config.PRECO_ENTRADA_USD_MTOK, config.PRECO_SAIDA_USD_MTOK) != (3.0, 15.0):
        linhas_tabela_preco.append(
            "  - a preço de tabela (US$ 3/US$ 15 por MTok, sem desconto de lançamento): "
            f"**US$ {pags_ocr * custo_ocr_por_pagina(3.0, 15.0):.2f}**"
        )

    linhas = [
        "# Triagem de documentos pelo conteúdo",
        "",
        (
            f"Gerado em {datetime.now(UTC):%Y-%m-%d %H:%M} UTC por "
            "`tools/triar_documentos.py` — zero chamadas pagas (regex sobre texto nativo)."
        ),
        "",
        "## Resumo",
        "",
        f"- Documentos: **{n}** ({n - len(validos)} com erro de leitura)",
        linha_texto,
        linha_nome,
        "- Executante: " + ", ".join(f"**{k}**: {v}" for k, v in sorted(grupos.items())),
        linha_custo,
        *linhas_tabela_preco,
        "",
        "`(?)` = confiança média (inferido), `—` = não encontrado. Confira no PDF antes de indexar.",
        "",
        "## Nome x conteúdo",
        "",
        "| # | arquivo | veredito | nº CAT (conteúdo) | órgão (conteúdo) | executante | motivos |",
        "|---:|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(registros, 1):
        if "erro" in r:
            linhas.append(f"| {i} | {r['arquivo']} | ERRO | | | | {r['erro']} |")
            continue
        nv = r["nome_vs_conteudo"]
        linhas.append(
            f"| {i} | {r['arquivo']} | **{nv['veredito']}** | {_v(r, 'numero_cat')} | "
            f"{_v(r, 'orgao')} | {_v(r, 'executante_grupo')} | {'; '.join(nv['motivos'])} |"
        )

    linhas += [
        "",
        "## Texto nativo x OCR",
        "",
        "| # | arquivo | páginas | nativas | precisam OCR | situação | custo OCR (US$) |",
        "|---:|---|---:|---:|---:|---|---:|",
    ]
    for i, r in enumerate(registros, 1):
        if "erro" in r:
            continue
        linhas.append(
            f"| {i} | {r['arquivo']} | {r['paginas']} | {r['paginas_nativas']} | "
            f"{r['paginas_ocr']} | {r['situacao_texto']}"
            f"{' (OCR antigo embutido)' if r['camada_ocr_embutida'] else ''} | "
            f"{r['custo_ocr_estimado_usd']:.2f} |"
        )

    linhas += [
        "",
        "## Metadados extraídos",
        "",
        (
            "| # | título sugerido | contratante (bruto) | CNPJ contratante | executante (bruto) | "
            "responsável técnico | local | período |"
        ),
        "|---:|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(registros, 1):
        if "erro" in r:
            continue
        linhas.append(
            f"| {i} | {_v(r, 'titulo_sugerido')} | {_v(r, 'contratante')} | "
            f"{_v(r, 'contratante_cnpj')} | {_v(r, 'executante')} | "
            f"{_v(r, 'responsavel_tecnico')} | {_v(r, 'local')} | {_v(r, 'periodo')} |"
        )

    dups = [r for r in validos if any(r["duplicatas"].values())]
    linhas += ["", "## Duplicatas", ""]
    if not dups:
        linhas.append("Nenhuma.")
    for r in dups:
        d = r["duplicatas"]
        if d["mesmo_arquivo"]:
            linhas.append(f"- {r['arquivo']}: bytes idênticos a {', '.join(d['mesmo_arquivo'])}")
        if d["mesmo_numero_cat_no_conteudo"]:
            linhas.append(
                f"- {r['arquivo']}: mesmo nº de CAT no conteúdo "
                f"({r['metadados']['numero_cat']['valor']}) que "
                f"{', '.join(d['mesmo_numero_cat_no_conteudo'])}"
            )
        for par in d["conteudo_parecido"]:
            linhas.append(
                f"- {r['arquivo']}: texto das 3 primeiras páginas {par['similaridade']:.0%} "
                f"igual ao de {par['arquivo']}"
            )
    return "\n".join(linhas) + "\n"


def _coletar(entradas: list[str]) -> list[Path]:
    if not entradas:
        dados = RAIZ / "data"
        # Windows: glob é case-insensitive, mas no Linux ".PDF" escaparia.
        candidatos = list(dados.glob("*")) + list((dados / "brutos").glob("*"))
        return sorted(p for p in candidatos if p.is_file() and p.suffix.lower() == ".pdf")
    arquivos: list[Path] = []
    for e in entradas:
        p = Path(e)
        if p.is_dir():
            arquivos += sorted(x for x in p.iterdir() if x.suffix.lower() == ".pdf")
        elif p.is_file():
            arquivos.append(p)
        else:
            print(f"aviso: {e} não existe, ignorando", file=sys.stderr)
    return arquivos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Triagem de PDFs pelo conteúdo (sem custo).")
    ap.add_argument("entradas", nargs="*", help="PDFs ou pastas (padrão: data/ e data/brutos/)")
    ap.add_argument("--saida", type=Path, default=RAIZ / ".tmp", help="padrão: .tmp/")
    args = ap.parse_args(argv)

    arquivos = _coletar(args.entradas)
    if not arquivos:
        print("Nenhum PDF encontrado.", file=sys.stderr)
        return 1

    registros = []
    for caminho in arquivos:
        try:
            r = triar(caminho)
        except Exception as exc:  # noqa: BLE001 — um PDF quebrado não derruba o lote
            r = {
                "arquivo": caminho.name,
                "caminho": str(caminho),
                "sha256": "",
                "erro": f"{type(exc).__name__}: {exc}",
            }
        veredito = r.get("nome_vs_conteudo", {}).get("veredito", r.get("erro", ""))
        print(f"{caminho.name}: {r.get('situacao_texto', '?')} | {veredito}")
        registros.append(r)
    marcar_duplicatas(registros)

    args.saida.mkdir(parents=True, exist_ok=True)
    preco = custo_ocr_por_pagina()
    saida_json = args.saida / "triagem_documentos.json"
    saida_md = args.saida / "triagem_documentos.md"
    saida_json.write_text(
        json.dumps(
            {
                "gerado_em": datetime.now(UTC).isoformat(),
                "custo_ocr_usd_por_pagina": round(preco, 5),
                "premissa_custo": {
                    "tokens_entrada_por_pagina": TOKENS_ENTRADA_POR_PAGINA,
                    "tokens_saida_por_pagina": TOKENS_SAIDA_POR_PAGINA,
                    "preco_entrada_usd_mtok": config.PRECO_ENTRADA_USD_MTOK,
                    "preco_saida_usd_mtok": config.PRECO_SAIDA_USD_MTOK,
                    "modelo": config.OPENROUTER_MODELO,
                },
                "documentos": registros,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    saida_md.write_text(relatorio_md(registros, preco), encoding="utf-8")
    print(f"\n{len(registros)} documento(s) -> {saida_json} e {saida_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
