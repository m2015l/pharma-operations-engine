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

MIGRACAO = RAIZ / "src" / "solufarma_rag" / "db" / "migrations" / "001_schema_inicial.sql"

EXTENSOES = ("vector", "pg_trgm", "unaccent")
TABELAS = ("licitacoes", "licitacao_itens", "documentos", "doc_chunks", "agent_query_log")
# Sem estas duas a indexação incremental não funciona (ver ADR/FRENTE_RAG).
COLUNAS_CRITICAS = (("doc_chunks", "content_hash"), ("doc_chunks", "embedding_content_hash"))

OK = "  [ok]  "
FALHA = "  [FALHA] "


def aplicar(conn) -> None:
    sql = MIGRACAO.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"Migração aplicada: {MIGRACAO.relative_to(RAIZ)}")


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

    return tudo_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica a migração 001")
    parser.add_argument("--check", action="store_true", help="Diagnostica o estado do banco")
    args = parser.parse_args()

    if not (args.apply or args.check):
        parser.error("informe --apply e/ou --check")

    try:
        conn = criar_conexao()
    except Exception as exc:  # noqa: BLE001 - erro de conexão precisa sair legível
        print(f"Não foi possível conectar: {exc}", file=sys.stderr)
        return 1

    try:
        if args.apply:
            aplicar(conn)
        if args.check:
            pronto = checar(conn)
            print("\nBanco pronto para uso." if pronto else "\nHá itens pendentes acima.")
            return 0 if pronto else 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
