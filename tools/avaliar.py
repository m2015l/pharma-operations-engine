"""Mede a qualidade do retrieval contra o golden set — o A/B Voyage x OpenAI.

Uso:
    python tools/avaliar.py --provedor voyage --salvar
    python tools/avaliar.py --provedor openai --salvar
    python tools/avaliar.py --comparar          # confronta as execuções salvas

    python tools/avaliar.py --lexico            # só full-text, sem embedding

POR QUE ESTE ARQUIVO EXISTE
A escolha do modelo de embeddings estava em aberto desde 09/08 e não dava para
resolver por argumento: os dois são plausíveis, e a diferença aparece no acervo
real ou não aparece em lugar nenhum. Vetorizar o acervo inteiro custa US$ 0,00
na Voyage e ~US$ 0,17 na OpenAI, então medir é literalmente mais barato do que
continuar discutindo.

O QUE ELE MEDE
Recall@k por página: a pergunta recuperou algum trecho vindo de uma página que
sabidamente contém a resposta? Página, e não chunk, porque o chunking pode
mudar sem invalidar o golden set — amarrar o gabarito a um chunk_index tornaria
o conjunto descartável a cada reajuste do chunker.

O controle negativo (`esperado_paginas: []`) é tão importante quanto o resto:
mede se o piso de relevância está segurando. Um modelo que acerta tudo mas
também "acha" resposta para usina nuclear não está pronto.

FLUXO COMPLETO DO A/B
    1. generate_embeddings.py --provedor voyage --reset --sim
    2. avaliar.py --provedor voyage --salvar
    3. generate_embeddings.py --provedor openai --reset --sim
    4. avaliar.py --provedor openai --salvar
    5. avaliar.py --comparar
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from solufarma_rag.db.repository import (
    FiltrosBusca,
    SupabaseChunkRepository,
    criar_conexao,
)
from solufarma_rag.ingestion.embeddings import criar_provedor
from solufarma_rag.retrieval.hybrid_search import HybridSearcher

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


GOLDEN = RAIZ / "data" / "golden_set.json"
DIR_RESULTADOS = RAIZ / "data" / "relatorios"


def _paginas_cobertas(chunk) -> set[int]:
    """Todas as páginas que o chunk atravessa — ele pode cruzar a fronteira."""
    return set(range(chunk.pagina_inicio, chunk.pagina_fim + 1))


def _acertou(resultados, esperado: list[int]) -> bool:
    """Algum trecho recuperado veio de uma página esperada?"""
    if not esperado:
        # Controle negativo: acertar é NÃO recuperar nada.
        return not resultados
    faixa = set(range(esperado[0], esperado[-1] + 1)) if len(esperado) == 2 else set(esperado)
    return any(_paginas_cobertas(r.chunk) & faixa for r in resultados)


def avaliar(buscar, casos: list[dict], top_k: int) -> dict:
    linhas = []
    for caso in casos:
        resultados = buscar(caso["pergunta"], top_k)
        ok = _acertou(resultados, caso["esperado_paginas"])
        paginas = sorted({p for r in resultados for p in _paginas_cobertas(r.chunk)})
        linhas.append(
            {
                "pergunta": caso["pergunta"],
                "esperado": caso["esperado_paginas"],
                "recuperou_paginas": paginas,
                "n_resultados": len(resultados),
                "melhor_score": round(resultados[0].score, 5) if resultados else 0.0,
                "acertou": ok,
                "negativo": not caso["esperado_paginas"],
            }
        )

    positivos = [linha for linha in linhas if not linha["negativo"]]
    negativos = [linha for linha in linhas if linha["negativo"]]
    return {
        "linhas": linhas,
        "recall": sum(linha["acertou"] for linha in positivos) / max(len(positivos), 1),
        "acertos": sum(linha["acertou"] for linha in positivos),
        "total": len(positivos),
        "negativos_ok": sum(linha["acertou"] for linha in negativos),
        "negativos_total": len(negativos),
    }


def calibrar(repo, provider, casos: list[dict], pool: int) -> None:
    """Deriva o piso de similaridade dos scores medidos — não de chute.

    O QUE O PISO FAZ — e o que ele NÃO faz
    Ele decide se o acervo responde ou diz "não encontrei". É uma separação
    entre PERGUNTAS, não entre trechos: pergunta respondível passa, pergunta
    sem resposta no acervo volta vazia.

    Ele NÃO serve para limpar trechos irrelevantes de dentro de um resultado bom.
    Se a pergunta certa recupera 5 trechos e só 2 prestam, isso é ordenação —
    trabalho do reranker, cujo gancho já existe em HybridSearcher. Subir o piso
    para resolver isso corta resposta certa junto.

    O MÉTODO
    Roda a busca vetorial SEM piso (0.0) e mede duas distribuições:

      sinal    — em cada pergunta RESPONDÍVEL, o melhor score de um trecho
                 vindo de página esperada. É o que o piso precisa deixar passar.
      teto-não — em cada pergunta do CONTROLE NEGATIVO (resposta não existe no
                 acervo), o melhor score de qualquer trecho. É o que o piso
                 precisa barrar.

    Piso bom: acima do maior teto-não, abaixo do menor sinal.

    O melhor distrator das perguntas respondíveis é medido e exibido também, mas
    NÃO entra na conta do piso — é o diagnóstico de quanto o reranker teria a
    ganhar.

    POR QUE NÃO DÁ PARA CHUTAR
    A similaridade de cosseno tem escala própria por modelo. O 0.15 histórico
    veio do provedor fake (bag-of-words), onde vetores esparsos produzem
    cossenos baixos. Um modelo denso real põe quase tudo numa faixa estreita e
    alta — 0.15 lá dentro não filtra nada, e o acervo passa a "responder"
    qualquer pergunta.
    """
    from solufarma_rag.ingestion.embeddings import embeddar_consulta

    sinais: list[tuple[float, str]] = []
    tetos_nao: list[tuple[float, str]] = []
    distratores: list[tuple[float, str]] = []

    print(f"\n{'=' * 72}\nCALIBRAÇÃO DO PISO — {provider.model_id}\n{'=' * 72}")

    for caso in casos:
        vetor = embeddar_consulta(provider, caso["pergunta"])
        brutos = repo.buscar_vetorial(vetor, FiltrosBusca(), pool, 0.0)
        rotulo_caso = caso["pergunta"][:56]

        if not brutos:
            print(f"\n  {rotulo_caso}\n      (nenhum trecho recuperado)")
            continue

        esperado = caso["esperado_paginas"]

        if not esperado:
            # Controle negativo: TUDO que ele recupera é falso positivo. O melhor
            # score aqui é o teto que o piso precisa ficar acima.
            teto = brutos[0][1]
            tetos_nao.append((teto, caso["pergunta"]))
            print(f"\n  {rotulo_caso}   (controle negativo)")
            print(f"      melhor score (a barrar): {teto:.4f}")
            continue

        faixa = set(range(esperado[0], esperado[-1] + 1)) if len(esperado) == 2 else set(esperado)
        melhor_sinal = next(
            (s for c, s in brutos if _paginas_cobertas(c) & faixa), None
        )
        melhor_distrator = next(
            (s for c, s in brutos if not (_paginas_cobertas(c) & faixa)), None
        )
        if melhor_sinal is not None:
            sinais.append((melhor_sinal, caso["pergunta"]))
        if melhor_distrator is not None:
            distratores.append((melhor_distrator, caso["pergunta"]))

        s = f"{melhor_sinal:.4f}" if melhor_sinal is not None else "  —   "
        d = f"{melhor_distrator:.4f}" if melhor_distrator is not None else "  —   "
        ordem = "sinal em 1º" if brutos and melhor_sinal == brutos[0][1] else "distrator na frente"
        print(f"\n  {rotulo_caso}")
        print(f"      sinal: {s}   melhor distrator: {d}   ({ordem})")

    print(f"\n{'-' * 72}")
    if not sinais:
        print("Nenhum sinal recuperado. O piso não é o problema — reveja o modelo,")
        print("os embeddings gravados, ou as páginas esperadas do golden set.")
        return

    menor_sinal, pergunta_pior = min(sinais, key=lambda t: t[0])
    maior_nao, pergunta_nao = max(tetos_nao, key=lambda t: t[0]) if tetos_nao else (0.0, "—")

    print(f"Menor sinal a preservar : {menor_sinal:.4f}   ({pergunta_pior[:44]})")
    print(f"Maior score a barrar    : {maior_nao:.4f}   ({pergunta_nao[:44]})")
    if not tetos_nao:
        print("\n  AVISO: o golden set não tem controle negativo. Sem ele não há como")
        print("  medir o que o piso deve barrar. Acrescente ao menos uma pergunta")
        print("  cuja resposta não exista no acervo.")
        return

    if menor_sinal > maior_nao:
        recomendado = round((menor_sinal + maior_nao) / 2, 4)
        margem = menor_sinal - maior_nao
        print(f"\nAs faixas SEPARAM (folga de {margem:.4f}).")
        print(f"\n  Ponha no .env:  SIMILARIDADE_MINIMA={recomendado}")
        if margem < 0.03:
            print(
                "\n  Folga estreita: com mais documentos ela tende a fechar.\n"
                "  Recalibre depois de indexar o acervo completo."
            )
    else:
        # Sobreposição: mostrar QUAIS perguntas caem abaixo do teto, porque o
        # custo de subir o piso é concreto (essas param de ser respondidas) e a
        # decisão é de produto, não do script.
        perdidas = [(s, q) for s, q in sinais if s <= maior_nao]
        recomendado = round(maior_nao + 0.005, 4)
        print(f"\nAs faixas SE SOBREPÕEM. Um piso de {recomendado} barraria o controle")
        print(f"negativo, mas custaria {len(perdidas)} de {len(sinais)} perguntas respondíveis:")
        for s, q in sorted(perdidas):
            print(f"    {s:.4f}  {q[:56]}")
        print(f"\n  Piso sugerido:  SIMILARIDADE_MINIMA={recomendado}")
        print("  Antes de aplicar, decida se perder essas perguntas é aceitável.")
        print("  A alternativa é atacar a causa: chunking dessas páginas, outro")
        print("  modelo de embeddings, ou o reranker.")

    if distratores:
        maior_distrator, pergunta_distrator = max(distratores, key=lambda t: t[0])
        acima = sum(1 for (s, q), (d, _) in zip(sinais, distratores) if d > s)
        print(f"\n{'-' * 72}")
        print("Diagnóstico de ordenação (NÃO afeta o piso):")
        print(f"  Maior distrator: {maior_distrator:.4f} ({pergunta_distrator[:44]})")
        print(f"  Perguntas em que um distrator vence o sinal: {acima}/{len(sinais)}")
        if acima:
            print("  É isso que o reranker resolveria — o trecho certo está no pool,")
            print("  só não está no topo.")


def imprimir(rotulo: str, r: dict) -> None:
    print(f"\n{'=' * 72}\n{rotulo}\n{'=' * 72}")
    for linha in r["linhas"]:
        marca = "ok  " if linha["acertou"] else "FALHA"
        tipo = " (controle negativo)" if linha["negativo"] else ""
        print(f"\n[{marca}] {linha['pergunta']}{tipo}")
        print(f"        esperado : páginas {linha['esperado'] or '— nenhuma —'}")
        print(f"        recuperou: páginas {linha['recuperou_paginas'] or '— nada —'}")
        print(f"        {linha['n_resultados']} trechos, melhor score {linha['melhor_score']}")

    print(f"\n{'-' * 72}")
    print(f"Recall@k    : {r['acertos']}/{r['total']}  ({r['recall']:.0%})")
    print(f"Controles   : {r['negativos_ok']}/{r['negativos_total']} corretos")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provedor", default=None, help="voyage | openai | fake")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--lexico", action="store_true", help="Só full-text, sem embedding")
    p.add_argument(
        "--calibrar",
        action="store_true",
        help="Mede a distribuição de scores e recomenda SIMILARIDADE_MINIMA",
    )
    p.add_argument("--salvar", action="store_true", help="Grava o resultado para --comparar")
    p.add_argument("--comparar", action="store_true", help="Confronta as execuções salvas")
    args = p.parse_args()

    DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)

    if args.comparar:
        arquivos = sorted(DIR_RESULTADOS.glob("avaliacao_*.json"))
        if len(arquivos) < 2:
            print("Salve ao menos duas execuções com --salvar antes de comparar.", file=sys.stderr)
            return 1
        print(f"\n{'provedor':<32} {'recall':>10} {'controles':>12}")
        print("-" * 56)
        for arq in arquivos:
            d = json.loads(arq.read_text(encoding="utf-8"))
            print(
                f"{d['rotulo']:<32} {d['acertos']}/{d['total']} ({d['recall']:.0%})".ljust(44)
                + f"{d['negativos_ok']}/{d['negativos_total']}".rjust(12)
            )
        print("\nRecall mais alto com controles corretos vence.")
        return 0

    casos = json.loads(GOLDEN.read_text(encoding="utf-8"))
    conn = criar_conexao()
    try:
        repo = SupabaseChunkRepository(conn=conn)

        if args.lexico:
            rotulo = "somente léxico (full-text)"

            def buscar(pergunta: str, top_k: int):
                from solufarma_rag.db.models import ChunkComScore

                brutos = repo.buscar_textual(pergunta, FiltrosBusca(), top_k)
                return [ChunkComScore(chunk=c, score=s) for c, s in brutos]
        else:
            try:
                provider = criar_provedor(args.provedor)
            except (ImportError, RuntimeError, ValueError) as exc:
                print(f"\n{exc}\n", file=sys.stderr)
                return 1

            pendentes = len(repo.listar_pendentes())
            if pendentes:
                print(
                    f"AVISO: {pendentes} chunks sem embedding — o ramo vetorial vai\n"
                    f"       devolver vazio e a medição sai enviesada.\n"
                )
            if args.calibrar:
                calibrar(repo, provider, casos, pool=20)
                return 0

            rotulo = provider.model_id
            searcher = HybridSearcher(repo=repo, provider=provider)
            print(f"Piso de similaridade em uso: {searcher.similaridade_minima}")

            def buscar(pergunta: str, top_k: int):
                return searcher.buscar(pergunta, FiltrosBusca(), top_k)

        resultado = avaliar(buscar, casos, args.top_k)
        imprimir(rotulo, resultado)

        if args.salvar:
            nome = "".join(ch if ch.isalnum() else "_" for ch in rotulo)
            destino = DIR_RESULTADOS / f"avaliacao_{nome}.json"
            destino.write_text(
                json.dumps({"rotulo": rotulo, **resultado}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nSalvo em {destino.relative_to(RAIZ)}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
