"""Testes do agente e do contrato de citação obrigatória."""

from __future__ import annotations

import json
import logging

from solufarma_rag.agent.agent import MSG_SEM_RESULTADOS, AgenteLicitacoes
from solufarma_rag.agent.citations import extrair_citacoes, montar_contexto
from solufarma_rag.agent.llm import FakeLLM
from solufarma_rag.db.models import ChunkComScore
from solufarma_rag.db.repository import InMemoryChunkRepository, ItemPlanilha
from solufarma_rag.retrieval.hybrid_search import HybridSearcher


def _interpretacao(
    consulta="autoclave", consultas=None, fluxo="consulta_historico", **filtros
) -> str:
    """Monta o JSON de `PROMPT_INTERPRETAR`.

    Desde I5 (PRECISÃO.md) o campo é "consultas" (lista). `consulta=` (singular)
    continua aceito por conveniência dos testes que só têm um assunto — vira
    uma lista de 1 item; passe `consultas=[...]` explicitamente para exercitar
    o caso de múltiplos assuntos.
    """
    return json.dumps(
        {
            "tipo_fluxo": fluxo,
            "consultas": consultas if consultas is not None else [consulta],
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


def test_trechos_recuperados_registra_o_total_do_contexto(repo_indexado, provider):
    """I10: a linha 'N citadas de M recuperados' do CLI depende deste campo."""
    agente, _ = _agente(repo_indexado, provider, [_interpretacao(), "Fornecemos autoclave [1]."])

    resposta = agente.responder("já fornecemos autoclave?")

    assert resposta.trechos_recuperados >= len(resposta.citacoes)
    assert resposta.trechos_recuperados >= 1


def test_sem_resultados_trechos_recuperados_e_zero(repo_indexado, provider):
    agente, _ = _agente(
        repo_indexado,
        provider,
        [_interpretacao(consulta="ressonância magnética", tipo_documento="ata")],
        max_refinamentos=0,
    )

    resposta = agente.responder("Já fornecemos ressonância magnética?")

    assert resposta.trechos_recuperados == 0


# -- I5: pergunta com múltiplos assuntos vira várias consultas -------------


def test_pergunta_com_dois_assuntos_gera_duas_consultas_e_une_sem_duplicar(fazer_chunk):
    """Turno 4.3 do PRECISÃO.md: um vetor médio de dois assuntos não casa com
    nenhum. Cada consulta busca separado; a união deduplica por chunk.chave."""
    chunk_sala_limpa = fazer_chunk(0, "sala limpa ISO 7")
    chunk_manutencao = fazer_chunk(1, "manutenção predial 5 anos")
    chunk_repetido = fazer_chunk(0, "sala limpa ISO 7")  # mesma chave de chunk_sala_limpa

    searcher = SearcherStub(
        [
            [ChunkComScore(chunk=chunk_sala_limpa, score=1.0)],
            [
                ChunkComScore(chunk=chunk_repetido, score=0.9),
                ChunkComScore(chunk=chunk_manutencao, score=0.8),
            ],
        ]
    )
    llm = FakeLLM(
        respostas=[
            _interpretacao(consultas=["sala limpa ISO 7", "manutenção predial 5 anos"]),
            "Sala limpa ISO 7 [1] e manutenção predial [2].",
        ]
    )
    agente = AgenteLicitacoes(searcher=searcher, llm=llm)

    resposta = agente.responder("fala de sala limpa ISO 7 e manutenção predial 5 anos?")

    assert searcher.consultas == ["sala limpa ISO 7", "manutenção predial 5 anos"]
    assert resposta.encontrou_no_acervo is True
    assert resposta.trechos_recuperados == 2, "chunk repetido não pode contar duas vezes"
    assert len(resposta.citacoes) == 2


def test_interpretacao_limita_a_tres_consultas():
    """Limite duro no código (agent.py), não só na instrução do prompt."""
    searcher = SearcherStub([[], [], []])
    llm = FakeLLM(respostas=[_interpretacao(consultas=["a", "b", "c", "d"])])
    agente = AgenteLicitacoes(searcher=searcher, llm=llm, max_refinamentos=0)

    agente.responder("pergunta com muitos assuntos")

    assert searcher.consultas == ["a", "b", "c"]


# -- I8: reescrita de referência com histórico ------------------------------


def test_com_historico_reescreve_a_pergunta_antes_de_interpretar(fazer_chunk):
    """Turno 1.2 do PRECISÃO.md: "e a área disso" sem histórico não tem
    antecedente para o interpretador resolver."""
    searcher = SearcherStub([[ChunkComScore(chunk=fazer_chunk(0), score=1.0)]])
    llm = FakeLLM(
        respostas=[
            "qual a área construída da obra do SENAI CETIQT, somando os pavimentos?",
            _interpretacao(consulta="área construída total da obra por pavimento"),
            "A área somada é X [1].",
        ]
    )
    agente = AgenteLicitacoes(searcher=searcher, llm=llm)
    historico = [
        {
            "pergunta": "temos atestado de implantação de laboratório?",
            "resposta": "Sim, o SENAI CETIQT [1].",
        }
    ]

    agente.responder("e a área disso, quantos m2 tinha a obra?", historico=historico)

    assert len(llm.chamadas) == 3, "reescrita + interpretar + responder"
    prompt_reescrita = llm.chamadas[0]["mensagens"][0]["content"]
    assert "e a área disso" in prompt_reescrita
    assert "temos atestado de implantação de laboratório" in prompt_reescrita
    # A pergunta reescrita (não a original) é o que chega à interpretação.
    prompt_interpretar = llm.chamadas[1]["mensagens"][0]["content"]
    assert "SENAI CETIQT" in prompt_interpretar


def test_sem_historico_nao_chama_reescrita(repo_indexado, provider):
    agente, llm = _agente(repo_indexado, provider, [_interpretacao(), "Resposta [1]."])

    agente.responder("já fornecemos autoclave?")

    assert len(llm.chamadas) == 2, "sem histórico, não deveria haver chamada de reescrita"


def test_historico_vazio_nao_chama_reescrita(repo_indexado, provider):
    agente, llm = _agente(repo_indexado, provider, [_interpretacao(), "Resposta [1]."])

    agente.responder("já fornecemos autoclave?", historico=[])

    assert len(llm.chamadas) == 2, "lista vazia é 'sem histórico', não deve acionar reescrita"


def test_reescrita_que_devolve_pergunta_intacta_no_llm_e_usada_como_esta(repo_indexado, provider):
    """Se o LLM não resolver a referência, devolve a pergunta sem alterações —
    e é essa (não a original com aspas/espaços do LLM) que segue no fluxo."""
    llm = FakeLLM(
        respostas=[
            '"já fornecemos autoclave?"',  # LLM devolve entre aspas
            _interpretacao(),
            "Resposta [1].",
        ]
    )
    agente = AgenteLicitacoes(searcher=HybridSearcher(repo=repo_indexado, provider=provider), llm=llm)

    resposta = agente.responder("já fornecemos autoclave?", historico=[{"pergunta": "oi"}])

    assert resposta.encontrou_no_acervo is True


# -- I9: pergunta de quantitativo consulta itens_planilha -------------------


def test_pergunta_quantitativa_complementa_com_itens_planilha(fazer_chunk):
    """Turno 2.4 do PRECISÃO.md: a busca vetorial/léxica sozinha errou o
    número de pontos de gás; itens_planilha tem a linha exata."""
    repo_itens = InMemoryChunkRepository()
    repo_itens.adicionar_item_planilha(
        ItemPlanilha(
            documento_id="doc-001",
            tipo_documento="atestado",
            orgao="SENAI CETIQT",
            pagina=45,
            secao="GASES",
            # `buscar_itens_planilha` casa por ilike sobre as CÉLULAS (não a
            # seção) — o termo de busca precisa aparecer literalmente na linha,
            # igual ao comportamento real do SQL (ver repository.py).
            celulas=["VÁLVULA REGULADORA DE PRESSÃO PARA GASES, 2º ESTÁGIO", "CJ", "144,00"],
        )
    )
    searcher = SearcherStub([[]])  # busca semântica não acha nada
    llm = FakeLLM(
        respostas=[
            _interpretacao(consulta="gases"),
            "Foram instalados 144 reguladores em parede [1].",
        ]
    )
    agente = AgenteLicitacoes(searcher=searcher, llm=llm, repo_itens=repo_itens, max_refinamentos=0)

    resposta = agente.responder("quantos pontos de consumo de gases foram instalados?")

    assert resposta.encontrou_no_acervo is True
    assert resposta.trechos_recuperados == 1
    prompt_resposta = llm.chamadas[-1]["mensagens"][0]["content"]
    assert "144,00" in prompt_resposta
    assert len(resposta.citacoes) == 1


def test_pergunta_sem_marcador_de_quantidade_nao_consulta_itens_planilha(fazer_chunk):
    """Fora do gatilho de quantitativo, repo_itens não deveria ser chamado —
    evita ilike custoso/ruído em toda pergunta que não precisa dele."""

    class RepoEspiao:
        def __init__(self) -> None:
            self.chamado = False

        def buscar_itens_planilha(self, termo, documento_id=None, limite=20):
            self.chamado = True
            return []

    repo_espiao = RepoEspiao()
    searcher = SearcherStub([[ChunkComScore(chunk=fazer_chunk(0), score=1.0)]])
    llm = FakeLLM(respostas=[_interpretacao(), "Resposta [1]."])
    agente = AgenteLicitacoes(searcher=searcher, llm=llm, repo_itens=repo_espiao)

    agente.responder("já fornecemos autoclave?")

    assert repo_espiao.chamado is False


def test_sem_repo_itens_pergunta_quantitativa_nao_quebra(fazer_chunk):
    """`repo_itens=None` (padrão) é o comportamento de hoje — não pode quebrar."""
    searcher = SearcherStub([[ChunkComScore(chunk=fazer_chunk(0), score=1.0)]])
    llm = FakeLLM(respostas=[_interpretacao(), "Resposta [1]."])
    agente = AgenteLicitacoes(searcher=searcher, llm=llm)

    resposta = agente.responder("quantos pontos de consumo de gases foram instalados?")

    assert resposta.encontrou_no_acervo is True
