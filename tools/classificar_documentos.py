#!/usr/bin/env python
"""
tools/classificar_documentos.py — Classificação + resumo de cada documento via LLM
(item 19 do plano; lógica em `src/solufarma/classificacao.py`).

Lê os chunks do documento no Supabase (texto já extraído — nada de PDF/OCR),
chama o LLM uma vez por documento, valida a saída em código e grava
`documentos.classificacao` (jsonb) + `documentos.resumo`.

INCREMENTAL: só processa documento sem classificação, ou cuja classificação foi
feita sobre um texto que mudou depois (rechunk/reindexação muda o hash). Use
`--refazer` para forçar.

    uv run python tools/classificar_documentos.py --dry-run          # custo estimado, sem LLM
    uv run python tools/classificar_documentos.py --documento <uuid> # um documento
    uv run python tools/classificar_documentos.py                    # todos os pendentes
    uv run python tools/classificar_documentos.py --refazer --teto-usd 0.50

Modelo: `--modelo` ou CLASSIFICACAO_MODELO no .env (padrão abaixo). O custo
REAL de cada chamada vem do OpenRouter (`usage.cost`) e é somado contra o
`--teto-usd`: a execução para antes de passar do teto.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from dotenv import load_dotenv

from solufarma import classificacao as cl

for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

# Escolhido em 29/09 comparando com o texto em 2 documentos (CAT SJC-02085 com
# OCR ruidoso + atestado dos Vestiários/FIOCRUZ). gemini-2.5-flash-lite custa
# ~40% disso e acertou os fatos (valor, período, executante), mas errou mais nos
# vocabulários que viram filtro (vacina -> "farmacêutica", "hidráulica" sem
# evidência, CLP sem "automação"). Diferença: ~US$ 0,003 por documento.
# Trocar = CLASSIFICACAO_MODELO no .env, sem tocar em código.
MODELO_PADRAO = "google/gemini-3.1-flash-lite"

# US$ por milhão de tokens (entrada, saída), tabela do OpenRouter em 29/09/26.
# Só serve para o --dry-run; o custo real vem da resposta da API.
PRECOS = {
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "google/gemini-3.1-flash-lite": (0.25, 1.50),
    "google/gemini-2.5-flash": (0.30, 2.50),
    "deepseek/deepseek-v4-flash": (0.076, 0.153),
    "openai/gpt-5-mini": (0.25, 2.00),
    "anthropic/claude-sonnet-5": (2.00, 10.00),
}


def _precos(modelo: str) -> tuple[float, float]:
    ent, sai = os.getenv("CLASSIFICACAO_PRECO_ENTRADA"), os.getenv("CLASSIFICACAO_PRECO_SAIDA")
    if ent and sai:
        return float(ent), float(sai)
    # Modelo desconhecido: estima pelo mais caro da tabela (lado seguro).
    return PRECOS.get(modelo, max(PRECOS.values()))


def selecionar(docs: list[dict], ids: list[str], refazer: bool, conn) -> list[dict]:
    escolhidos = []
    for d in docs:
        if ids and d["id"] not in ids:
            continue
        if d["n_chunks"] == 0:
            print(f"  pulado (sem chunks): {d['titulo']}")
            continue
        d["chunks"] = cl.carregar_chunks(conn, d["id"])
        d["hash_atual"] = cl.hash_conteudo(d["chunks"])
        desatualizado = d["classificado"] and d["hash_classificado"] != d["hash_atual"]
        if refazer or not d["classificado"] or desatualizado:
            d["motivo"] = (
                "refazer"
                if (refazer and d["classificado"] and not desatualizado)
                else "texto mudou"
                if desatualizado
                else "novo"
            )
            escolhidos.append(d)
    return escolhidos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="só estima custo; não chama LLM")
    ap.add_argument("--refazer", action="store_true", help="reclassifica mesmo os já feitos")
    ap.add_argument("--documento", action="append", default=[], help="uuid (pode repetir)")
    ap.add_argument("--limite", type=int, default=0, help="no máximo N documentos")
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--teto-usd", type=float, default=1.00, help="para ao atingir este gasto")
    ap.add_argument("--max-chars", type=int, default=cl.MAX_CHARS_PADRAO)
    ap.add_argument("--nao-gravar", action="store_true", help="chama o LLM mas não grava no banco")
    ap.add_argument("--saida", default=str(RAIZ / ".tmp" / "classificacao_documentos.json"))
    args = ap.parse_args()

    load_dotenv(RAIZ / ".env")
    from solufarma_rag.db.repository import criar_conexao

    modelo = args.modelo or os.getenv("CLASSIFICACAO_MODELO") or MODELO_PADRAO
    preco_ent, preco_sai = _precos(modelo)
    conn = criar_conexao()
    docs = selecionar(cl.listar_documentos(conn), args.documento, args.refazer, conn)
    if args.limite:
        docs = docs[: args.limite]
    if not docs:
        print("Nada a classificar: todos os documentos estão em dia.")
        return 0

    print(
        f"Modelo: {modelo}  (US$ {preco_ent}/{preco_sai} por Mtok)  teto: US$ {args.teto_usd:.2f}"
    )
    total_est = 0.0
    for d in docs:
        msg, _, trunc = cl.preparar(d["chunks"], d["titulo"], args.max_chars)
        tokens = cl.estimar_tokens(cl.SYSTEM_PROMPT + msg)
        d["custo_est"] = cl.estimar_custo(tokens, preco_ent, preco_sai)
        total_est += d["custo_est"]
        print(
            f"  [{d['motivo']:>11}] {d['titulo'][:70]:<70} {d['n_chunks']:>4} chunks "
            f"~{tokens:>6} tok  ~US$ {d['custo_est']:.4f}{'  (truncado)' if trunc else ''}"
        )
    print(f"Estimado: {len(docs)} documento(s), ~US$ {total_est:.4f}")
    if args.dry_run:
        return 0

    from solufarma_rag.agent.llm import OpenRouterLLM

    llm = OpenRouterLLM(model=modelo, json_mode=True, temperatura=0)
    gasto, relatorio = 0.0, []
    for i, d in enumerate(docs, 1):
        if gasto + d["custo_est"] > args.teto_usd:
            print(f"PARANDO: o próximo documento passaria do teto (gasto US$ {gasto:.4f}).")
            break
        print(f"\n[{i}/{len(docs)}] {d['titulo']}")
        try:
            res = cl.classificar_documento(
                llm, d["chunks"], d["titulo"], modelo=modelo, max_chars=args.max_chars
            )
        except Exception as exc:  # noqa: BLE001 — um documento ruim não derruba o lote
            print(f"  ERRO: {exc}")
            relatorio.append({"id": d["id"], "titulo": d["titulo"], "erro": str(exc)})
            continue
        custo = res.uso.get("custo_usd")
        gasto += custo if custo is not None else d["custo_est"]
        c = res.classificacao
        print(
            f"  tipo={(c['tipo_documento'] or {}).get('valor')}  "
            f"grupo={(c['executante_grupo'] or {}).get('valor')}  "
            f"disciplinas={[x['valor'] for x in c['disciplinas']]}"
        )
        print(f"  custo real: US$ {custo}  | acumulado: US$ {gasto:.4f}")
        for a in res.avisos:
            print(f"  aviso: {a}")
        if not args.nao_gravar:
            cl.salvar(conn, d["id"], c, res.resumo)
        relatorio.append(
            {"id": d["id"], "titulo": d["titulo"], "classificacao": c, "resumo": res.resumo}
        )

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGasto desta execução: US$ {gasto:.4f}. Relatório: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
