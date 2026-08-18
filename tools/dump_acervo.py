"""Despeja o conteúdo indexado do acervo — a verdade de referência das auditorias.

Uso:
    python tools/dump_acervo.py                      # tudo, para stdout
    python tools/dump_acervo.py -o .tmp/acervo.md    # para arquivo
    python tools/dump_acervo.py --documento <uuid>   # um documento só
    python tools/dump_acervo.py --indice             # só o índice de seções/páginas

Sem isto, avaliar uma resposta do agente é circular: a única janela para o
conteúdo é a própria busca, então um trecho que a busca NUNCA recupera é
indistinguível de um trecho que não existe. Quem audita precisa ver o acervo
inteiro, não o que o retrieval decidiu mostrar.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from solufarma_rag.db.repository import criar_conexao

for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


SQL = """
    select d.id, d.titulo, d.tipo, coalesce(l.orgao, '—') as orgao,
           c.chunk_index, coalesce(c.secao, '') as secao,
           c.pagina_inicio, c.pagina_fim, c.conteudo, c.token_count,
           (c.embedding is not null) as tem_embedding
    from doc_chunks c
    join documentos d on d.id = c.documento_id
    left join licitacoes l on l.id = d.licitacao_id
    {filtro}
    order by d.titulo, c.chunk_index
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--saida", default=None, help="Arquivo de saída (padrão: stdout)")
    p.add_argument("--documento", default=None, help="Filtra por documento_id")
    p.add_argument("--indice", action="store_true", help="Só o índice, sem o texto")
    args = p.parse_args()

    filtro = "where c.documento_id = %(doc)s" if args.documento else ""
    conn = criar_conexao()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL.format(filtro=filtro), {"doc": args.documento})
            linhas = cur.fetchall()
    finally:
        conn.close()

    if not linhas:
        print("Nenhum chunk indexado (confira DATABASE_URL e se a indexação rodou).")
        return 1

    partes: list[str] = []
    doc_atual = None
    sem_embedding = 0

    for linha in linhas:
        doc_id, titulo, tipo, orgao, idx = linha[:5]
        secao, p_ini, p_fim, conteudo, tokens, tem_emb = linha[5:]
        if doc_id != doc_atual:
            doc_atual = doc_id
            partes.append(f"\n\n# {titulo}\n")
            partes.append(f"- documento_id: `{doc_id}`\n- tipo: {tipo}\n- órgão: {orgao}\n")
        if not tem_emb:
            sem_embedding += 1
        marca = "" if tem_emb else "  **[SEM EMBEDDING]**"
        cabecalho = (
            f"\n## chunk {idx} · p.{p_ini}-{p_fim} · {tokens} tokens{marca}\n"
            f"seção: {secao or '(sem seção)'}\n"
        )
        partes.append(cabecalho)
        if not args.indice:
            partes.append(f"\n{conteudo}\n")

    texto = "".join(partes).lstrip()
    rodape = f"\n\n---\n{len(linhas)} chunks · {sem_embedding} sem embedding\n"

    if args.saida:
        destino = Path(args.saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + rodape, encoding="utf-8")
        print(f"{len(linhas)} chunks escritos em {destino}")
    else:
        print(texto + rodape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
