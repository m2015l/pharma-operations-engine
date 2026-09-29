"""CLIs sem teste até 29/09 (item 20): avaliar, perguntar, upload_documento, generate_embeddings.

Tudo offline: parsing de argumentos e a lógica pura de cada ferramenta. Nada
abre conexão com o Supabase nem chama API.
"""

from __future__ import annotations

import hashlib
import types

import httpx
import pytest

from solufarma_rag.db.models import ChunkComScore
from solufarma_rag.db.repository import InMemoryChunkRepository
from solufarma_rag.ingestion.embeddings import FakeEmbeddingProvider, gerar_embeddings_pendentes
from tests.falsos import carregar_ferramenta

# --- avaliar.py ---------------------------------------------------------------


@pytest.fixture(scope="module")
def avaliar():
    return carregar_ferramenta("avaliar")


def _res(fazer_chunk, doc, pi, pf=None, score=0.9):
    c = fazer_chunk(1, documento_id=doc, pagina_inicio=pi, pagina_fim=pf or pi)
    return ChunkComScore(chunk=c, score=score)


def test_faixa_de_duas_paginas_e_inclusiva(avaliar):
    assert avaliar._faixa([4, 6]) == {4, 5, 6}
    assert avaliar._faixa([45]) == {45}
    assert avaliar._faixa([1, 3, 9]) == {1, 3, 9}


def test_casa_por_pagina_sem_documento_formato_antigo(avaliar, fazer_chunk):
    r = _res(fazer_chunk, "outro", 1)
    assert avaliar._acertou([r], [1])


def test_casa_exige_documento_quando_informado(avaliar, fazer_chunk):
    # Página 1 de OUTRA CAT não pode contar como acerto.
    assert not avaliar._acertou([_res(fazer_chunk, "outro", 1)], [1], "senai")
    assert avaliar._acertou([_res(fazer_chunk, "senai", 1)], [1], "senai")


def test_chunk_que_cruza_paginas_casa_pela_sobreposicao(avaliar, fazer_chunk):
    assert avaliar._acertou([_res(fazer_chunk, "d", 44, 46)], [45])


def test_controle_negativo_acerta_quando_volta_vazio(avaliar, fazer_chunk):
    assert avaliar._acertou([], [])
    assert not avaliar._acertou([_res(fazer_chunk, "d", 1)], [])


def test_avaliar_agrega_recall_e_controles(avaliar, fazer_chunk):
    casos = [
        {"pergunta": "a", "esperado_paginas": [1], "documento_id": "d1", "documento": "Doc 1"},
        {"pergunta": "b", "esperado_paginas": [2], "documento_id": "d1"},
        {"pergunta": "nada", "esperado_paginas": []},
    ]
    respostas = {
        "a": [_res(fazer_chunk, "d1", 1)],
        "b": [_res(fazer_chunk, "d2", 2)],  # página certa, documento errado
        "nada": [],
    }
    r = avaliar.avaliar(lambda pergunta, top_k: respostas[pergunta], casos, top_k=5)
    assert (r["acertos"], r["total"], r["negativos_ok"], r["negativos_total"]) == (1, 2, 1, 1)
    assert r["linhas"][0]["documento"] == "Doc 1"


def test_calibrar_offline_recomenda_piso(avaliar, fazer_chunk, capsys):
    repo = InMemoryChunkRepository()
    repo.upsert_chunks([
        fazer_chunk(1, "autoclave horizontal de cem litros aço inox", documento_id="d1",
                    pagina_inicio=3, pagina_fim=3, content_hash="h1"),
        fazer_chunk(2, "centrífuga laboratorial refrigerada garantia", documento_id="d1",
                    pagina_inicio=4, pagina_fim=4, content_hash="h2"),
    ])
    provider = FakeEmbeddingProvider()
    gerar_embeddings_pendentes(repo, provider)
    casos = [
        {"pergunta": "autoclave horizontal cem litros", "esperado_paginas": [3],
         "documento_id": "d1"},
        {"pergunta": "usina nuclear capacidade megawatts", "esperado_paginas": []},
    ]
    avaliar.calibrar(repo, provider, casos, pool=5)
    saida = capsys.readouterr().out
    assert "SIMILARIDADE_MINIMA=" in saida


def test_parser_avaliar(avaliar):
    a = avaliar.construir_parser().parse_args(["--provedor", "voyage", "--calibrar"])
    assert (a.provedor, a.calibrar, a.top_k, a.lexico, a.salvar) == ("voyage", True, 5, False, False)


def test_golden_set_versionado_e_bem_formado():
    import json

    from tests.falsos import RAIZ_REPO

    casos = json.loads((RAIZ_REPO / "data" / "golden_set.json").read_text(encoding="utf-8"))
    positivos = [c for c in casos if c["esperado_paginas"]]
    negativos = [c for c in casos if not c["esperado_paginas"]]
    assert positivos and negativos
    # Com vários documentos no acervo, página sozinha é ambígua.
    assert all(c.get("documento_id") for c in positivos)
    assert len({c["pergunta"] for c in casos}) == len(casos)


# --- perguntar.py -------------------------------------------------------------


