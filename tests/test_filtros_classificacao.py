"""Filtros pela classificação por IA (executante_grupo, disciplinas) e a regra da Enterprise Vendor Hub.

Tudo offline: repositório em memória, provedor de embeddings fake e FakeLLM.
"""

from __future__ import annotations

import json
import logging

import pytest

from pharma_rag.agent.agent import MSG_SEM_RESULTADOS, AgenteLicitacoes
from pharma_rag.agent.citations import montar_contexto
from pharma_rag.agent.llm import FakeLLM
from pharma_rag.agent.prompts import PROMPT_INTERPRETAR
from pharma_rag.db import repository
from pharma_rag.db.models import ChunkComScore
from pharma_rag.db.repository import FiltrosBusca, InMemoryChunkRepository
from pharma_rag.ingestion.embeddings import FakeEmbeddingProvider, gerar_embeddings_pendentes
from pharma_rag.retrieval.hybrid_search import HybridSearcher


def _cls(grupo: str, executante: str, *disciplinas: str) -> dict:
    return {
        "executante": {"valor": executante, "pagina": 1},
        "executante_grupo": {"valor": grupo, "pagina": 1, "trecho": "x"},
        "disciplinas": [{"valor": d, "pagina": 2} for d in disciplinas],
        "meta": {"versao_schema": 1},
    }


PRINCIPAL = _cls("principal", "Pharma Operations Platform Ltda.", "hvac", "sala_limpa")
COLIGADA = _cls("coligada", "Enterprise Vendor Hub Engenharia", "eletrica")


@pytest.fixture
def repo(fazer_chunk) -> InMemoryChunkRepository:
    """Três documentos sobre sala limpa: Pharma Operations Platform (HVAC), Enterprise Vendor Hub (elétrica), não classificado."""
    r = InMemoryChunkRepository()
    texto = "execução de sala limpa ISO 7 com climatização e painéis para laboratório"
    r.upsert_chunks(
        [
            fazer_chunk(0, f"[A]\n{texto} farmacêutico", documento_id="doc-pharma-ops", tipo_documento="atestado"),
            fazer_chunk(0, f"[B]\n{texto} de vacinas", documento_id="doc-coligada", tipo_documento="atestado"),
            fazer_chunk(0, f"[C]\n{texto} hospitalar", documento_id="doc-sem-classificacao", tipo_documento="atestado"),
        ]
    )
    gerar_embeddings_pendentes(r, FakeEmbeddingProvider())
    r.definir_classificacao("doc-pharma-ops", PRINCIPAL)
    r.definir_classificacao("doc-coligada", COLIGADA)
    return r


def _docs(resultados) -> set[str]:
    return {r.chunk.documento_id for r in resultados}


# --- FiltrosBusca / repositório ---------------------------------------------


def test_containment_espelha_o_jsonb():
    assert FiltrosBusca().classificacao_exigida() is None
    f = FiltrosBusca(executante_grupo="principal", disciplinas=["hvac"])
    assert f.classificacao_exigida() == {
        "executante_grupo": {"valor": "principal"},
        "disciplinas": [{"valor": "hvac"}],
    }
    assert f.aceita_classificacao(PRINCIPAL)
    assert not f.aceita_classificacao(COLIGADA)
    assert not f.aceita_classificacao(None)  # não classificado sai com filtro
    assert FiltrosBusca().aceita_classificacao(None)  # ... e fica sem filtro
    # Várias disciplinas = TODAS (containment de array).
    assert FiltrosBusca(disciplinas=["hvac", "sala_limpa"]).aceita_classificacao(PRINCIPAL)
    assert not FiltrosBusca(disciplinas=["hvac", "eletrica"]).aceita_classificacao(PRINCIPAL)


def test_busca_sem_filtro_nao_perde_documento_nao_classificado(repo):
    resultados = HybridSearcher(repo=repo, provider=FakeEmbeddingProvider()).buscar("sala limpa ISO 7")
    assert _docs(resultados) == {"doc-pharma-ops", "doc-coligada", "doc-sem-classificacao"}
    por_doc = {r.chunk.documento_id: r.chunk for r in resultados}
    assert por_doc["doc-coligada"].executante_grupo == "coligada"
    assert por_doc["doc-pharma-ops"].executante == "Pharma Operations Platform Ltda."
    assert por_doc["doc-sem-classificacao"].executante_grupo is None


