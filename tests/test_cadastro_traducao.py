"""Cadastro do documento e tradução de chunks (ingestion/) — offline, banco falso."""

from __future__ import annotations

from datetime import date

import pytest

from solufarma_rag.db.models import Chunk
from solufarma_rag.ingestion.cadastro import cadastrar_documento, gravar_itens_planilha
from solufarma_rag.ingestion.traducao import traduzir_chunk, traduzir_chunks
from tests.falsos import ConexaoFalsa

ARGS_CADASTRO = {
    "storage_path": "abc/doc.pdf",
    "hash_sha256": "f" * 64,
    "titulo": "Câmara Fria (CAT SJC-01975)",
    "tipo": "atestado",
    "orgao": "INSTITUTO BUTANTAN",
    "num_paginas": 3,
    "ocr_aplicado": False,
    "metodo_extracao": "nativo",
}


# --- cadastro ----------------------------------------------------------------


def test_cadastro_novo_cria_licitacao_e_documento():
    # respostas: documento não existe, licitação não existe, id da licitação, id do documento
    conn = ConexaoFalsa(respostas=[None, None, ("lic-1",), ("doc-1",)])
    documento_id, ja_existia = cadastrar_documento(conn, **ARGS_CADASTRO)

    assert (documento_id, ja_existia) == ("doc-1", False)
    ((_, params),) = conn.sql("insert into documentos")
    assert params == (
        "lic-1", "atestado", "Câmara Fria (CAT SJC-01975)", "abc/doc.pdf", "f" * 64,
        3, False, "nativo",
    )
    assert conn.commits == 1


def test_cadastro_reaproveita_licitacao_existente():
    conn = ConexaoFalsa(respostas=[None, ("lic-9",), ("doc-2",)])
    documento_id, _ = cadastrar_documento(conn, **ARGS_CADASTRO)
    assert documento_id == "doc-2"
    assert not conn.sql("insert into licitacoes")
    # `is not distinct from`: numero_edital nulo precisa casar com nulo.
    assert conn.sql("is not distinct from")


def test_cadastro_existente_atualiza_titulo_e_metodo_sem_mexer_no_orgao():
    conn = ConexaoFalsa(respostas=[("doc-velho",)])
    documento_id, ja_existia = cadastrar_documento(conn, **ARGS_CADASTRO)

    assert (documento_id, ja_existia) == ("doc-velho", True)
    (sql, params), = conn.sql("update documentos")
    assert params == ("Câmara Fria (CAT SJC-01975)", False, "nativo", "doc-velho")
    assert "licitacao" not in sql and "orgao" not in sql
    assert not conn.sql("insert")
    assert conn.commits == 1


@pytest.mark.parametrize(
    "campo, valor, mensagem",
    [("tipo", "planilha", "tipo deve ser"), ("orgao", "   ", "orgao é obrigatório")],
)
def test_cadastro_valida_antes_de_tocar_no_banco(campo, valor, mensagem):
    conn = ConexaoFalsa()
    with pytest.raises(ValueError, match=mensagem):
        cadastrar_documento(conn, **{**ARGS_CADASTRO, campo: valor})
    assert conn.executados == []


def test_gravar_itens_apaga_antes_e_preenche_as_duas_chaves():
    conn = ConexaoFalsa()
    itens = [
        {"pagina": 2, "secao": "PISO", "celulas": ["P01", "206,92"]},
        {"pagina": 3, "secao": None, "celulas": None},
        # Linha com a qualidade da leitura (migração 004): status, confiança e
        # observação viajam junto com o dado.
        {
            "pagina": 5,
            "secao": "GASES",
            "celulas": ["2.1", ""],
            "status": "ilegivel",
            "confianca": 0.55,
            "observacoes": "carimbo sobre as linhas 2.1, 2.5",
        },
    ]
    assert gravar_itens_planilha(conn, documento_hash="h16", documento_id="d1", itens=itens) == 3

    assert conn.executados[0][0].startswith("delete from itens_planilha")
    inserts = conn.sql("insert into itens_planilha")
    # JSON anterior à migração 004 não tem os três campos: ficam nulos em vez de
    # virar "ok", porque afirmar integridade sem ter verificado é pior que não saber.
    assert [p for _, p in inserts] == [
        ("h16", "d1", 2, "PISO", ["P01", "206,92"], None, None, None),
        ("h16", "d1", 3, None, [], None, None, None),
        (
            "h16", "d1", 5, "GASES", ["2.1", ""],
            "ilegivel", 0.55, "carimbo sobre as linhas 2.1, 2.5",
        ),
    ]
    assert conn.commits == 1


# --- tradução ----------------------------------------------------------------

BRUTO = {
    "id": "9068e5659da77411#c0007",
    "texto": "[Doc | p. 3] conteúdo com cabeçalho",
    "texto_puro": "conteúdo sem cabeçalho",
    "caminho_secao": ["DADOS DO CONTRATO", "2.4 Prazo"],
    "pagina_inicio": 3,
    "pagina_fim": 4,
    "n_chars": 400,
}
META = {
    "documento_id": "doc-1",
    "tipo_documento": "atestado",
    "orgao": "SENAI",
    "data": date(2020, 1, 2),
}


def test_traduz_campo_a_campo():
    c = traduzir_chunk(BRUTO, 0, **META)
    assert c.chunk_index == 7  # do id, não da posição
    assert c.secao == "DADOS DO CONTRATO > 2.4 Prazo"
    assert (c.pagina_inicio, c.pagina_fim) == (3, 4)
    assert c.conteudo == BRUTO["texto"]  # COM cabeçalho: é o que vai ao embedding
    assert c.content_hash == Chunk.calcular_hash(BRUTO["texto"])
    assert c.token_count == 100
    assert (c.documento_id, c.orgao, c.data) == ("doc-1", "SENAI", date(2020, 1, 2))


def test_sem_id_usa_posicao_e_pagina_zero_vira_um():
    bruto = {"texto": "abc", "pagina_inicio": 0, "pagina_fim": None}
    c = traduzir_chunk(bruto, 5, **META)
    assert c.chunk_index == 5
    assert (c.pagina_inicio, c.pagina_fim) == (1, 1)
    assert c.secao == ""
    assert c.token_count == 1  # nunca zero (Field ge=1)


def test_chunk_sem_texto_e_recusado():
    with pytest.raises(ValueError, match="sem texto"):
        traduzir_chunk({"id": "x#c0001", "texto": "   "}, 0, **META)


def test_traduz_lote_preserva_ordem():
    lote = [dict(BRUTO, id=f"h#c{i:04d}") for i in (3, 1, 2)]
    assert [c.chunk_index for c in traduzir_chunks(lote, **META)] == [3, 1, 2]
