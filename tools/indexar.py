"""Indexação — amarra upload → cadastro → tradução → upsert (etapa 9).

Uso:
    python tools/indexar.py "data/brutos/EDITAL.pdf" \
        --orgao "Instituto BioPharma" --tipo edital \
        --numero-edital "PE 045/2023" --data-abertura 2023-05-10

    python tools/indexar.py ... --dry-run    # traduz e valida, não escreve nada

Fecha a lacuna do §5 de workflows/indexacao.md:

    extrair → chunks → [cadastrar documento] → [traduzir chunks] → upsert → embeddings
                            ↑ este CLI          ↑ este CLI

Espera que `tools/chunk_document.py` já tenha rodado — lê
`data/chunks/<stem>_chunks.json` e `<stem>_itens.json`.

O roteiro de cadastro/gravação vive em `pharma_rag.ingestion.indexacao`
(`indexar_documento`) e é o MESMO que o upload da API (`api/ingestao.py`) usa.

Os embeddings NÃO são gerados aqui: os chunks entram com `embedding is null` e
`tools/generate_embeddings.py` os pega depois. A separação é de propósito —
indexar é barato e reexecutável, embeddar custa dinheiro por chamada.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))

from pharma_rag.db.repository import SupabaseChunkRepository, criar_conexao
from pharma_rag.ingestion.cadastro import cadastrar_documento
from pharma_rag.ingestion.indexacao import (
    EXTRACAO_DESCONHECIDA,
    TituloDivergente,
    indexar_documento,
    metodo_extracao,
    resolver_titulo,
)
from pharma_rag.ingestion.traducao import traduzir_chunks

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


# Mesmas variáveis de ambiente de `pharma_ops.config`: permitem rodar o CLI de
# uma worktree lendo o `data/` do repositório principal (que é gitignored).
DIR_CHUNKS = Path(os.getenv("PHARMA_OPS_DIR_CHUNKS", RAIZ / "data" / "chunks"))
DIR_EXTRAIDOS = Path(os.getenv("PHARMA_OPS_DIR_EXTRAIDOS", RAIZ / "data" / "extraidos"))


def _carregar(caminho: Path) -> list[dict]:
    if not caminho.is_file():
        raise FileNotFoundError(
            f"{caminho.name} não encontrado. Rode `tools/chunk_document.py` antes."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def detectar_extracao(stem: str, dir_extraidos: Path | None = None) -> tuple[bool, str] | None:
    """Lê `<dir_extraidos>/<stem>.json` e deriva o método. None se não achar."""
    caminho = (dir_extraidos or DIR_EXTRAIDOS) / f"{stem}.json"
    if not caminho.is_file():
        return None
    doc = json.loads(caminho.read_text(encoding="utf-8-sig"))
    return metodo_extracao(doc.get("paginas") or [])


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf", help="PDF original em data/brutos/")
    p.add_argument("--orgao", required=True, help="Órgão/entidade contratante")
    p.add_argument("--tipo", default="edital", help="edital | ata | resultado | anexo | ... | outro")
    p.add_argument(
        "--titulo",
        default=None,
        help="Padrão: o título já gravado nos chunks. Se divergir deles, a indexação é recusada.",
    )
    p.add_argument("--numero-edital", default=None)
    p.add_argument("--data-abertura", default=None, help="AAAA-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="Traduz e valida sem escrever")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"PDF não encontrado: {pdf}", file=sys.stderr)
        return 1

    stem = pdf.stem
    try:
        chunks_brutos = _carregar(DIR_CHUNKS / f"{stem}_chunks.json")
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    # Nem todo documento tem tabela; ausência do arquivo de itens é normal.
    caminho_itens = DIR_CHUNKS / f"{stem}_itens.json"
    itens = _carregar(caminho_itens) if caminho_itens.is_file() else []

    try:
        titulo = resolver_titulo(args.titulo, chunks_brutos)
    except TituloDivergente as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    if titulo == stem.replace("_", " "):
        print(
            "AVISO: o título é o nome do arquivo. Os PDFs do Drive vieram com nome trocado "
            "(28/09) — confira o conteúdo (tools/triar_documentos.py) antes de indexar.",
            file=sys.stderr,
        )

    extracao = detectar_extracao(stem)
    if extracao is None:
        print(
            f"AVISO: {DIR_EXTRAIDOS / (stem + '.json')} não encontrado (ou sem rota por "
            "página). Gravando ocr_aplicado=True, metodo_extracao='vlm' como antes.",
            file=sys.stderr,
        )
        extracao = EXTRACAO_DESCONHECIDA
    ocr_aplicado, metodo = extracao

    data_abertura = date.fromisoformat(args.data_abertura) if args.data_abertura else None
    # O DDL não guarda contagem de páginas em lugar nenhum antes do cadastro;
    # a maior página vista nos chunks é a melhor estimativa disponível aqui.
    num_paginas = max((int(c.get("pagina_fim") or 0) for c in chunks_brutos), default=None)

    print(f"Documento: {stem}")
    print(f"  título: {titulo}")
    print(f"  chunks: {len(chunks_brutos)}   linhas de planilha: {len(itens)}   páginas: {num_paginas}")
    print(f"  extração: {metodo} (ocr_aplicado={ocr_aplicado})")

    if args.dry_run:
        traduzidos = traduzir_chunks(
            chunks_brutos,
            documento_id="00000000-0000-0000-0000-000000000000",
            tipo_documento=args.tipo,
            orgao=args.orgao,
            data=data_abertura,
        )
        print(f"\n[dry-run] {len(traduzidos)} chunks traduzidos e validados. Nada foi escrito.")
        exemplo = traduzidos[0]
        print(f"  exemplo: chunk_index={exemplo.chunk_index} "
              f"p.{exemplo.pagina_inicio}-{exemplo.pagina_fim} "
              f"secao={exemplo.secao!r} tokens={exemplo.token_count}")
        return 0

    import upload_documento

    print("\n1. Upload para o Storage")
    import httpx

    with httpx.Client() as client:
        url, chave = upload_documento._credenciais()
        storage_path, hash_sha256 = upload_documento.enviar(client, url, chave, pdf)
    print(f"   {storage_path}")

    conn = criar_conexao()
    try:
        print("\n2. Cadastro, tradução e gravação dos chunks")
        repo = SupabaseChunkRepository(conn=conn)
        # Reindexação: upsert + remoção dos chunks que o chunking novo não gerou
        # mais (senão sobram órfãos com chunk_index alto), numa transação só e
        # restrita a este documento_id — tudo dentro de indexar_documento.
        res = indexar_documento(
            conn,
            storage_path=storage_path,
            hash_sha256=hash_sha256,
            chunks_brutos=chunks_brutos,
            itens=itens,
            titulo=titulo,
            orgao=args.orgao,
            tipo=args.tipo,
            ocr_aplicado=ocr_aplicado,
            metodo=metodo,
            numero_edital=args.numero_edital,
            data_abertura=data_abertura,
            num_paginas=num_paginas,
            repo=repo,
            cadastrar=cadastrar_documento,
        )
        print(
            f"   documento_id = {res.documento_id}"
            + ("  (já cadastrado: título e método de extração atualizados)" if res.ja_existia else "")
        )
        print(
            f"   upsert_chunks: {res.chunks_gravados} chunks   "
            f"órfãos removidos: {res.orfaos_removidos}"
        )
        print(f"   aguardando embedding: {len(repo.listar_pendentes())}")
        if itens:
            print(f"   itens_planilha: {res.itens_gravados} linhas")
    finally:
        conn.close()

    print("\nPronto. Próximo passo: tools/generate_embeddings.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
