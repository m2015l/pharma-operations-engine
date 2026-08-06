"""Testes do agente e do contrato de citação obrigatória."""

from __future__ import annotations

import json
import logging

from solufarma_rag.agent.agent import MSG_SEM_RESULTADOS, AgenteLicitacoes
from solufarma_rag.agent.citations import extrair_citacoes, montar_contexto
from solufarma_rag.agent.llm import FakeLLM
from solufarma_rag.db.models import ChunkComScore
from solufarma_rag.db.repository import InMemoryChunkRepository
from solufarma_rag.retrieval.hybrid_search import HybridSearcher


def _interpretacao(consulta="autoclave", fluxo="consulta_historico", **filtros) -> str:
    return json.dumps(
        {
            "tipo_fluxo": fluxo,
            "consulta": consulta,
            "filtros": {
                "orgao": filtros.get("orgao"),
                "tipo_documento": filtros.get("tipo_documento"),
                "data_inicio": filtros.get("data_inicio"),
                "data_fim": filtros.get("data_fim"),
            },
        }
    )


def _agente(repo, provider, respostas: list[str], **kwargs) -> tuple[AgenteLicitacoes, FakeLLM]:
    """Agente sobre a busca híbrida real (integração com o repositório em memória)."""
    llm = FakeLLM(respostas=respostas)
    agente = AgenteLicitacoes(
        searcher=HybridSearcher(repo=repo, provider=provider), llm=llm, **kwargs
    )
    return agente, llm


class SearcherStub:
    """Busca programada — isola o controle de fluxo do agente do retrieval real.

    Cada chamada consome a próxima lista de `respostas`; assim um teste pode
    encenar "primeira busca vazia, segunda com resultados" de forma determinística,
    sem depender da similaridade produzida pelo provedor fake.
    """

    def __init__(self, respostas: list[list[ChunkComScore]]) -> None:
        self.respostas = respostas
        self.consultas: list[str] = []

    def buscar(self, consulta, filtros=None, top_k=5) -> list[ChunkComScore]:
        self.consultas.append(consulta)
        if not self.respostas:
            return []
        return self.respostas.pop(0)


# -- citações --------------------------------------------------------------


def test_montar_contexto_numera_trechos_a_partir_de_1(fazer_chunk):
    resultados = [ChunkComScore(chunk=fazer_chunk(i), score=1.0) for i in range(3)]

    contexto = montar_contexto(resultados)

    assert 'id="1"' in contexto and 'id="3"' in contexto
    assert 'id="0"' not in contexto


def test_extrair_citacoes_resolve_marcadores_ate_a_pagina(fazer_chunk):
    resultados = [
        ChunkComScore(chunk=fazer_chunk(0, "conteúdo A", pagina_inicio=4, pagina_fim=5), score=1.0)
    ]

    citacoes, invalidos = extrair_citacoes("Ganhamos esse item [1].", resultados)

    assert invalidos == []
    assert citacoes[0].marcador == 1
    assert citacoes[0].documento_id == "doc-001"
    assert (citacoes[0].pagina_inicio, citacoes[0].pagina_fim) == (4, 5)


def test_extrair_citacoes_sinaliza_marcador_inexistente(fazer_chunk):
    """Citar fonte que não existe é alucinação — precisa ser reportado."""
    resultados = [ChunkComScore(chunk=fazer_chunk(0), score=1.0)]

    citacoes, invalidos = extrair_citacoes("Afirmação [1] e outra [7].", resultados)

    assert [c.marcador for c in citacoes] == [1]
    assert invalidos == [7]


def test_extrair_citacoes_nao_duplica_marcador_repetido(fazer_chunk):
    resultados = [ChunkComScore(chunk=fazer_chunk(0), score=1.0)]

    citacoes, _ = extrair_citacoes("Item [1] com garantia [1].", resultados)

    assert len(citacoes) == 1


