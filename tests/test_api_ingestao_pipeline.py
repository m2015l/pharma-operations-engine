"""Upload real: etapas que reusam o pipeline de verdade, com dublês (sem rede/banco/LLM).

- cadastro → `indexar_documento` (o mesmo do tools/indexar.py): método por página,
  título do cabeçalho dos chunks, reindexação sem órfãos;
- embeddings → só o documento enviado (RepoRestrito);
- classificação → falha SUAVE (documento fica indexado, etapa 'pendente');
- teto de páginas de OCR → o envio para antes da extração, sem gastar.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from pharma_rag.db.repository import InMemoryChunkRepository
from tests.falsos import ConexaoFalsa

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))

import ingestao

PDF = b"%PDF-1.4\n%%EOF\n"
TITULO = "CAT 123 — Instituto BioPharma — Biotério"


@pytest.fixture
def envio(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestao, "_ENVIOS", {})
    caminho = tmp_path / "x.pdf"
    caminho.write_bytes(PDF)
    e = ingestao.criar_envio(caminho, "x.pdf", "Instituto BioPharma", "atestado")
    e.titulo = TITULO
    return e


def _chunk_bruto(i: int, titulo: str = TITULO) -> dict:
    return {
        "id": f"h#c{i:04d}",
        "texto": f"[{titulo} | p. {i}] corpo do trecho {i} com texto suficiente para indexar",
        "documento": titulo,
        "caminho_secao": [],
        "pagina_inicio": i,
        "pagina_fim": i,
    }


@pytest.fixture
def banco(monkeypatch):
    """Storage falso, conexão falsa e repositório em memória no lugar do Supabase."""
    upload = types.ModuleType("upload_documento")
    upload._credenciais = lambda: ("http://supabase.invalido", "chave")
    upload.enviar = lambda client, url, chave, pdf: ("h/x.pdf", "a" * 64)
    monkeypatch.setitem(sys.modules, "upload_documento", upload)

    from pharma_rag.db import repository

    # cadastrar_documento: select documento (None) → select licitação (None) →
    # insert licitação → insert documento.
    conn = ConexaoFalsa(respostas=[None, None, ("lic-1",), ("doc-1",)])
    repo = InMemoryChunkRepository()
    monkeypatch.setattr(repository, "criar_conexao", lambda *a, **k: conn)
    monkeypatch.setattr(repository, "SupabaseChunkRepository", lambda conn: repo)
    return types.SimpleNamespace(conn=conn, repo=repo)


# --- cadastro ----------------------------------------------------------------


def test_cadastro_usa_indexar_documento_sem_orfaos_e_com_metodo_por_pagina(
    envio, banco, fazer_chunk
):
    banco.repo.upsert_chunks([fazer_chunk(7, "velho", documento_id="doc-1")])
    envio.contexto["extracao"] = {
        "n_paginas": 2,
        "paginas": [{"estrategia": "nativo"}, {"estrategia": "vlm"}],
    }
    envio.contexto["chunks"] = [_chunk_bruto(1), _chunk_bruto(2)]
    envio.contexto["itens"] = []

    detalhe = ingestao.etapa_cadastro(envio)

    assert envio.documento_id == "doc-1"
    assert banco.repo.total_chunks() == 2  # o chunk 7 (órfão) saiu
    assert "1 trechos antigos removidos" in detalhe and "misto" in detalhe
    insert = banco.conn.sql("insert into documentos")[0][1]
    assert TITULO in insert and "misto" in insert and True in insert
    assert banco.conn.fechada


def test_cadastro_recusa_titulo_divergente_dos_chunks(envio, banco):
    envio.contexto["extracao"] = {"paginas": [{"estrategia": "nativo"}]}
    envio.contexto["chunks"] = [_chunk_bruto(1, titulo="Outro título")]
    with pytest.raises(ValueError, match="diverge"):
        ingestao.etapa_cadastro(envio)


def test_cadastro_sem_trechos_falha_com_mensagem_clara(envio, banco):
    envio.contexto["extracao"] = {"paginas": []}
    envio.contexto["chunks"] = []
    with pytest.raises(RuntimeError, match="nenhum trecho"):
        ingestao.etapa_cadastro(envio)


# --- embeddings ----------------------------------------------------------------


def test_embeddings_so_do_documento_enviado(envio, banco, monkeypatch, fazer_chunk):
    from pharma_rag.ingestion import embeddings

    monkeypatch.setattr(embeddings, "criar_provedor", lambda nome: embeddings.FakeEmbeddingProvider())
    corpo = "corpo com texto suficiente para passar do filtro de ruído"
    banco.repo.upsert_chunks(
        [
            fazer_chunk(0, f"cab\n{corpo}", documento_id="doc-1"),
            fazer_chunk(0, f"cab\n{corpo}", documento_id="doc-de-outra-sessao"),
        ]
    )
    envio.documento_id = "doc-1"

    assert ingestao.etapa_embeddings(envio).startswith("1 trechos indexados")
    assert {c.documento_id for c in banco.repo.listar_pendentes()} == {"doc-de-outra-sessao"}
    assert banco.repo.documentos_indexados == {"doc-1"}


# --- classificação -----------------------------------------------------------


def test_classificacao_falha_suave_quando_o_llm_recusa(envio, banco, monkeypatch):
    from pharma_ops import classificacao as cl
    from pharma_rag.agent import llm

    class LLM403:
        def __init__(self, *a, **k):
            raise RuntimeError("Error code: 403 - Key limit exceeded (monthly limit)")

    monkeypatch.setattr(llm, "OpenRouterLLM", LLM403)
    monkeypatch.setattr(cl, "carregar_chunks", lambda conn, doc: [cl.ChunkEntrada(0, "texto")])
    envio.documento_id = "doc-1"

    with pytest.raises(ingestao.EtapaAdiada) as exc:
        ingestao.etapa_classificacao(envio)
    msg = str(exc.value)
    assert msg.startswith("pendente — classificar depois com tools/classificar_documentos.py")
    assert "--documento doc-1" in msg and "403" in msg
    assert banco.conn.fechada


def test_classificacao_ok_grava_e_resume(envio, banco, monkeypatch):
    from pharma_ops import classificacao as cl
    from pharma_rag.agent import llm

    gravado = {}
    monkeypatch.setattr(llm, "OpenRouterLLM", lambda **k: object())
    monkeypatch.setattr(cl, "carregar_chunks", lambda conn, doc: [cl.ChunkEntrada(0, "texto")])
    monkeypatch.setattr(
        cl,
        "classificar_documento",
        lambda *a, **k: cl.Resultado(
            {"executante_grupo": {"valor": "principal"}, "disciplinas": [{"valor": "hvac"}]},
            "Resumo.",
            [],
            {"custo_usd": 0.0031},
        ),
    )
    monkeypatch.setattr(cl, "salvar", lambda conn, doc, c, r: gravado.update(doc=doc, resumo=r))
    envio.documento_id = "doc-1"

    detalhe = ingestao.etapa_classificacao(envio)
    assert detalhe == "executante: principal · disciplinas: hvac · US$ 0.0031"
    assert gravado == {"doc": "doc-1", "resumo": "Resumo."}


def test_executar_com_classificacao_adiada_conclui_o_envio(envio, monkeypatch):
    feitas = []

    def ok(chave):
        def etapa(e):
            feitas.append(chave)
            return "ok"

        return etapa

    def adiada(e):
        raise ingestao.EtapaAdiada("pendente — classificar depois com tools/classificar_documentos.py")

    etapas = {c: ok(c) for c in ingestao.ROTULOS}
    etapas["classificacao"] = adiada
    monkeypatch.setattr(ingestao, "ETAPAS", etapas)

    ingestao.executar(envio)
    assert envio.estado == "concluido" and envio.erro is None
    classif = envio.etapa("classificacao")
    assert classif.estado == "pendente" and "classificar_documentos.py" in classif.detalhe
    assert envio.etapa("embeddings").estado == "ok"


# --- teto de OCR ---------------------------------------------------------------


def _triagem_falsa(monkeypatch, paginas_ocr: int, custo: float):
    falso = types.ModuleType("triar_documentos")
    falso.triar = lambda caminho: {
        "paginas_ocr": paginas_ocr,
        "custo_ocr_estimado_usd": custo,
        "metadados": {"titulo_sugerido": {"valor": TITULO}},
    }
    monkeypatch.setitem(sys.modules, "triar_documentos", falso)


def _carregar_main(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MODO_DEMO", "0")
    spec = importlib.util.spec_from_file_location("api_main_teto", RAIZ / "api" / "main.py")
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    return TestClient(main.app)


def test_teto_de_ocr_para_antes_da_extracao_e_aprovar_libera(envio, monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_PAGINAS_OCR", "60")
    _triagem_falsa(monkeypatch, paginas_ocr=72, custo=0.288)
    feitas = []

    def falsa(chave):
        def etapa(e):
            feitas.append(chave)
            return "ok"

        return etapa

    etapas = {c: falsa(c) for c in ingestao.ROTULOS}
    etapas["triagem"] = ingestao.etapa_triagem
    monkeypatch.setattr(ingestao, "ETAPAS", etapas)
    monkeypatch.setattr(ingestao, "enfileirar", ingestao.executar)

    ingestao.executar(envio)
    assert feitas == []  # nada pago rodou
    assert envio.estado == "erro" and envio.aguardando_aprovacao
    esperado = "aguardando aprovação — 72 páginas de OCR, ~US$ 0.29"
    assert envio.erro.startswith(esperado)
    assert envio.etapa("triagem").estado == "ok"
    extracao = envio.etapa("extracao")
    assert extracao.estado == "pendente" and extracao.detalhe.startswith(esperado)

    cliente = _carregar_main(monkeypatch)
    status = cliente.get(f"/uploads/{envio.id}").json()
    assert status["aguardando_aprovacao"] is True and status["estado"] == "erro"

    r = cliente.post(f"/uploads/{envio.id}/aprovar")
    assert r.status_code == 202
    assert envio.estado == "concluido" and not envio.aguardando_aprovacao
    assert feitas == ["extracao", "chunks", "cadastro", "embeddings", "classificacao"]
    assert cliente.post(f"/uploads/{envio.id}/aprovar").status_code == 409


def test_teto_de_ocr_nao_trava_envio_pequeno(envio, monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_PAGINAS_OCR", "60")
    _triagem_falsa(monkeypatch, paginas_ocr=60, custo=0.24)
    assert "60 página(s) precisam de OCR" in ingestao.etapa_triagem(envio)
