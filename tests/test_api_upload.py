"""Upload real da API (F9): POST /upload + GET /uploads/{id} com as etapas MOCKADAS.

Nenhum teste chama OCR, Storage, banco ou embedding — `ingestao.ETAPAS` é
trocado por funções falsas e a fila roda de forma síncrona.

    UV_LINK_MODE=copy uv run --extra dev --with-requirements api/requirements.txt \
        pytest -q tests/test_api_upload.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart", reason="python-multipart vem de api/requirements.txt")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))
sys.path.insert(0, str(RAIZ / "src"))

import ingestao

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
ORDEM = ["triagem", "extracao", "chunks", "cadastro", "embeddings", "classificacao"]


def _carregar_main(monkeypatch, modo_demo: str):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MODO_DEMO", modo_demo)
    monkeypatch.setenv("MODO_DEMO_LATENCIA", "0")
    spec = importlib.util.spec_from_file_location(f"api_main_upload_{modo_demo}", RAIZ / "api" / "main.py")
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    assert main.ingestao is ingestao
    return TestClient(main.app)


@pytest.fixture
def chamadas(monkeypatch, tmp_path):
    """Etapas falsas que registram a ordem; fila síncrona; PDFs em tmp_path."""
    feitas: list[str] = []

    def falsa(chave):
        def etapa(envio):
            feitas.append(chave)
            if chave == "triagem":
                envio.titulo = "CAT 123 — Instituto Butantan — Biotério"
            if chave == "cadastro":
                envio.documento_id = "00000000-0000-0000-0000-000000000001"
            return f"{chave} ok"

        return etapa

    monkeypatch.setattr(ingestao, "ETAPAS", {c: falsa(c) for c in ORDEM})
    monkeypatch.setattr(ingestao, "PASTA_UPLOADS", tmp_path / "brutos")
    monkeypatch.setattr(ingestao, "enfileirar", ingestao.executar)
    monkeypatch.setattr(ingestao, "_ENVIOS", {})
    return feitas


def _enviar(cliente, conteudo=PDF, **form):
    dados = {"orgao": "Instituto Butantan", **form}
    return cliente.post("/upload", data=dados, files={"arquivo": ("cat 123.pdf", conteudo, "application/pdf")})


def test_modo_real_guarda_o_pdf_e_roda_as_etapas_em_ordem(monkeypatch, chamadas):
    cliente = _carregar_main(monkeypatch, "0")
    r = _enviar(cliente)
    assert r.status_code == 202
    corpo = r.json()
    assert corpo["status"] == "na_fila" and corpo["tipo"] == "atestado"
    assert corpo["envio_id"]

    assert (ingestao.PASTA_UPLOADS / "cat_123.pdf").read_bytes() == PDF
    assert chamadas == ORDEM

    status = cliente.get(f"/uploads/{corpo['envio_id']}").json()
    assert status["estado"] == "concluido"
    assert [e["estado"] for e in status["etapas"]] == ["ok"] * len(ORDEM)
    assert [e["chave"] for e in status["etapas"]] == ORDEM
    assert status["titulo"] == "CAT 123 — Instituto Butantan — Biotério"
    assert status["documento_id"].endswith("0001")

    lista = cliente.get("/uploads").json()
    assert [e["id"] for e in lista] == [corpo["envio_id"]]


def test_falha_numa_etapa_para_o_envio_e_mostra_o_erro(monkeypatch, chamadas):
    def extracao_quebra(envio):
        raise RuntimeError("OPENROUTER_API_KEY ausente")

    ingestao.ETAPAS["extracao"] = extracao_quebra
    cliente = _carregar_main(monkeypatch, "0")
    envio_id = _enviar(cliente).json()["envio_id"]

    status = cliente.get(f"/uploads/{envio_id}").json()
    assert status["estado"] == "erro"
    assert "OPENROUTER_API_KEY ausente" in status["erro"]
    estados = {e["chave"]: e["estado"] for e in status["etapas"]}
    assert estados == {
        "triagem": "ok", "extracao": "erro", "chunks": "pendente",
        "cadastro": "pendente", "embeddings": "pendente", "classificacao": "pendente",
    }
    assert chamadas == ["triagem"]


def test_modo_demo_simula_sem_guardar_nem_processar(monkeypatch, chamadas):
    cliente = _carregar_main(monkeypatch, "1")
    r = _enviar(cliente)
    assert r.status_code == 202
    corpo = r.json()
    assert corpo["status"] == "simulado"
    assert corpo["envio_id"] is None
    assert "nada foi guardado" in corpo["mensagem"]
    assert not ingestao.PASTA_UPLOADS.exists()
    assert chamadas == []
    assert cliente.get("/uploads").json() == []


def test_validacoes_do_upload(monkeypatch, chamadas):
    cliente = _carregar_main(monkeypatch, "0")
    assert _enviar(cliente, conteudo=b"nao e pdf").status_code == 415
    assert _enviar(cliente, tipo="receita").status_code == 422
    assert cliente.get("/uploads/nao-existe").status_code == 404
    assert chamadas == []


def test_guardar_nao_sobrescreve_arquivo_diferente_com_o_mesmo_nome(tmp_path):
    a = ingestao.guardar(PDF, "Atestado Ç.pdf", tmp_path)
    b = ingestao.guardar(PDF, "Atestado Ç.pdf", tmp_path)
    c = ingestao.guardar(PDF + b"x", "Atestado Ç.pdf", tmp_path)
    assert a == b and a.name == "Atestado_C.pdf"
    assert c != a and c.read_bytes() == PDF + b"x"


# --------------------------------------------------------------------------
# Etapas reais com as dependências trocadas (triagem e chunks)
# --------------------------------------------------------------------------


def _envio(tmp_path) -> ingestao.Envio:
    caminho = tmp_path / "nome_trocado.pdf"
    caminho.write_bytes(PDF)
    return ingestao.criar_envio(caminho, "nome_trocado.pdf", "SENAI CETIQT", "atestado")


def test_triagem_usa_o_titulo_do_conteudo_e_avisa_custo_de_ocr(monkeypatch, tmp_path):
    falso = types.ModuleType("triar_documentos")
    falso.triar = lambda caminho: {
        "paginas_ocr": 3,
        "custo_ocr_estimado_usd": 0.012,
        "metadados": {"titulo_sugerido": {"valor": "CAT 576640 — SENAI CETIQT — Laboratório"}},
    }
    monkeypatch.setitem(sys.modules, "triar_documentos", falso)
    envio = _envio(tmp_path)
    detalhe = ingestao.etapa_triagem(envio)
    assert envio.titulo == "CAT 576640 — SENAI CETIQT — Laboratório"
    assert "3 página(s) precisam de OCR" in detalhe


def test_triagem_sem_titulo_no_conteudo_nao_usa_so_o_nome_do_arquivo(monkeypatch, tmp_path):
    falso = types.ModuleType("triar_documentos")
    falso.triar = lambda caminho: {"paginas_ocr": 0, "metadados": {"titulo_sugerido": {"valor": None}}}
    monkeypatch.setitem(sys.modules, "triar_documentos", falso)
    envio = _envio(tmp_path)
    detalhe = ingestao.etapa_triagem(envio)
    assert envio.titulo == "SENAI CETIQT — nome trocado"
    assert "confira" in detalhe


def test_chunks_recebem_o_titulo_da_triagem(monkeypatch, tmp_path):
    from solufarma import chunking

    recebido = {}

    def chunkar_falso(doc, titulo=None):
        recebido["titulo"] = titulo
        return [], [{"linha": 1}]

    monkeypatch.setattr(chunking, "chunkar_documento", chunkar_falso)
    envio = _envio(tmp_path)
    envio.titulo = "CAT 1 — Órgão — Objeto"
    envio.contexto["extracao"] = {"arquivo": "x.pdf", "hash_documento": "abc", "paginas": []}
    assert ingestao.etapa_chunks(envio) == "0 trechos, 1 linhas de planilha"
    assert recebido["titulo"] == "CAT 1 — Órgão — Objeto"