def test_trecho_longo_e_truncado_para_exibicao(fazer_chunk):
    resultados = [ChunkComScore(chunk=fazer_chunk(0, "x" * 500), score=1.0)]

    citacoes, _ = extrair_citacoes("Fato [1].", resultados)

    assert len(citacoes[0].trecho) <= 201
    assert citacoes[0].trecho.endswith("…")


# -- fluxo do agente -------------------------------------------------------


def test_fluxo_consulta_historico_responde_com_citacoes(repo_indexado, provider):
    agente, llm = _agente(
        repo_indexado,
        provider,
        [_interpretacao(), "Já fornecemos autoclave horizontal de 100 litros [1]."],
    )

    resposta = agente.responder("Já fornecemos autoclave?")

    assert resposta.encontrou_no_acervo is True
    assert resposta.tipo_fluxo == "consulta_historico"
    assert len(resposta.citacoes) == 1
    assert len(llm.chamadas) == 2, "deve chamar interpretar + responder"


def test_contexto_enviado_ao_llm_contem_os_trechos(repo_indexado, provider):
    agente, llm = _agente(repo_indexado, provider, [_interpretacao(), "Resposta [1]."])

    agente.responder("Já fornecemos autoclave?")

    prompt_final = llm.chamadas[-1]["mensagens"][0]["content"]
    assert "<trecho id=" in prompt_final
    assert "autoclave" in prompt_final.lower()


def test_sem_resultados_admite_que_nao_encontrou(repo_indexado, provider):
    """Nunca responder por conhecimento geral quando o acervo não tem a resposta."""
    agente, _ = _agente(
        repo_indexado,
        provider,
        [_interpretacao(consulta="ressonância magnética", tipo_documento="ata")],
        max_refinamentos=0,
    )

    resposta = agente.responder("Já fornecemos ressonância magnética?")

    assert resposta.encontrou_no_acervo is False
    assert resposta.citacoes == []
    assert resposta.texto == MSG_SEM_RESULTADOS


def test_refina_a_consulta_quando_busca_volta_vazia(fazer_chunk):
    """Busca vazia → LLM reformula a consulta → segunda busca encontra."""
    searcher = SearcherStub([[], [ChunkComScore(chunk=fazer_chunk(0), score=1.0)]])
    llm = FakeLLM(
        respostas=[
            _interpretacao(consulta="tomógrafo de altíssimo campo"),
            "autoclave",  # reformulação sugerida pelo LLM
            "Encontrei registros de autoclave [1].",
        ]
    )
    agente = AgenteLicitacoes(searcher=searcher, llm=llm)

    resposta = agente.responder("Temos histórico com esterilização?")

    assert resposta.encontrou_no_acervo is True
    assert len(llm.chamadas) == 3, "interpretar + refinar + responder"
    assert searcher.consultas == ["tomógrafo de altíssimo campo", "autoclave"]


def test_nao_refina_mais_do_que_o_limite():
    """Nem toda reformulação salva a busca — o loop precisa ter teto."""
    searcher = SearcherStub([[], []])
    llm = FakeLLM(respostas=[_interpretacao(consulta="inexistente"), "outro termo inexistente"])
    agente = AgenteLicitacoes(searcher=searcher, llm=llm, max_refinamentos=1)

    resposta = agente.responder("Pergunta sem resposta no acervo")

    assert resposta.encontrou_no_acervo is False
    assert len(llm.chamadas) == 2, "não pode entrar em loop de refinamento"
    assert len(searcher.consultas) == 2


def test_nao_refina_se_llm_repete_a_mesma_consulta():
    """Reformulação idêntica não justifica outra busca — evita chamada inútil."""
    searcher = SearcherStub([[]])
    llm = FakeLLM(respostas=[_interpretacao(consulta="autoclave"), "autoclave"])
    agente = AgenteLicitacoes(searcher=searcher, llm=llm, max_refinamentos=1)

    resposta = agente.responder("pergunta")

    assert resposta.encontrou_no_acervo is False
    assert len(searcher.consultas) == 1