@pytest.mark.parametrize(
    "filtros, esperado",
    [
        (FiltrosBusca(executante_grupo="principal"), {"doc-pharma-ops"}),
        (FiltrosBusca(executante_grupo="coligada"), {"doc-coligada"}),
        (FiltrosBusca(disciplinas=["hvac"]), {"doc-pharma-ops"}),
        (FiltrosBusca(disciplinas=["eletrica"]), {"doc-coligada"}),
        (FiltrosBusca(executante_grupo="coligada", disciplinas=["hvac"]), set()),
    ],
)
def test_busca_com_filtro_de_classificacao(repo, filtros, esperado):
    searcher = HybridSearcher(repo=repo, provider=FakeEmbeddingProvider())
    assert _docs(searcher.buscar("sala limpa ISO 7", filtros)) == esperado


def test_sql_do_filtro_e_containment_parametrizado():
    assert "d.classificacao @> %(classificacao)s::jsonb" in repository._WHERE_FILTROS
    assert "%(classificacao)s::jsonb is null" in repository._WHERE_FILTROS
    assert repository._params_filtros(FiltrosBusca())["classificacao"] is None
    param = repository._params_filtros(FiltrosBusca(executante_grupo="principal"))
    assert json.loads(param["classificacao"]) == {"executante_grupo": {"valor": "principal"}}
    # As colunas novas vêm depois do score: os índices antigos não mudam.
    sql = repository._SELECT_CHUNK.format(score="0.0")
    assert sql.index("as score") < sql.index("'{executante,valor}'")


def test_contar_documentos_sem_classificacao(repo):
    assert repo.contar_documentos_sem_classificacao() == 1


# --- agente: interpretação ---------------------------------------------------


class SearcherGravador:
    def __init__(self, respostas: list[list[ChunkComScore]] | None = None):
        self.respostas = list(respostas or [])
        self.filtros: list[FiltrosBusca] = []

    def buscar(self, consulta, filtros=None, top_k=5):
        self.filtros.append(filtros)
        return self.respostas.pop(0) if self.respostas else []


def _interp(**filtros) -> str:
    base = {"orgao": None, "tipo_documento": None, "data_inicio": None, "data_fim": None}
    return json.dumps(
        {"tipo_fluxo": "consulta_historico", "consultas": ["sala limpa"], "filtros": base | filtros}
    )


def test_prompt_de_interpretacao_oferece_os_filtros_de_classificacao():
    prompt = PROMPT_INTERPRETAR.format(pergunta="só atestados da Pharma Operations Platform")
    assert '"executante_grupo": null' in prompt and '"disciplinas": []' in prompt
    assert "hvac" in prompt and "{disciplinas}" not in prompt


def test_interpretacao_extrai_e_valida_os_filtros(fazer_chunk):
    searcher = SearcherGravador([[ChunkComScore(chunk=fazer_chunk(0, "x"), score=1.0)]])
    llm = FakeLLM(
        respostas=[
            _interp(executante_grupo="Principal", disciplinas=["HVAC", "Inventada"]),
            "Resposta [1].",
        ]
    )
    AgenteLicitacoes(searcher=searcher, llm=llm).responder("Só atestados da Pharma Operations Platform de HVAC")
    f = searcher.filtros[0]
    assert (f.executante_grupo, f.disciplinas) == ("principal", ["hvac"])


def test_interpretacao_sem_pedido_explicito_nao_filtra(fazer_chunk):
    searcher = SearcherGravador([[ChunkComScore(chunk=fazer_chunk(0, "x"), score=1.0)]])
    llm = FakeLLM(respostas=[_interp(executante_grupo=None, disciplinas=[]), "Ok [1]."])
    AgenteLicitacoes(searcher=searcher, llm=llm).responder("Já fizemos sala limpa?")
    assert searcher.filtros[0].classificacao_exigida() is None


def test_grupo_fora_do_vocabulario_e_descartado(fazer_chunk, caplog):
    searcher = SearcherGravador([[ChunkComScore(chunk=fazer_chunk(0, "x"), score=1.0)]])
    llm = FakeLLM(respostas=[_interp(executante_grupo="acme"), "Ok [1]."])
    with caplog.at_level(logging.WARNING):
        AgenteLicitacoes(searcher=searcher, llm=llm).responder("x")
    assert searcher.filtros[0].executante_grupo is None
    assert "fora do vocabulário" in caplog.text


