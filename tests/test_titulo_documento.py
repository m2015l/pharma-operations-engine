"""
Título do documento não pode vir do nome do arquivo (achado de 28/09).

Cobre o encadeamento: chunking (cabeçalho de cada chunk) -> CLI de chunks
(--titulo) -> tools/indexar.py (recusa --titulo divergente dos chunks).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pharma_ops import chunking, cli

RAIZ = Path(__file__).resolve().parents[1]
TITULO_REAL = "Atestado Laboratório Químico Central Indústrias Químicas - vapor puro"


def _carregar_indexar():
    spec = importlib.util.spec_from_file_location("indexar", RAIZ / "tools" / "indexar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- chunking ---------------------------------------------------------------


def test_sem_titulo_usa_nome_do_arquivo_como_fallback(documento_extraido):
    chunks, _ = chunking.chunkar_documento(documento_extraido)
    assert all(c.documento == "INSTITUTO BIOPHARMA CAT 100200" for c in chunks)
    assert all(c.texto.startswith("[INSTITUTO BIOPHARMA CAT 100200 |") for c in chunks)


def test_titulo_explicito_vai_para_o_cabecalho_de_todo_chunk(documento_extraido):
    chunks, _ = chunking.chunkar_documento(documento_extraido, titulo=TITULO_REAL)
    assert chunks
    for c in chunks:
        assert c.documento == TITULO_REAL
        assert c.texto.startswith(f"[{TITULO_REAL} |")
        assert "INSTITUTO BIOPHARMA CAT 100200" not in c.texto.split("]")[0]


def test_titulo_no_json_de_extracao_e_respeitado(documento_extraido):
    doc = {**documento_extraido, "titulo": TITULO_REAL}
    chunks, _ = chunking.chunkar_documento(doc)
    assert {c.documento for c in chunks} == {TITULO_REAL}


def test_parametro_tem_precedencia_sobre_json(documento_extraido):
    doc = {**documento_extraido, "titulo": "do json"}
    chunks, _ = chunking.chunkar_documento(doc, titulo="do parametro")
    assert {c.documento for c in chunks} == {"do parametro"}


def test_titulo_em_branco_cai_no_fallback(documento_extraido):
    chunks, _ = chunking.chunkar_documento(documento_extraido, titulo="   ")
    assert {c.documento for c in chunks} == {"INSTITUTO BIOPHARMA CAT 100200"}


# --- CLI de chunks -----------------------------------------------------------


def test_cli_chunks_grava_titulo(tmp_path, documento_extraido):
    entrada = tmp_path / "INSTITUTO BIOPHARMA_CAT_100200.json"
    entrada.write_text(json.dumps(documento_extraido), encoding="utf-8")
    saida = tmp_path / "chunks"

    rc = cli.main_chunks([str(entrada), "--saida", str(saida), "--titulo", TITULO_REAL])

    assert rc == 0
    gravados = json.loads((saida / "INSTITUTO BIOPHARMA_CAT_100200_chunks.json").read_text("utf-8"))
    assert {c["documento"] for c in gravados} == {TITULO_REAL}


def test_cli_chunks_recusa_titulo_com_varios_jsons(tmp_path, documento_extraido):
    for nome in ("a.json", "b.json"):
        (tmp_path / nome).write_text(json.dumps(documento_extraido), encoding="utf-8")
    rc = cli.main_chunks([str(tmp_path), "--saida", str(tmp_path / "out"), "--titulo", "X"])
    assert rc == 2


# --- indexar.py ----------------------------------------------------------------


@pytest.fixture(scope="module")
def indexar():
    return _carregar_indexar()


def test_indexar_sem_titulo_herda_o_dos_chunks(indexar):
    chunks = [{"documento": TITULO_REAL}, {"documento": TITULO_REAL}]
    assert indexar.resolver_titulo(None, chunks) == TITULO_REAL


def test_indexar_titulo_igual_ao_dos_chunks_passa(indexar):
    chunks = [{"documento": TITULO_REAL}]
    assert indexar.resolver_titulo(f"  {TITULO_REAL} ", chunks) == TITULO_REAL


def test_indexar_recusa_titulo_divergente(indexar):
    chunks = [{"documento": "COMPLEXO FARMACEUTICO INDUSTRIAL ATESTADO OBRA II"}]
    with pytest.raises(indexar.TituloDivergente, match="Re-gere os chunks"):
        indexar.resolver_titulo(TITULO_REAL, chunks)


def test_indexar_recusa_chunks_com_titulos_mistos(indexar):
    chunks = [{"documento": "A"}, {"documento": "B"}]
    with pytest.raises(indexar.TituloDivergente):
        indexar.resolver_titulo(None, chunks)


def test_indexar_chunks_legados_sem_campo_exigem_titulo(indexar):
    with pytest.raises(indexar.TituloDivergente):
        indexar.resolver_titulo(None, [{"id": "x"}])
    assert indexar.resolver_titulo("Manual", [{"id": "x"}]) == "Manual"
