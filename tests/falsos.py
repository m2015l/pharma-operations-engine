"""Dublês offline para os testes dos CLIs (item 20): banco falso e carregador de tools/.

Nada aqui abre rede nem conexão: a conexão falsa só registra o SQL executado e
devolve respostas enfileiradas, o suficiente para conferir o que cada função
mandaria ao Supabase.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]


def carregar_ferramenta(nome: str):
    """Importa `tools/<nome>.py` como módulo (a pasta tools/ não é pacote)."""
    pasta = str(RAIZ_REPO / "tools")
    if pasta not in sys.path:
        # indexar.py importa `upload_documento` como módulo irmão.
        sys.path.insert(0, pasta)
    spec = importlib.util.spec_from_file_location(
        f"ferramenta_{nome}", RAIZ_REPO / "tools" / f"{nome}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CursorFalso:
    """Cursor psycopg mínimo: grava o SQL executado e devolve respostas enfileiradas."""

    def __init__(self, conn: ConexaoFalsa):
        self.conn = conn
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executados.append((" ".join(sql.split()), params))
        if self.conn.erro_em and self.conn.erro_em in sql:
            raise RuntimeError("falha simulada")
        self.rowcount = self.conn.rowcount

    def executemany(self, sql, seq):
        for params in seq:
            self.execute(sql, params)

    def fetchone(self):
        return self.conn.respostas.pop(0) if self.conn.respostas else None


class ConexaoFalsa:
    """Conexão psycopg falsa: sem rede, registra commit/rollback."""

    def __init__(self, respostas: list | None = None, rowcount: int = 0, erro_em: str = ""):
        self.respostas = list(respostas or [])
        self.rowcount = rowcount
        self.erro_em = erro_em
        self.executados: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.fechada = False

    def cursor(self):
        return CursorFalso(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.fechada = True

    def sql(self, trecho: str) -> list[tuple[str, object]]:
        """Execuções cujo SQL contém `trecho` (normalizado em espaço simples)."""
        return [(s, p) for s, p in self.executados if trecho in s]