def test_refinamento_mantem_o_filtro_de_classificacao_e_avisa_quando_vazio():
    searcher = SearcherGravador()
    llm = FakeLLM(respostas=[_interp(executante_grupo="principal"), "sala limpa classificada"])
    resposta = AgenteLicitacoes(searcher=searcher, llm=llm).responder("só da Pharma Operations Platform")
    assert [f.executante_grupo for f in searcher.filtros] == ["principal", "principal"]
    assert not resposta.encontrou_no_acervo
    assert resposta.texto.startswith(MSG_SEM_RESULTADOS)
    assert "executante principal" in resposta.texto and "não classificados" in resposta.texto


def test_filtro_ativo_registra_no_log_os_nao_classificados(repo, caplog):
    llm = FakeLLM(respostas=[_interp(executante_grupo="principal"), "Fizemos [1]."])
    agente = AgenteLicitacoes(
        searcher=HybridSearcher(repo=repo, provider=FakeEmbeddingProvider()),
        llm=llm,
        repo_itens=repo,
    )
    with caplog.at_level(logging.WARNING):
        resposta = agente.responder("só atestados da Pharma Operations Platform de sala limpa ISO 7")
    assert "1 documento(s) sem classificação ficam fora" in caplog.text
    assert {c.documento_id for c in resposta.citacoes} == {"doc-pharma-ops"}


# --- agente: regra da Enterprise Vendor Hub ------------------------------------------------------


def test_contexto_leva_o_executante_quando_classificado(repo):
    resultados = HybridSearcher(repo=repo, provider=FakeEmbeddingProvider()).buscar("sala limpa ISO 7")
    contexto = montar_contexto(resultados)
    assert 'executante_grupo="coligada"' in contexto
    assert 'executante="Pharma Operations Platform Ltda."' in contexto


def _agente_coligada(repo, pergunta: str, resposta_llm: str):
    llm = FakeLLM(respostas=[_interp(), resposta_llm])
    agente = AgenteLicitacoes(
        searcher=HybridSearcher(repo=repo, provider=FakeEmbeddingProvider()), llm=llm
    )
    return agente.responder(pergunta), llm


def test_comprovacao_com_coligada_nas_fontes_explicita_o_executante(repo):
    resposta, llm = _agente_coligada(
        repo, "Temos atestado para comprovar capacidade técnica em sala limpa ISO 7?", "Sim [1][2][3]."
    )
    prompt_final = llm.chamadas[-1]["mensagens"][0]["content"]
    assert "EXECUTANTE DOS ATESTADOS" in prompt_final
    assert "Executante de cada atestado citado:" in resposta.texto
    assert "Enterprise Vendor Hub Engenharia (Enterprise Vendor Hub — só consulta interna" in resposta.texto
    assert "Pharma Operations Platform Ltda. (Pharma Operations Platform)" in resposta.texto
    assert "executante não classificado" in resposta.texto
    por_doc = {c.documento_id: c.executante_grupo for c in resposta.citacoes}
    assert por_doc == {"doc-pharma-ops": "principal", "doc-coligada": "coligada", "doc-sem-classificacao": None}
    assert resposta.contrato_citacao_ok


def test_pergunta_que_nao_e_de_comprovacao_nao_ganha_a_nota(repo):
    resposta, llm = _agente_coligada(repo, "Quais salas limpas ISO 7 já fizemos?", "Estas [1].")
    assert "EXECUTANTE DOS ATESTADOS" not in llm.chamadas[-1]["mensagens"][0]["content"]
    assert "Executante de cada atestado" not in resposta.texto


def test_comprovacao_sem_coligada_nas_fontes_nao_ganha_a_nota(repo):
    llm = FakeLLM(respostas=[_interp(executante_grupo="principal"), "Sim [1]."])
    agente = AgenteLicitacoes(
        searcher=HybridSearcher(repo=repo, provider=FakeEmbeddingProvider()), llm=llm
    )
    resposta = agente.responder("Comprovação em nome da Pharma Operations Platform de sala limpa ISO 7")
    assert "Executante de cada atestado" not in resposta.texto
