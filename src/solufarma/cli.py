"""
cli.py — Entrypoints de linha de comando.

Os scripts em `tools/` são invólucros finos sobre estas funções, conforme o
framework WAT do CLAUDE.md. A lógica mora nos módulos do pacote; aqui só há
parsing de argumento, validação de ambiente e impressão.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from solufarma import chunking, config, extracao

EXTENSOES_ACEITAS = {".pdf", ".zip", ".jpg", ".jpeg", ".png"}


def _coletar(entradas: list[Path]) -> list[Path]:
    """Expande diretórios em arquivos. Aceita mistura de arquivo e pasta."""
    arquivos: list[Path] = []
    for entrada in entradas:
        if entrada.is_dir():
            arquivos.extend(
                sorted(
                    p
                    for p in entrada.iterdir()
                    if p.is_file() and p.suffix.lower() in EXTENSOES_ACEITAS
                )
            )
        elif entrada.is_file():
            arquivos.append(entrada)
        else:
            print(f"aviso: {entrada} não existe, ignorando", file=sys.stderr)
    return arquivos


def main_extrair(argv: list[str] | None = None) -> int:
    """OCR sobre data/brutos/ -> data/extraidos/"""
    ap = argparse.ArgumentParser(
        prog="solufarma-extrair",
        description="Extrai markdown estruturado de documentos do acervo.",
    )
    ap.add_argument(
        "entradas",
        nargs="*",
        type=Path,
        help="arquivos ou diretórios (padrão: data/brutos/)",
    )
    ap.add_argument("--saida", type=Path, default=None, help="padrão: data/extraidos/")
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args(argv)

    # Falha ANTES de abrir arquivo ou gastar chamada paga.
    try:
        config.exigir("extracao")
    except config.ConfiguracaoInvalida as e:
        print(f"\nERRO DE CONFIGURAÇÃO\n\n{e}\n", file=sys.stderr)
        return 2

    config.criar_diretorios()
    entradas = args.entradas or [config.DIR_BRUTOS]
    saida = args.saida or config.DIR_EXTRAIDOS

    arquivos = _coletar(entradas)
    if not arquivos:
        print(
            f"Nenhum documento encontrado em {', '.join(str(e) for e in entradas)}.\n"
            f"Coloque os PDFs em {config.DIR_BRUTOS} e rode de novo.",
            file=sys.stderr,
        )
        return 1

    print(f"{len(arquivos)} documento(s) | {config.resumo()}")
    _, falhos = extracao.processar_lote(arquivos, saida, verboso=not args.silencioso)
    return 1 if falhos else 0


def main_chunks(argv: list[str] | None = None) -> int:
    """Chunking sobre data/extraidos/ -> data/chunks/"""
    ap = argparse.ArgumentParser(
        prog="solufarma-chunks",
        description="Costura e corta o markdown extraído em chunks.",
    )
    ap.add_argument(
        "entradas",
        nargs="*",
        type=Path,
        help="JSONs de extração ou diretórios (padrão: data/extraidos/)",
    )
    ap.add_argument("--saida", type=Path, default=None, help="padrão: data/chunks/")
    args = ap.parse_args(argv)

    # Chunking não faz chamada paga — não exige credencial nenhuma.
    config.criar_diretorios()
    entradas = args.entradas or [config.DIR_EXTRAIDOS]
    saida = args.saida or config.DIR_CHUNKS
    saida.mkdir(parents=True, exist_ok=True)

    jsons: list[Path] = []
    for entrada in entradas:
        jsons.extend(sorted(entrada.glob("*.json")) if entrada.is_dir() else [entrada])
    if not jsons:
        print(f"Nenhum JSON de extração em {entradas}. Rode a extração antes.", file=sys.stderr)
        return 1

    for caminho in jsons:
        doc = json.loads(caminho.read_text(encoding="utf-8"))
        chunks, itens = chunking.chunkar_documento(doc)

        (saida / f"{caminho.stem}_chunks.json").write_text(
            json.dumps([asdict(c) for c in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (saida / f"{caminho.stem}_itens.json").write_text(
            json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        por_tipo: dict[str, int] = {}
        for c in chunks:
            por_tipo[c.tipo] = por_tipo.get(c.tipo, 0) + 1
        media = sum(c.n_chars for c in chunks) / max(len(chunks), 1)
        prosa = [c for c in chunks if c.tipo == "prosa"]
        pct_tamanho = (
            100 * sum(1 for c in prosa if c.cortado_por_tamanho) / len(prosa) if prosa else 0
        )

        print(
            f"{caminho.name}: {len(chunks)} chunks {por_tipo}, média {media:.0f} chars, "
            f"{pct_tamanho:.0f}% da prosa cortada por tamanho"
        )
        print(f"  + {len(itens)} linhas de planilha para a tabela relacional")

    return 0


if __name__ == "__main__":
    raise SystemExit(main_extrair())
