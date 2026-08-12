"""Cadastro do documento — etapa 7 de workflows/indexacao.md.

Insere (ou reencontra) as linhas em `licitacoes` e `documentos` e devolve o UUID
que todos os chunks daquele arquivo vão apontar. É a peça que faltava entre o
upload para o Storage e o `upsert_chunks`.

IDEMPOTÊNCIA
`documentos.hash_sha256` é UNIQUE — é o que impede o mesmo arquivo de entrar
duas vezes por ter sido baixado com nomes diferentes. Reexecutar devolve o UUID
que já existe em vez de falhar, então rodar a indexação de novo é seguro.

`licitacoes` não tem constraint de unicidade (um órgão tem várias licitações, e
`numero_edital` pode ser nulo). A busca é por (orgao, numero_edital) antes de
inserir: não é à prova de corrida, mas a ingestão é um lote sequencial, não um
endpoint concorrente.

DE ONDE VÊM OS METADADOS
`orgao`, `numero_edital` e `data_abertura` chegam como parâmetro — não são
extraídos do documento. Essa é a decisão em aberto do §4 do workflow (usuário
informa no upload × LLM lê da capa), e a assinatura aqui serve às duas: quem
preenche os argumentos pode ser um formulário do Streamlit ou um extrator
automático. O backend não muda.
"""

from __future__ import annotations

from datetime import date

from ..db.models import TIPOS_DOCUMENTO as TIPOS_VALIDOS


def _achar_ou_criar_licitacao(
    cur, orgao: str, numero_edital: str | None, data_abertura: date | None
) -> str:
    # `is not distinct from` em vez de `=` porque numero_edital é nullable e
    # `NULL = NULL` é NULL, não true — a busca nunca casaria para documento sem
    # número, e cada reexecução criaria uma licitação nova.
    cur.execute(
        """
        select id from licitacoes
         where orgao = %s and numero_edital is not distinct from %s
         limit 1
        """,
        (orgao, numero_edital),
    )
    linha = cur.fetchone()
    if linha is not None:
        return str(linha[0])

    cur.execute(
        """
        insert into licitacoes (orgao, numero_edital, data_abertura)
        values (%s, %s, %s)
        returning id
        """,
        (orgao, numero_edital, data_abertura),
    )
    return str(cur.fetchone()[0])


def cadastrar_documento(
    conn,
    *,
    storage_path: str,
    hash_sha256: str,
    titulo: str,
    tipo: str,
    orgao: str,
    numero_edital: str | None = None,
    data_abertura: date | None = None,
    num_paginas: int | None = None,
    ocr_aplicado: bool = False,
    metodo_extracao: str | None = None,
) -> tuple[str, bool]:
    """Cadastra o documento e devolve `(documento_id, ja_existia)`.

    `ja_existia` deixa o CLI dizer se reaproveitou um cadastro anterior, em vez
    de o usuário achar que gravou algo novo quando não gravou.
    """
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"tipo deve ser um de {TIPOS_VALIDOS}, recebido: {tipo!r}")
    if not orgao.strip():
        raise ValueError("orgao é obrigatório (é NOT NULL em licitacoes)")

    with conn.cursor() as cur:
        cur.execute("select id from documentos where hash_sha256 = %s", (hash_sha256,))
        linha = cur.fetchone()
        if linha is not None:
            return str(linha[0]), True

        licitacao_id = _achar_ou_criar_licitacao(cur, orgao, numero_edital, data_abertura)
        cur.execute(
            """
            insert into documentos (
                licitacao_id, tipo, titulo, storage_path, hash_sha256,
                num_paginas, ocr_aplicado, metodo_extracao, status_processamento
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, 'chunked')
            returning id
            """,
            (
                licitacao_id,
                tipo,
                titulo,
                storage_path,
                hash_sha256,
                num_paginas,
                ocr_aplicado,
                metodo_extracao,
            ),
        )
        documento_id = str(cur.fetchone()[0])
    conn.commit()
    return documento_id, False


def gravar_itens_planilha(
    conn, *, documento_hash: str, documento_id: str, itens: list[dict]
) -> int:
    """Grava as linhas de tabela extraídas (ADR-006). Devolve quantas gravou.

    Apaga antes de inserir: `itens_planilha` não tem constraint de unicidade
    (uma tabela pode repetir a mesma linha legitimamente), então sem o delete
    reexecutar a indexação duplicaria as 807 linhas em silêncio.

    Preenche as DUAS colunas de documento: `documento_hash` (o que o chunking
    produz) e `documento_id` (a FK de verdade). O DDL permite gravar só com o
    hash para a ingestão não travar esperando cadastro — mas aqui o cadastro já
    aconteceu, então não há motivo para deixar a FK nula.
    """
    with conn.cursor() as cur:
        cur.execute("delete from itens_planilha where documento_hash = %s", (documento_hash,))
        for item in itens:
            cur.execute(
                """
                insert into itens_planilha (documento_hash, documento_id, pagina, secao, celulas)
                values (%s, %s, %s, %s, %s)
                """,
                (
                    documento_hash,
                    documento_id,
                    item.get("pagina"),
                    item.get("secao"),
                    list(item.get("celulas") or []),
                ),
            )
    conn.commit()
    return len(itens)
