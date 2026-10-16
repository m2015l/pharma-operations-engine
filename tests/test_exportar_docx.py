"""Exportação .docx da API (api/exportar_docx.py e POST /exportar/docx).

Roda sem rede e sem custo. Os cenários de `api/fixtures/demo.json` entram
quando o arquivo existe (ele fica fora do git); um cenário sintético cobre os
mesmos casos em qualquer máquina.

    UV_LINK_MODE=copy uv run --extra dev --with-requirements api/requirements.txt \
        pytest -q tests/test_exportar_docx.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

docx = pytest.importorskip("docx", reason="python-docx vem de api/requirements.txt")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))
sys.path.insert(0, str(RAIZ / "src"))

import exportar_docx
from schemas import CitacaoOut, ExportarDocxIn, RespostaOut, TurnoExportado

FIXTURES = RAIZ / "api" / "fixtures" / "demo.json"
GERADO_EM = datetime(2026, 9, 29, 17, 32, tzinfo=UTC)  # 14:32 em São Paulo


def _citacao(n: int, trecho: str = "Trecho **citado** do atestado.") -> CitacaoOut:
    return CitacaoOut(
        marcador=n,
        chunk_chave=f"doc#c{n:04d}",
        documento_id="doc-1",
        titulo_documento="INSTITUTO BIOPHARMA CAT 100200",
        tipo_documento="atestado",
        orgao="INSTITUTO BIOPHARMA",
        secao="3. Serviços > 3.1 Edificação" if n != 2 else "",
        pagina_inicio=3,
        pagina_fim=3 if n != 3 else 5,
        trecho=trecho,
    )


def _sintetico() -> list[TurnoExportado]:
    longo = "palavra " * 200
    return [
        TurnoExportado(
            pergunta="A gente já fez obra de laboratório?",
            resposta=RespostaOut(
                texto=(
                    "Sim, há um atestado [1].\n\n**Escopo:**\n\n"
                    "- Gases especiais [2]\n- Água fria [3][1]\n\n"
                    "1. **Elétrica**: quadros [3]\n2. Citação inventada [9]"
                ),
                citacoes=[_citacao(1), _citacao(2, longo), _citacao(3)],
                trechos_recuperados=8,
                contrato_citacao_ok=False,
                citacoes_invalidas=[9],
                encontrou_no_acervo=True,
                tipo_fluxo="consulta_historico",
                modo="demo",
                origem="auditoria 2026-08-17 turno 1.1",
            ),
        ),
        TurnoExportado(
            pergunta="Temos obra rodoviária?",
            resposta=RespostaOut(
                texto="Não encontrei nada sobre obra rodoviária no acervo.",
                citacoes=[],
                trechos_recuperados=0,
                contrato_citacao_ok=True,
                encontrou_no_acervo=False,
                tipo_fluxo="consulta_historico",
                modo="demo",
            ),
        ),
        TurnoExportado(pergunta="E o prazo?", erro="A API não respondeu."),
    ]


def _cenarios_demo() -> list[TurnoExportado]:
    if not FIXTURES.is_file():
        return []
    import mock  # noqa: UP026 — api/mock.py, o mesmo que /perguntar usa no modo demo

    dados = json.loads(FIXTURES.read_text(encoding="utf-8"))
    turnos = []
    for c in dados["cenarios"]:
        resposta = mock.responder(c["pergunta_exemplo"], [])
        turnos.append(TurnoExportado(pergunta=c["pergunta_exemplo"], resposta=resposta))
    return turnos


def _abrir(conteudo: bytes):
    return docx.Document(io.BytesIO(conteudo))


def _texto(doc) -> str:
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                partes.append(celula.text)
    return "\n".join(partes)


def test_nome_do_arquivo_segue_o_padrao_no_fuso_de_sao_paulo():
    turnos = _sintetico()
    conversa = ExportarDocxIn(gerado_em=GERADO_EM, turnos=turnos)
    resposta = ExportarDocxIn(escopo="resposta", gerado_em=GERADO_EM, turnos=turnos[:1])
    assert exportar_docx.nome_arquivo(conversa) == "consulta-pharma-ops-2026-09-29-1432.docx"
    assert exportar_docx.nome_arquivo(resposta) == "resposta-pharma-ops-2026-09-29-1432.docx"


def test_conversa_sintetica_tem_cabecalho_rodape_marcadores_e_fontes():
    corpo = ExportarDocxIn(gerado_em=GERADO_EM, turnos=_sintetico())
    doc = _abrir(exportar_docx.gerar(corpo))
    texto = _texto(doc)

    secao = doc.sections[0]
    assert "Licitações" in secao.header.paragraphs[0].text
    rodape = secao.footer.paragraphs[0]
    assert exportar_docx.AVISO in rodape.text
    instrucoes = [el.text.strip() for el in rodape._p.iter() if el.tag.endswith("instrText")]
    assert instrucoes == ["PAGE", "NUMPAGES"]

    assert "Consulta ao acervo técnico" in texto
    assert "Gerado em 29/09/2026 às 14:32 · 3 perguntas" in texto
    assert "Modo demonstração" in texto
    assert "Pergunta 1" in texto and "Pergunta 3" in texto
    assert "[1]" in texto and "[3]" in texto
    assert "(fonte inexistente)" in texto
    assert "Resposta sem fonte rastreável" in texto
    assert "3 citadas de 8 trechos recuperados" in texto
    assert "Nada encontrado no acervo" in texto
    assert "Sem resposta (erro: A API não respondeu.)" in texto

    # Só o turno com citações ganha tabela: cabeçalho + 3 fontes.
    assert len(doc.tables) == 1
    linhas = doc.tables[0].rows
    assert len(linhas) == 4
    assert "p. 3–5" in linhas[3].cells[1].text
    assert "folha de rosto (sem seção)" in linhas[2].cells[1].text
    assert "Trecho citado do atestado." in linhas[1].cells[1].text  # ** removido
    trecho_longo = linhas[2].cells[1].paragraphs[-1].text
    assert trecho_longo.endswith("…”") and len(trecho_longo) <= exportar_docx.MAX_TRECHO + 3

    # Marcador válido em negrito teal; inválido riscado.
    runs = [r for p in doc.paragraphs for r in p.runs]
    validos = [r for r in runs if r.text == "[1]"]
    assert validos and all(r.bold and r.font.color.rgb == exportar_docx.TEAL_TEXTO for r in validos)
    assert any(r.text == "[9]" and r.font.strike for r in runs)
    # **negrito** do markdown vira run em negrito, sem os asteriscos.
    assert any(r.text == "Escopo:" and r.bold for r in runs)
    assert "**" not in texto


def test_sem_autor_nos_metadados():
    doc = _abrir(exportar_docx.gerar(ExportarDocxIn(gerado_em=GERADO_EM, turnos=_sintetico())))
    assert doc.core_properties.author == ""
    assert doc.core_properties.last_modified_by == ""


def test_resposta_isolada_usa_titulo_no_singular():
    corpo = ExportarDocxIn(escopo="resposta", gerado_em=GERADO_EM, turnos=_sintetico()[:1])
    texto = _texto(_abrir(exportar_docx.gerar(corpo)))
    assert "Resposta do acervo técnico" in texto
    assert "Pergunta 1" not in texto and "perguntas" not in texto


@pytest.mark.skipif(not FIXTURES.is_file(), reason="api/fixtures/demo.json fica fora do git")
def test_todas_as_respostas_gravadas_do_demo_viram_docx():
    turnos = _cenarios_demo()
    assert turnos
    doc = _abrir(exportar_docx.gerar(ExportarDocxIn(gerado_em=GERADO_EM, turnos=turnos)))
    texto = _texto(doc)
    assert "**" not in texto
    for t in turnos:
        assert t.pergunta in texto
        for c in t.resposta.citacoes:
            assert f"[{c.marcador}]" in texto
    com_fontes = [t for t in turnos if t.resposta.encontrou_no_acervo and t.resposta.citacoes]
    assert len(doc.tables) == len(com_fontes)


# --------------------------------------------------------------------------
# Rota HTTP
# --------------------------------------------------------------------------


@pytest.fixture
def cliente(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MODO_DEMO", "1")
    # Carrega api/main.py por caminho: "main" pode colidir com outro módulo no sys.path.
    spec = importlib.util.spec_from_file_location("api_main_exportar", RAIZ / "api" / "main.py")
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    return TestClient(main.app)


def test_rota_devolve_docx_com_nome_no_content_disposition(cliente):
    corpo = ExportarDocxIn(gerado_em=GERADO_EM, turnos=_sintetico())
    r = cliente.post("/exportar/docx", content=corpo.model_dump_json(),
                     headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'filename="consulta-pharma-ops-2026-09-29-1432.docx"' in r.headers["content-disposition"]
    assert "Consulta ao acervo técnico" in _texto(_abrir(r.content))


def test_rota_valida_corpo_e_limite_de_tamanho(cliente):
    vazio = {"gerado_em": GERADO_EM.isoformat(), "turnos": []}
    assert cliente.post("/exportar/docx", json=vazio).status_code == 422

    grande = b"x" * (5 * 1024 * 1024 + 1)
    r = cliente.post("/exportar/docx", content=grande, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
