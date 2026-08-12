"""Aplica a migração inicial no Supabase e verifica se o banco ficou utilizável.

Uso:
    python tools/setup_supabase.py --check     # só diagnostica, não escreve nada
    python tools/setup_supabase.py --apply     # aplica migrations/001_schema_inicial.sql
    python tools/setup_supabase.py --apply --check

Precisa de DATABASE_URL no `.env` (Supabase → Project Settings → Database →
Connection string → URI, com a senha preenchida). A migração é idempotente:
rodar `--apply` duas vezes não quebra nada.

O `--check` é o que responde "o banco está pronto?": confere extensões, tabelas,
colunas críticas da indexação incremental e os índices de busca, e manda um
vector(1024) de ida e volta pelo driver — se o pgvector não estivesse registrado
no psycopg, esse round-trip falharia antes de qualquer ingestão real.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from solufarma_rag.db.repository import criar_conexao

MIGRACOES_DIR = RAIZ / "src" / "solufarma_rag" / "db" / "migrations"
# Só os arquivos numerados entram, em ordem lexicográfica (= ordem de criação).
# `rascunho_busca_hibrida.sql` fica de fora de propósito: o rodapé da 001 explica
# por que a RPC não vai para o banco.
MIGRACOES = sorted(MIGRACOES_DIR.glob("[0-9][0-9][0-9]_*.sql"))

EXTENSOES = ("vector", "pg_trgm", "unaccent")
# Bucket dos PDFs originais. `documentos.storage_path` é NOT NULL, então sem ele
# nenhuma linha entra em `documentos` — ver migrations/002_storage.sql.
BUCKET = "documentos"
TABELAS = (
    "licitacoes",
    "licitacao_itens",
    "documentos",
    "doc_chunks",
    "itens_planilha",
    "agent_query_log",
)
# Sem estas duas a indexação incremental não funciona (ver ADR/FRENTE_RAG).
COLUNAS_CRITICAS = (("doc_chunks", "content_hash"), ("doc_chunks", "embedding_content_hash"))

OK = "  [ok]  "
FALHA = "  [FALHA] "


def aplicar(conn) -> None:
    """Aplica todas as migrações numeradas, em ordem.

    Commit por migração, não no fim: se a 003 falhar, a 002 já aplicada
    permanece. Todas são idempotentes, então reexecutar é sempre seguro.
    """
    if not MIGRACOES:
        raise RuntimeError(f"Nenhuma migração encontrada em {MIGRACOES_DIR}")
    for caminho in MIGRACOES:
        sql = caminho.read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print(f"Migração aplicada: {caminho.relative_to(RAIZ)}")


def checar(conn) -> bool:
    """Diagnóstico completo. Retorna True se o banco está pronto para uso."""
    tudo_ok = True

    with conn.cursor() as cur:
        print("\nExtensões:")
        cur.execute("select extname from pg_extension")
        instaladas = {linha[0] for linha in cur.fetchall()}
        for ext in EXTENSOES:
            presente = ext in instaladas
            tudo_ok &= presente
            print(f"{OK if presente else FALHA}{ext}")

        print("\nTabelas:")
        cur.execute("select tablename from pg_tables where schemaname = 'public'")
        tabelas = {linha[0] for linha in cur.fetchall()}
        for tabela in TABELAS:
            presente = tabela in tabelas
            tudo_ok &= presente
            print(f"{OK if presente else FALHA}{tabela}")

        print("\nColunas da indexação incremental:")
        for tabela, coluna in COLUNAS_CRITICAS:
            cur.execute(
                """
                select 1 from information_schema.columns
                 where table_name = %s and column_name = %s
                """,
                (tabela, coluna),
            )
            presente = cur.fetchone() is not None
            tudo_ok &= presente
            print(f"{OK if presente else FALHA}{tabela}.{coluna}")

        print("\nRLS (sem ele a publishable key lê o acervo inteiro):")
        cur.execute(
            "select relname, relrowsecurity from pg_class where relname = any(%s)",
            (list(TABELAS),),
        )
        for nome, ligado in cur.fetchall():
            tudo_ok &= ligado
            print(f"{OK if ligado else FALHA}{nome}")

        print("\nÍndices de busca:")
        cur.execute("select indexname from pg_indexes where tablename = 'doc_chunks'")
        indices = {linha[0] for linha in cur.fetchall()}
        for indice in ("idx_chunks_embedding", "idx_chunks_fts"):
            presente = indice in indices
            tudo_ok &= presente
            print(f"{OK if presente else FALHA}{indice}")

        print("\nStorage (destino dos PDFs originais):")
        cur.execute("select public from storage.buckets where id = %s", (BUCKET,))
        linha = cur.fetchone()
        if linha is None:
            tudo_ok = False
            print(f"{FALHA}bucket '{BUCKET}' não existe — rode --apply")
        else:
            print(f"{OK}bucket '{BUCKET}' existe")
            # Bucket público gera URL aberta na internet: documento de licitação
            # de cliente vazaria sem login. Ver migrations/002_storage.sql.
            privado = not linha[0]
            tudo_ok &= privado
            print(f"{OK if privado else FALHA}bucket é privado")

        print("\nRound-trip de vetor (pgvector ↔ driver):")
        try:
            cur.execute("select %s::vector", ([0.1] * 1024,))
            devolvido = cur.fetchone()[0]
            # O pgvector devolve um objeto Vector (ou ndarray, se numpy estiver
            # instalado), não uma lista — daí a normalização antes de medir.
            valores = devolvido.to_list() if hasattr(devolvido, "to_list") else list(devolvido)
            ok_vetor = len(valores) == 1024
            tudo_ok &= ok_vetor
            print(f"{OK if ok_vetor else FALHA}vector(1024) enviado e recebido de volta")
        except Exception as exc:  # noqa: BLE001 - diagnóstico precisa reportar qualquer falha
            tudo_ok = False
            print(f"{FALHA}{exc}")

        print("\nConteúdo atual:")
        for tabela in ("documentos", "doc_chunks"):
            if tabela in tabelas:
                cur.execute(f"select count(*) from {tabela}")
                print(f"         {tabela}: {cur.fetchone()[0]} linhas")
        if "doc_chunks" in tabelas:
            cur.execute("select count(*) from doc_chunks where embedding is not null")
            print(f"         doc_chunks com embedding: {cur.fetchone()[0]}")
        cur.execute("select count(*) from storage.objects where bucket_id = %s", (BUCKET,))
        print(f"         PDFs no Storage: {cur.fetchone()[0]}")

    return tudo_ok


def fumaca(conn) -> bool:
    """Exercita o SupabaseChunkRepository de ponta a ponta e desfaz tudo.

    O `--check` prova que o schema existe; este prova que o CÓDIGO fala com ele.
    São coisas diferentes: uma coluna com nome trocado, um tipo incompatível ou
    um JOIN errado passam pelo `--check` e só aparecem aqui.

    Usa dados sintéticos com um prefixo reconhecível e apaga no final, inclusive
    se algo falhar no meio — nunca deixa lixo no banco do cliente.
    """
    from solufarma_rag.db.models import Chunk
    from solufarma_rag.db.repository import FiltrosBusca, SupabaseChunkRepository
    from solufarma_rag.ingestion.embeddings import (
        FakeEmbeddingProvider,
        gerar_embeddings_pendentes,
    )
    from solufarma_rag.retrieval.hybrid_search import HybridSearcher

    MARCA = "SMOKE-TEST-SOLUFARMA"
    ok = True

    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into licitacoes (orgao, numero_edital, data_abertura) "
                "values (%s, 'PE 000/2026', '2026-01-15') returning id",
                (MARCA,),
            )
            licitacao_id = cur.fetchone()[0]
            cur.execute(
                "insert into documentos (licitacao_id, tipo, titulo, storage_path) "
                "values (%s, 'edital', %s, %s) returning id",
                (licitacao_id, MARCA, f"{MARCA}/doc.pdf"),
            )
            documento_id = str(cur.fetchone()[0])
        conn.commit()

        repo = SupabaseChunkRepository(conn=conn)
        textos = [
            "Aquisição de autoclave horizontal 100 litros para esterilização.",
            "Registro na ANVISA obrigatório para os equipamentos médicos ofertados.",
        ]
        chunks = [
            Chunk(
                documento_id=documento_id,
                chunk_index=i,
                tipo_documento="edital",
                orgao=MARCA,
                secao="1. DO OBJETO",
                pagina_inicio=1,
                pagina_fim=1,
                conteudo=texto,
                token_count=max(1, len(texto) // 4),
                content_hash=Chunk.calcular_hash(texto),
            )
            for i, texto in enumerate(textos)
        ]

        etapas = []
        repo.upsert_chunks(chunks)
        etapas.append(("upsert_chunks", len(repo.listar_pendentes()) == 2))

        provider = FakeEmbeddingProvider()
        rel = gerar_embeddings_pendentes(repo, provider)
        etapas.append(("gerar_embeddings", rel.embeddados == 2))
        etapas.append(("listar_pendentes zera", repo.listar_pendentes() == []))
        etapas.append(("marca documento indexado", rel.documentos_indexados == [documento_id]))

        # Incremental: segunda passada não pode reembeddar nada.
        rel2 = gerar_embeddings_pendentes(repo, provider)
        etapas.append(("incremental nao reprocessa", rel2.embeddados == 0))

        searcher = HybridSearcher(repo=repo, provider=provider)
        achados = searcher.buscar("autoclave esterilização")
        etapas.append(("busca hibrida acha", len(achados) > 0))
        etapas.append(
            ("busca traz chunk completo", bool(achados) and achados[0].chunk.orgao == MARCA)
        )

        filtrado = searcher.buscar("autoclave", FiltrosBusca(orgao="Órgão Que Não Existe"))
        etapas.append(("filtro por orgao corta", filtrado == []))

        for nome, passou in etapas:
            ok &= passou
            print(f"{OK if passou else FALHA}{nome}")

    except Exception as exc:  # noqa: BLE001 - smoke test precisa reportar qualquer falha
        ok = False
        print(f"{FALHA}{type(exc).__name__}: {exc}")
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("delete from licitacoes where orgao = %s", (MARCA,))
            cur.execute("delete from documentos where titulo = %s", (MARCA,))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("select count(*) from documentos where titulo = %s", (MARCA,))
            restou = cur.fetchone()[0]
        print(f"{OK if restou == 0 else FALHA}limpeza (0 linhas de teste no banco)")
        ok &= restou == 0

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica a migração 001")
    parser.add_argument("--check", action="store_true", help="Diagnostica o estado do banco")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Exercita o repositório de ponta a ponta com dados sintéticos (e apaga)",
    )
    args = parser.parse_args()

    if not (args.apply or args.check or args.smoke):
        parser.error("informe --apply, --check e/ou --smoke")

    try:
        conn = criar_conexao()
    except Exception as exc:  # noqa: BLE001 - erro de conexão precisa sair legível
        print(f"Não foi possível conectar: {exc}", file=sys.stderr)
        return 1

    try:
        if args.apply:
            aplicar(conn)
        tudo_ok = True
        if args.check:
            tudo_ok &= checar(conn)
        if args.smoke:
            print("\nSmoke test do repositório (dados sintéticos, apagados no fim):")
            tudo_ok &= fumaca(conn)
        if args.check or args.smoke:
            print("\nBanco pronto para uso." if tudo_ok else "\nHá itens pendentes acima.")
            return 0 if tudo_ok else 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
