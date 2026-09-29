"""tools/indexar.py — método de extração pelas rotas das páginas + fluxo com dublês."""

from __future__ import annotations

import json
import sys
import types

import pytest

from solufarma_rag.db.repository import InMemoryChunkRepository
from tests.falsos import ConexaoFalsa, carregar_ferramenta

STEM = "CAT 123 Teste"
TITULO = "Câmara Fria (CAT SJC-01975)"


@pytest.fixture
def indexar():
    return carregar_ferramenta("indexar")


def _paginas(*rotas):
    return [{"numero": i, "estrategia": r} for i, r in enumerate(rotas, start=1)]


@pytest.mark.parametrize(
    "rotas, esperado",
    [
        (("nativo", "nativo"), (False, "nativo")),
        (("vlm", "vlm"), (True, "vlm")),
        (("vazia",), (True, "vlm")),  # foi ao VLM e voltou vazia: chamada aconteceu
        (("nativo", "vlm"), (True, "misto")),
        (("nativo", "vazia"), (True, "misto")),
        (("pendente",), None),
        ((), None),
    ],
)
def test_metodo_extracao_pelas_rotas(indexar, rotas, esperado):
    assert indexar.metodo_extracao(_paginas(*rotas)) == esperado


def test_detectar_extracao_le_o_json_do_stem(indexar, tmp_path):
    (tmp_path / f"{STEM}.json").write_text(
        json.dumps({"paginas": _paginas("nativo", "vlm")}), encoding="utf-8"
    )
    assert indexar.detectar_extracao(STEM, tmp_path) == (True, "misto")
    assert indexar.detectar_extracao("outro", tmp_path) is None


def test_parser_padroes(indexar):
    args = indexar.construir_parser().parse_args(["x.pdf", "--orgao", "FURP"])
    assert (args.pdf, args.orgao, args.tipo, args.titulo, args.dry_run) == (
        "x.pdf", "FURP", "edital", None, False,
    )


def test_parser_exige_orgao(indexar):
    with pytest.raises(SystemExit):
        indexar.construir_parser().parse_args(["x.pdf"])


# --- fluxo main() com diretórios temporários ----------------------------------


@pytest.fixture
def ambiente(indexar, tmp_path, monkeypatch):
    """PDF + chunks (+ extração opcional) em tmp_path, com os DIR_* apontando para lá."""
    brutos, chunks, extraidos = (tmp_path / d for d in ("brutos", "chunks", "extraidos"))
    for d in (brutos, chunks, extraidos):
        d.mkdir()
    pdf = brutos / f"{STEM}.pdf"
    pdf.write_bytes(b"%PDF-1.4 falso")
    lote = [
        {"id": f"h#c{i:04d}", "texto": f"[{TITULO} | p. {i}] corpo {i}", "documento": TITULO,
         "caminho_secao": [], "pagina_inicio": i, "pagina_fim": i}
        for i in (1, 2)
    ]
    (chunks / f"{STEM}_chunks.json").write_text(json.dumps(lote), encoding="utf-8")
    monkeypatch.setattr(indexar, "DIR_CHUNKS", chunks)
    monkeypatch.setattr(indexar, "DIR_EXTRAIDOS", extraidos)
    return types.SimpleNamespace(pdf=pdf, extraidos=extraidos)


def test_dry_run_nao_escreve_e_mostra_metodo(indexar, ambiente, capsys):
    (ambiente.extraidos / f"{STEM}.json").write_text(
        json.dumps({"paginas": _paginas("nativo", "nativo")}), encoding="utf-8"
    )
    assert indexar.main([str(ambiente.pdf), "--orgao", "X", "--tipo", "atestado", "--dry-run"]) == 0
    saida = capsys.readouterr().out
    assert "extração: nativo (ocr_aplicado=False)" in saida
    assert "2 chunks traduzidos e validados" in saida


def test_titulo_divergente_sai_com_2(indexar, ambiente):
    argv = [str(ambiente.pdf), "--orgao", "X", "--titulo", "Outro", "--dry-run"]
    assert indexar.main(argv) == 2


def test_pdf_inexistente_sai_com_1(indexar, tmp_path):
    assert indexar.main([str(tmp_path / "nao.pdf"), "--orgao", "X"]) == 1


@pytest.fixture
def dubles(indexar, monkeypatch):
    """Troca Storage, conexão, cadastro e repositório por dublês que gravam as chamadas."""
    chamadas: dict = {}
    upload = types.ModuleType("upload_documento")
    upload._credenciais = lambda: ("http://supabase.invalido", "chave")
    upload.enviar = lambda client, url, chave, pdf: ("h/doc.pdf", "a" * 64)
    monkeypatch.setitem(sys.modules, "upload_documento", upload)

    conn = ConexaoFalsa()
    monkeypatch.setattr(indexar, "criar_conexao", lambda: conn)

    def cadastrar(conn, **kw):
        chamadas["cadastro"] = kw
        return "doc-1", True

    monkeypatch.setattr(indexar, "cadastrar_documento", cadastrar)
    repo = InMemoryChunkRepository()
    monkeypatch.setattr(indexar, "SupabaseChunkRepository", lambda conn: repo)
    chamadas.update(conn=conn, repo=repo)
    return chamadas


@pytest.mark.parametrize(
    "rotas, esperado",
    [(("nativo",), (False, "nativo")), (("vlm", "nativo"), (True, "misto"))],
)
def test_main_grava_metodo_derivado(indexar, ambiente, dubles, rotas, esperado):
    (ambiente.extraidos / f"{STEM}.json").write_text(
        json.dumps({"paginas": _paginas(*rotas)}), encoding="utf-8"
    )
    assert indexar.main([str(ambiente.pdf), "--orgao", "X", "--tipo", "atestado"]) == 0

    cad = dubles["cadastro"]
    assert (cad["ocr_aplicado"], cad["metodo_extracao"]) == esperado
    assert cad["titulo"] == TITULO
    assert dubles["repo"].total_chunks() == 2
    assert dubles["conn"].fechada


def test_main_sem_json_de_extracao_mantem_vlm_com_aviso(indexar, ambiente, dubles, capsys):
    assert indexar.main([str(ambiente.pdf), "--orgao", "X", "--tipo", "atestado"]) == 0
    cad = dubles["cadastro"]
    assert (cad["ocr_aplicado"], cad["metodo_extracao"]) == (True, "vlm")
    assert "não encontrado" in capsys.readouterr().err


def test_main_reindexacao_remove_orfaos(indexar, ambiente, dubles, fazer_chunk, capsys):
    # Chunk 3 é de uma indexação anterior: o chunking novo só gera 1 e 2.
    dubles["repo"].upsert_chunks([fazer_chunk(3, "velho", documento_id="doc-1")])
    assert indexar.main([str(ambiente.pdf), "--orgao", "X", "--tipo", "atestado"]) == 0
    assert dubles["repo"].total_chunks() == 2
    assert "órfãos removidos: 1" in capsys.readouterr().out