def test_fluxo_analise_edital_inclui_o_edital_no_prompt(repo_indexado, provider):
    agente, llm = _agente(
        repo_indexado,
        provider,
        [_interpretacao(fluxo="analise_edital"), "Risco identificado [1]."],
    )

    resposta = agente.responder(
        "Analise este edital", edital="Exige registro ANVISA e garantia de 36 meses."
    )

    assert resposta.tipo_fluxo == "analise_edital"
    assert "garantia de 36 meses" in llm.chamadas[-1]["mensagens"][0]["content"]


def test_filtros_extraidos_sao_aplicados_na_busca(repo_indexado, provider):
    agente, _ = _agente(
        repo_indexado,
        provider,
        [_interpretacao(orgao="Prefeitura de Goiânia")],
        max_refinamentos=0,
    )

    resposta = agente.responder("O que compramos para a Prefeitura de Goiânia?")

    assert resposta.encontrou_no_acervo is False, "acervo só tem SES/GO"


def test_interpretacao_com_json_invalido_nao_derruba_o_agente(repo_indexado, provider):
    """Desvio de formato do LLM cai no comportamento padrão, não em exceção."""
    agente, _ = _agente(repo_indexado, provider, ["desculpe, não entendi", "Resposta [1]."])

    resposta = agente.responder("autoclave")

    assert resposta.tipo_fluxo == "consulta_historico"
    assert resposta.encontrou_no_acervo is True


def test_interpretacao_aceita_json_entre_cercas_markdown(repo_indexado, provider):
    agente, _ = _agente(
        repo_indexado, provider, [f"```json\n{_interpretacao()}\n```", "Resposta [1]."]
    )

    resposta = agente.responder("autoclave")

    assert resposta.encontrou_no_acervo is True


def test_citacao_alucinada_e_registrada_em_log(repo_indexado, provider, caplog):
    agente, _ = _agente(repo_indexado, provider, [_interpretacao(), "Afirmação sem base [99]."])

    with caplog.at_level(logging.WARNING):
        resposta = agente.responder("autoclave?")

    assert resposta.citacoes == []
    assert resposta.citacoes_invalidas == [99]
    assert resposta.contrato_citacao_ok is False
    assert "99" in caplog.text


def test_resposta_sem_nenhuma_citacao_e_marcada_como_nao_confiavel(
    repo_indexado, provider, caplog
):
    """Afirmar sem fonte quebra o requisito central do projeto.

    Antes desta verificação, uma resposta sem nenhum [n] passava como sucesso,
    com citacoes=[] e nenhum log — indistinguível de uma resposta bem citada
    para quem consome a API.
    """
    agente, _ = _agente(
        repo_indexado, provider, [_interpretacao(), "Sim, já fornecemos esse equipamento antes."]
    )

    with caplog.at_level(logging.ERROR):
        resposta = agente.responder("já fornecemos autoclave?")

    assert resposta.citacoes == []
    assert resposta.contrato_citacao_ok is False, "resposta sem fonte não pode passar como válida"
    assert "sem nenhuma citação" in caplog.text


def test_resposta_bem_citada_tem_contrato_ok(repo_indexado, provider):
    agente, _ = _agente(repo_indexado, provider, [_interpretacao(), "Fornecemos autoclave [1]."])

    resposta = agente.responder("já fornecemos autoclave?")

    assert resposta.contrato_citacao_ok is True
    assert resposta.citacoes_invalidas == []


def test_trecho_da_citacao_nao_e_dominado_pelo_prefixo(repo_indexado, provider):
    """O trecho exibido deve mostrar o documento, não o prefixo contextual."""
    agente, _ = _agente(repo_indexado, provider, [_interpretacao(), "Consta no edital [1]."])

    resposta = agente.responder("autoclave?")

    trecho = resposta.citacoes[0].trecho
    assert not trecho.startswith("[Edital"), "prefixo contextual não deve abrir o trecho exibido"


def test_acervo_vazio_responde_que_nao_encontrou(provider):
    agente, _ = _agente(
        InMemoryChunkRepository(), provider, [_interpretacao()], max_refinamentos=0
    )

    resposta = agente.responder("qualquer pergunta")

    assert resposta.encontrou_no_acervo is False
