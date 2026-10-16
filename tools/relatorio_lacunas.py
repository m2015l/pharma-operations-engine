"""Lista as células que o OCR NÃO conseguiu ler — as tapadas por carimbo.

Uso:
    python tools/relatorio_lacunas.py                  # todos os documentos
    python tools/relatorio_lacunas.py --doc BIOPHARMA  # filtra por nome
    python tools/relatorio_lacunas.py --exportar lacunas.json   # arquivo para preencher
    python tools/relatorio_lacunas.py --aplicar lacunas.json    # devolve os valores

POR QUE ESTE ARQUIVO EXISTE
Uma célula vazia por carimbo e uma célula vazia de cabeçalho de seção são
idênticas no dado. `chunking.classificar_lacuna()` separa as duas usando a
confiança da página e a observação do próprio modelo, que enumera as linhas que
não conseguiu ler. Este relatório mostra o resultado com a POSIÇÃO exata, para
que os valores possam ser preenchidos à mão a partir do documento original.

O QUE CADA STATUS SIGNIFICA
    ilegivel — o modelo declarou que não leu ESTA linha. O valor existe no
               papel. É o que vale a pena preencher;
    suspeita — a página veio com confiança baixa e o modelo não disse quais
               linhas. Precisa de olhada humana na página inteira;
    vazio    — vazio legítimo (cabeçalho de seção). Não aparece aqui.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIR_CHUNKS = RAIZ / "data" / "chunks"

PRECISAM_ATENCAO = ("ilegivel", "suspeita")


def _carregar(filtro: str | None) -> list[tuple[str, list[dict]]]:
    saida = []
    for caminho in sorted(DIR_CHUNKS.glob("*_itens.json")):
        nome = caminho.name.removesuffix("_itens.json")
        if filtro and filtro.lower() not in nome.lower():
            continue
        saida.append((nome, json.loads(caminho.read_text(encoding="utf-8"))))
    return saida


def _colunas_vazias(celulas: list[str]) -> list[int]:
    return [i for i, c in enumerate(celulas) if not str(c or "").strip()]


def _descricao(celulas: list[str]) -> str:
    """A célula mais longa é a descrição — a mais informativa para localizar."""
    preenchidas = [c for c in celulas if str(c or "").strip()]
    return max(preenchidas, key=len) if preenchidas else ""


def listar(nome: str, itens: list[dict]) -> list[dict]:
    lacunas = []
    for pos, item in enumerate(itens):
        if item.get("status") not in PRECISAM_ATENCAO:
            continue
        celulas = item.get("celulas") or []
        lacunas.append(
            {
                "documento": nome,
                "indice": pos,  # posição no *_itens.json, para o --aplicar
                "pagina": item.get("pagina"),
                "secao": item.get("secao") or "",
                "status": item.get("status"),
                "confianca": item.get("confianca"),
                "codigo": str(celulas[0]).strip() if celulas else "",
                "descricao": _descricao(celulas),
                "celulas": celulas,
                "colunas_vazias": _colunas_vazias(celulas),
                "observacao_da_pagina": item.get("observacoes") or "",
            }
        )
    return lacunas


def _imprimir(nome: str, itens: list[dict]) -> list[dict]:
    lacunas = listar(nome, itens)
    marcados = sum(1 for i in itens if i.get("status"))
    sem_status = len(itens) - marcados
    print(f"\n### {nome}")
    sufixo = f"  ({sem_status} sem status — chunking anterior à mudança)" if sem_status else ""
    print(f"  {len(itens)} linhas de planilha{sufixo}")
    if not lacunas:
        print("  nenhuma lacuna: tudo lido, ou vazio legítimo")
        return []

    por_pagina: dict[int, list[dict]] = {}
    for lac in lacunas:
        por_pagina.setdefault(lac["pagina"], []).append(lac)

    for pagina, linhas in sorted(por_pagina.items()):
        conf = linhas[0]["confianca"]
        print(f"\n  página {pagina} (confiança {conf}) — {len(linhas)} linha(s):")
        for lac in linhas:
            faltando = ", ".join(f"col {i + 1}" for i in lac["colunas_vazias"])
            codigo = lac["codigo"] or "?"
            print(f"    [{lac['status']}] item {codigo} — {lac['descricao'][:52]}")
            print(f"        células: {lac['celulas']}   faltando: {faltando}")
        if linhas[0]["observacao_da_pagina"]:
            print(f"        obs do modelo: {linhas[0]['observacao_da_pagina'][:200]}")
    return lacunas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc", default=None, help="filtra por trecho do nome do documento")
    ap.add_argument("--exportar", type=Path, default=None, help="grava JSON para preencher")
    ap.add_argument("--aplicar", type=Path, default=None, help="lê o JSON preenchido e grava")
    args = ap.parse_args()

    if args.aplicar:
        return aplicar(args.aplicar)

    documentos = _carregar(args.doc)
    if not documentos:
        print("Nenhum *_itens.json em data/chunks/. Rode tools/chunk_document.py antes.")
        return 1

    todas: list[dict] = []
    for nome, itens in documentos:
        todas.extend(_imprimir(nome, itens))

    print("\n" + "=" * 70)
    ilegiveis = sum(1 for lac in todas if lac["status"] == "ilegivel")
    suspeitas = len(todas) - ilegiveis
    print(f"TOTAL: {len(todas)} linha(s) — {ilegiveis} ilegível(is), {suspeitas} suspeita(s)")

    if args.exportar:
        modelo = [
            {
                "documento": lac["documento"],
                "indice": lac["indice"],
                "pagina": lac["pagina"],
                "codigo": lac["codigo"],
                "descricao": lac["descricao"],
                "celulas_atuais": lac["celulas"],
                "celulas_corrigidas": lac["celulas"],  # <- edite aqui
            }
            for lac in todas
        ]
        args.exportar.write_text(
            json.dumps(modelo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Arquivo para preencher: {args.exportar}")
        print("Edite `celulas_corrigidas` e rode com --aplicar.")
    return 0


def aplicar(caminho: Path) -> int:
    """Grava os valores preenchidos à mão de volta nos *_itens.json."""
    correcoes = json.loads(caminho.read_text(encoding="utf-8"))
    por_documento: dict[str, list[dict]] = {}
    for c in correcoes:
        por_documento.setdefault(c["documento"], []).append(c)

    total = 0
    for nome, lista in por_documento.items():
        destino = DIR_CHUNKS / f"{nome}_itens.json"
        if not destino.is_file():
            print(f"aviso: {destino.name} não existe, pulando", file=sys.stderr)
            continue
        itens = json.loads(destino.read_text(encoding="utf-8"))
        for c in lista:
            novas = c.get("celulas_corrigidas") or []
            if novas == c.get("celulas_atuais"):
                continue  # não foi preenchido
            item = itens[c["indice"]]
            # Confere que o alvo não mudou: um rechunk entre o export e o
            # aplicar reordena os índices, e gravar no índice antigo escreveria
            # o valor na linha errada — em silêncio.
            if item.get("celulas") != c.get("celulas_atuais"):
                print(
                    f"ERRO: a linha {c['indice']} de {nome} mudou desde a exportação. "
                    "Rode o relatório de novo.",
                    file=sys.stderr,
                )
                return 1
            item["celulas"] = novas
            item["status"] = "corrigido_manual"
            total += 1
        destino.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{total} linha(s) corrigida(s). Rode tools/indexar.py para levar ao banco.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
