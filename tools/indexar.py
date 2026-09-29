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
import os
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


# Mesmas variáveis de ambiente de `solufarma.config`: permitem rodar o CLI de
# uma worktree lendo o `data/` do repositório principal (que é gitignored).
DIR_CHUNKS = Path(os.getenv("SOLUFARMA_DIR_CHUNKS", RAIZ / "data" / "chunks"))
DIR_EXTRAIDOS = Path(os.getenv("SOLUFARMA_DIR_EXTRAIDOS", RAIZ / "data" / "extraidos"))

# Quando o JSON de extração não é encontrado, mantém o comportamento anterior a
# 29/09 (o pipeline nasceu para o acervo escaneado) — com aviso.
EXTRACAO_DESCONHECIDA = (True, "vlm")


def _carregar(caminho: Path) -> list[dict]:
    if not caminho.is_file():
        raise FileNotFoundError(
            f"{caminho.name} não encontrado. Rode `tools/chunk_document.py` antes."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def metodo_extracao(paginas: list[dict]) -> tuple[bool, str] | None:
    """Deriva `(ocr_aplicado, metodo_extracao)` das rotas das páginas extraídas.

    Cada página do JSON de extração traz `estrategia`: `nativo` (texto do PDF),
    `vlm` (OCR por modelo de visão) ou `vazia` (foi ao VLM e voltou sem texto —
    conta como VLM, porque a chamada aconteceu). O resultado:

        todas nativas  -> (False, "nativo")
        todas VLM      -> (True,  "vlm")
        mistura        -> (True,  "misto")

    `documentos.metodo_extracao` é `text` sem CHECK (001_schema_inicial.sql),
    então "misto" é aceito pelo banco. Devolve None se não houver página com
    rota conhecida (ex.: `pendente`) — quem chama decide o fallback.
    """
    rotas = {
        "vlm" if p.get("estrategia") == "vazia" else p.get("estrategia")
        for p in paginas
    } & {"nativo", "vlm"}
    if not rotas:
        return None
    if rotas == {"nativo"}:
        return False, "nativo"
    if rotas == {"vlm"}:
        return True, "vlm"
    return True, "misto"


def detectar_extracao(stem: str, dir_extraidos: Path | None = None) -> tuple[bool, str] | None:
    """Lê `<dir_extraidos>/<stem>.json` e deriva o método. None se não achar."""
    caminho = (dir_extraidos or DIR_EXTRAIDOS) / f"{stem}.json"
    if not caminho.is_file():
        return None
    doc = json.loads(caminho.read_text(encoding="utf-8-sig"))
    return metodo_extracao(doc.get("paginas") or [])


class TituloDivergente(ValueError):
    """O --titulo pedido não é o que está gravado no cabeçalho dos chunks."""


def resolver_titulo(titulo_cli: str | None, chunks_brutos: list[dict]) -> str:
    """
    Decide o título do cadastro a partir dos chunks já gerados.

    O cabeçalho contextual (o que aparece na citação) é gravado no CHUNKING,
    não aqui. Se o `--titulo` daqui divergir do que está nos chunks, o banco
    fica com `documentos.titulo` certo e as citações erradas — o bug de 28/09.
    Por isso: sem `--titulo`, herda o dos chunks; com `--titulo` divergente,
    recusa e manda re-chunkar (chunking é grátis e determinístico).
    """
    titulos = {(c.get("documento") or "").strip() for c in chunks_brutos} - {""}
    if len(titulos) > 1:
        raise TituloDivergente(f"chunks com títulos diferentes entre si: {sorted(titulos)}")
    titulo_chunks = titulos.pop() if titulos else None
    if titulo_cli is None:
        if titulo_chunks is None:
            raise TituloDivergente("chunks sem campo 'documento'; passe --titulo e re-chunke")
        return titulo_chunks
    if titulo_chunks is not None and titulo_cli.strip() != titulo_chunks:
        raise TituloDivergente(
            f"--titulo {titulo_cli.strip()!r} diverge do título embutido nos chunks "
            f"{titulo_chunks!r}. Re-gere os chunks com o título certo:\n"
            "  uv run python tools/chunk_document.py <json de extração> "
            f'--titulo "{titulo_cli.strip()}"'
        )
    return titulo_cli.strip()


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
        print("\n2. Cadastro do documento")
        documento_id, ja_existia = cadastrar_documento(
            conn,
            storage_path=storage_path,
            hash_sha256=hash_sha256,
            titulo=titulo,
            tipo=args.tipo,
            orgao=args.orgao,
            numero_edital=args.numero_edital,
            data_abertura=data_abertura,
            num_paginas=num_paginas,
            ocr_aplicado=ocr_aplicado,
            metodo_extracao=metodo,
        )
        print(
            f"   documento_id = {documento_id}"
            + ("  (já cadastrado: título e método de extração atualizados)" if ja_existia else "")
        )

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
        # Reindexação: upsert + remoção dos chunks que o chunking novo não gerou
        # mais (senão sobram órfãos com chunk_index alto), numa transação só e
        # restrita a este documento_id.
        removidos = repo.substituir_chunks_documento(documento_id, chunks)
        pendentes = len(repo.listar_pendentes())
        print(f"   upsert_chunks: {len(chunks)} chunks   órfãos removidos: {removidos}")
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
