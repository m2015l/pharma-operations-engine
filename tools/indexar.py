"""Indexação — amarra upload → cadastro → tradução → upsert (etapa 9).

Uso:
    python tools/indexar.py "data/brutos/EDITAL.pdf" \
        --orgao "SENAI CETIQT" --tipo edital \
        --numero-edital "PE 045/2023" --data-abertura 2023-05-10

    python tools/indexar.py ... --dry-run    # traduz e valida, não escreve nada

Fecha a lacuna do §5 de workflows/indexacao.md:

    extrair → chunks → [cadastrar documento] → [traduzir chunks] → upsert → embeddings
                            ↑ este CLI          ↑ este CLI

Espera que `tools/chunk_document.py` já tenha rodado — lê
`data/chunks/<stem>_chunks.json` e `<stem>_itens.json`.

Os embeddings NÃO são gerados aqui: os chunks entram com `embedding is null` e
`tools/generate_embeddings.py` os pega depois. A separação é de propósito —
indexar é barato e reexecutável, embeddar custa dinheiro por chamada.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))

from solufarma_rag.db.repository import SupabaseChunkRepository, criar_conexao
from solufarma_rag.ingestion.cadastro import (
    cadastrar_documento,
    gravar_itens_planilha,
)
from solufarma_rag.ingestion.traducao import traduzir_chunks

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


DIR_CHUNKS = RAIZ / "data" / "chunks"


def _carregar(caminho: Path) -> list[dict]:
    if not caminho.is_file():
        raise FileNotFoundError(
            f"{caminho.name} não encontrado. Rode `tools/chunk_document.py` antes."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf", help="PDF original em data/brutos/")
    p.add_argument("--orgao", required=True, help="Órgão/entidade contratante")
    p.add_argument("--tipo", default="edital", help="edital | ata | resultado | anexo | ... | outro")
    p.add_argument("--titulo", default=None, help="Padrão: nome do arquivo sem extensão")
    p.add_argument("--numero-edital", default=None)
    p.add_argument("--data-abertura", default=None, help="AAAA-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="Traduz e valida sem escrever")
    args = p.parse_args()

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

    data_abertura = date.fromisoformat(args.data_abertura) if args.data_abertura else None
    # O DDL não guarda contagem de páginas em lugar nenhum antes do cadastro;
    # a maior página vista nos chunks é a melhor estimativa disponível aqui.
    num_paginas = max((int(c.get("pagina_fim") or 0) for c in chunks_brutos), default=None)

    print(f"Documento: {stem}")
    print(f"  chunks: {len(chunks_brutos)}   linhas de planilha: {len(itens)}   páginas: {num_paginas}")

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
        print("\n2. Cadastro do documento")
        documento_id, ja_existia = cadastrar_documento(
            conn,
            storage_path=storage_path,
            hash_sha256=hash_sha256,
            titulo=args.titulo or stem,
            tipo=args.tipo,
            orgao=args.orgao,
            numero_edital=args.numero_edital,
            data_abertura=data_abertura,
            num_paginas=num_paginas,
            ocr_aplicado=True,
            metodo_extracao="vlm",
        )
        print(f"   documento_id = {documento_id}" + ("  (já cadastrado)" if ja_existia else ""))

        print("\n3. Tradução dos chunks")
        chunks = traduzir_chunks(
            chunks_brutos,
            documento_id=documento_id,
            tipo_documento=args.tipo,
            orgao=args.orgao,
            data=data_abertura,
        )
        print(f"   {len(chunks)} chunks traduzidos")

        print("\n4. Gravação no banco")
        repo = SupabaseChunkRepository(conn=conn)
        repo.upsert_chunks(chunks)
        pendentes = len(repo.listar_pendentes())
        print(f"   upsert_chunks: {len(chunks)} chunks")
        print(f"   aguardando embedding: {pendentes}")

        if itens:
            gravados = gravar_itens_planilha(
                conn,
                documento_hash=hash_sha256[:16],
                documento_id=documento_id,
                itens=itens,
            )
            print(f"   itens_planilha: {gravados} linhas")
    finally:
        conn.close()

    print("\nPronto. Próximo passo: tools/generate_embeddings.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