@pytest.fixture(scope="module")
def perguntar():
    return carregar_ferramenta("perguntar")


def test_parser_perguntar(perguntar):
    a = perguntar.construir_parser().parse_args(["tem sala limpa?", "--so-busca"])
    assert (a.pergunta, a.so_busca, a.top_k, a.orgao, a.tipo) == (
        "tem sala limpa?", True, 8, None, None,
    )
    assert perguntar.construir_parser().parse_args([]).pergunta is None  # modo interativo


def test_filtros_vazios_nao_viram_filtro(perguntar):
    assert perguntar.montar_filtros(None, "") == perguntar.FiltrosBusca()
    f = perguntar.montar_filtros("Butantan", "atestado")
    assert (f.orgao, f.tipo_documento) == ("Butantan", "atestado")


def test_mostrar_busca_sem_resultado_avisa_do_piso(perguntar, capsys):
    buscador = types.SimpleNamespace(buscar=lambda *a: [])
    assert perguntar._mostrar_busca(buscador, "x", perguntar.FiltrosBusca(), 5) == []
    assert "piso de relevância" in capsys.readouterr().out


# --- upload_documento.py --------------------------------------------------------


@pytest.fixture(scope="module")
def upload():
    return carregar_ferramenta("upload_documento")


def test_sanitizar_remove_acento_e_espaco(upload):
    assert upload.sanitizar("Implant. laboratório ISI.pdf") == "Implant.-laboratorio-ISI.pdf"
    assert upload.sanitizar("Câmara  fria [conteudo real].pdf") == "Camara-fria-conteudo-real-.pdf"


def test_storage_path_tem_prefixo_de_hash(upload, tmp_path):
    arq = tmp_path / "Edital nº 1.pdf"
    arq.write_bytes(b"abc")
    h = upload.sha256_arquivo(arq)
    assert h == hashlib.sha256(b"abc").hexdigest()
    assert upload.montar_storage_path(arq, h) == f"{h[:16]}/Edital-no-1.pdf"


def _cliente(status: int, registro: list):
    def responder(request: httpx.Request) -> httpx.Response:
        registro.append(request)
        return httpx.Response(status, text="erro" if status >= 400 else "{}")

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_enviar_usa_apikey_e_upsert(upload, tmp_path):
    arq = tmp_path / "doc.pdf"
    arq.write_bytes(b"%PDF")
    pedidos: list = []
    with _cliente(200, pedidos) as client:
        caminho, h = upload.enviar(client, "https://x.supabase.co", "sb_secret_x", arq)
    (req,) = pedidos
    assert caminho == f"{h[:16]}/doc.pdf"
    assert req.url.path == f"/storage/v1/object/documentos/{caminho}"
    assert req.headers["apikey"] == "sb_secret_x"
    assert "authorization" not in req.headers  # Bearer quebra com a chave nova
    assert req.headers["x-upsert"] == "true"


def test_enviar_erro_http_vira_runtime_error(upload, tmp_path):
    arq = tmp_path / "doc.pdf"
    arq.write_bytes(b"%PDF")
    with _cliente(403, []) as client, pytest.raises(RuntimeError, match="HTTP 403"):
        upload.enviar(client, "https://x", "k", arq)


def test_enviar_recusa_acima_do_limite_sem_rede(upload, tmp_path, monkeypatch):
    arq = tmp_path / "grande.pdf"
    arq.write_bytes(b"x" * 11)
    monkeypatch.setattr(upload, "LIMITE_BYTES", 10)
    pedidos: list = []
    with _cliente(200, pedidos) as client, pytest.raises(ValueError, match="excede"):
        upload.enviar(client, "https://x", "k", arq)
    assert pedidos == []


def test_upload_sem_argumentos_e_erro_de_uso(upload):
    with pytest.raises(SystemExit):
        upload.main([])


# --- generate_embeddings.py -----------------------------------------------------


@pytest.fixture(scope="module")
def gerar():
    return carregar_ferramenta("generate_embeddings")


def test_reset_nao_combina_com_documento_id(gerar):
    with pytest.raises(SystemExit):
        gerar.main(["--reset", "--documento-id", "abc"])


def test_documento_id_repetivel(gerar):
    a = gerar.construir_parser().parse_args(["--documento-id", "a", "--documento-id", "b"])
    assert a.documento_id == ["a", "b"]


def test_repo_restrito_so_embedda_os_documentos_pedidos(gerar, fazer_chunk):
    corpo = "conteúdo com corpo suficiente para passar do filtro de ruído"
    repo = InMemoryChunkRepository()
    repo.upsert_chunks([
        fazer_chunk(1, corpo, documento_id="meu", content_hash="m1"),
        fazer_chunk(1, corpo, documento_id="da-outra-sessao", content_hash="o1"),
    ])
    relatorio = gerar_embeddings_pendentes(gerar.RepoRestrito(repo, {"meu"}), FakeEmbeddingProvider())

    assert relatorio.embeddados == 1
    assert relatorio.documentos_indexados == ["meu"]
    assert [c.documento_id for c in repo.listar_pendentes()] == ["da-outra-sessao"]
