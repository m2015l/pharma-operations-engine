#!/usr/bin/env python
"""
tools/checar_modelo.py — Confere o slug e o preço do modelo antes de gastar.

Consulta o catálogo público do OpenRouter (grátis, não consome crédito) e
compara com o que está no `.env`. Rode sempre que trocar `OPENROUTER_MODELO`:
slug certo com preço errado faz o relatório de custo mentir em silêncio, que é
justamente o modo de falha que este projeto combate.

    uv run python tools/checar_modelo.py

Sai com código 1 se o slug não existir ou o preço divergir.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests

from solufarma import config

CATALOGO = "https://openrouter.ai/api/v1/models"
TOLERANCIA = 0.01  # US$ por MTok


def main() -> int:
    alvo = config.OPENROUTER_MODELO
    try:
        resposta = requests.get(CATALOGO, timeout=60)
        resposta.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"não foi possível consultar o catálogo: {e}", file=sys.stderr)
        return 1

    modelos = {m["id"]: m for m in resposta.json().get("data", [])}

    if alvo not in modelos:
        print(f"SLUG NÃO EXISTE: {alvo}\n")
        print("Candidatos Claude com visão:")
        for slug in sorted(k for k in modelos if "claude" in k):
            preco = modelos[slug].get("pricing", {})
            entrada = float(preco.get("prompt", 0)) * 1e6
            saida = float(preco.get("completion", 0)) * 1e6
            print(f"  {slug:<45} ${entrada:.2f} / ${saida:.2f} por MTok")
        print("\nAjuste OPENROUTER_MODELO no .env.")
        return 1

    preco = modelos[alvo].get("pricing", {})
    entrada = float(preco.get("prompt", 0)) * 1e6
    saida = float(preco.get("completion", 0)) * 1e6

    print(f"slug   : {alvo}  (existe)")
    print(f"catálogo: ${entrada:.2f} entrada / ${saida:.2f} saída por MTok")
    print(
        f".env    : ${config.PRECO_ENTRADA_USD_MTOK:.2f} entrada / "
        f"${config.PRECO_SAIDA_USD_MTOK:.2f} saída por MTok"
    )

    divergente = (
        abs(entrada - config.PRECO_ENTRADA_USD_MTOK) > TOLERANCIA
        or abs(saida - config.PRECO_SAIDA_USD_MTOK) > TOLERANCIA
    )
    if divergente:
        print(
            "\nPREÇOS DIVERGEM — corrija o .env, senão o relatório de custo mente:\n"
            f"  OPENROUTER_PRECO_ENTRADA={entrada:.2f}\n"
            f"  OPENROUTER_PRECO_SAIDA={saida:.2f}"
        )
        return 1

    print("\nOK — slug e preços conferem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
