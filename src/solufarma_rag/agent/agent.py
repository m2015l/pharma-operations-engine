"""Orquestração do agente de licitações (docs/ARQUITETURA.md §5).

Fluxo do grafo (implementado aqui em Python puro, sem dependência de LangGraph
no núcleo — ver nota de decisão no final deste docstring):

    interpretar → buscar → (refinar → buscar)? → responder → citar

1. **interpretar**: o LLM traduz a pergunta em `consulta` + `filtros` estruturados
   (JSON estrito), identificando o fluxo — consulta ao histórico ou análise de
   um novo edital;
2. **buscar**: busca híbrida no acervo com os filtros extraídos;
3. **refinar**: se a busca voltar vazia, o LLM reformula a consulta uma única vez
   (o loop é limitado para não gastar tokens indefinidamente);
4. **responder**: o LLM responde a partir dos trechos numerados;
5. **citar**: os marcadores [n] são resolvidos em `Citacao` rastreáveis. Marcadores
   inexistentes são alucinação de fonte — registrados em log e removidos.

Se nada for encontrado no acervo, o agente responde explicitamente que não
encontrou (`encontrou_no_acervo=False`) em vez de responder por conhecimento
geral — regra central do projeto.

Nota de decisão: o núcleo não importa LangGraph. O grafo tem 5 nós, 1 aresta
condicional e nenhum requisito de persistência/checkpoint, então o custo de
manutenção da dependência não se paga nesta fatia; toda a lógica fica testável
offline com fakes. Se o agente ganhar múltiplas ferramentas, human-in-the-loop
ou retomada de estado, migrar para LangGraph (candidato a ADR).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from ..db.models import RespostaAgente
from ..db.repository import FiltrosBusca
from ..retrieval.hybrid_search import Searcher
from .citations import extrair_citacoes, montar_contexto
from .llm import LLMClient
from .prompts import (
    PROMPT_ANALISE_EDITAL_SUFIXO,
    PROMPT_INTERPRETAR,
    PROMPT_REFINAR_BUSCA,
    PROMPT_RESPONDER,
    SYSTEM_AGENTE,
)

logger = logging.getLogger(__name__)

FLUXOS_VALIDOS = ("consulta_historico", "analise_edital")
MSG_SEM_RESULTADOS = (
    "Não encontrei nada no acervo da Solufarma que responda a essa pergunta. "
    "Verifique se os documentos relacionados já foram enviados e indexados."
)

_RE_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON de uma resposta do LLM, tolerando cercas ```json.

    Retorna {} se não houver JSON parseável — o chamador cai no comportamento
    padrão em vez de quebrar a conversa por um desvio de formato do modelo.
    """
    m = _RE_JSON.search(texto)
    if not m:
        return {}
    try:
        dados = json.loads(m.group(0))
    except json.JSONDecodeError:
        logger.warning("Resposta de interpretação não é JSON válido: %r", texto[:200])
        return {}
    return dados if isinstance(dados, dict) else {}


@dataclass
class Interpretacao:
    """Resultado do nó de interpretação da pergunta."""

    tipo_fluxo: str
    consulta: str
    filtros: FiltrosBusca = field(default_factory=FiltrosBusca)


@dataclass
class AgenteLicitacoes:
    """Agente RAG do acervo de licitações da Solufarma.

    Dependências injetadas (`searcher` e `llm`) são Protocols: nos testes recebem
    fakes offline; em produção, `HybridSearcher` sobre o Supabase e `AnthropicLLM`.
    """

    searcher: Searcher
    llm: LLMClient
    top_k: int = 5
    max_refinamentos: int = 1

    def responder(self, pergunta: str, edital: str | None = None) -> RespostaAgente:
        """Executa o fluxo completo e devolve a resposta com citações resolvidas."""
        interpretacao = self._interpretar(pergunta, edital)
        resultados = self.searcher.buscar(
            interpretacao.consulta, interpretacao.filtros, self.top_k
        )

        tentativas = 0
        while not resultados and tentativas < self.max_refinamentos:
            tentativas += 1
            nova_consulta = self._refinar(pergunta, interpretacao.consulta)
            if not nova_consulta or nova_consulta == interpretacao.consulta:
                break
            interpretacao.consulta = nova_consulta
            resultados = self.searcher.buscar(nova_consulta, interpretacao.filtros, self.top_k)

        if not resultados:
            return RespostaAgente(
                texto=MSG_SEM_RESULTADOS,
                citacoes=[],
                tipo_fluxo=interpretacao.tipo_fluxo,
                encontrou_no_acervo=False,
            )

        texto = self._responder_com_contexto(pergunta, resultados, interpretacao, edital)
        citacoes, invalidos = extrair_citacoes(texto, resultados)

        if invalidos:
            # Fonte inexistente é alucinação: registrar sempre, nunca engolir em silêncio.
            logger.error(
                "Agente citou marcadores inexistentes %s (contexto tinha %d trechos)",
                invalidos,
                len(resultados),
            )

        # Resposta sem NENHUMA citação, tendo havido contexto, é quebra do contrato
        # de rastreabilidade — o requisito central do projeto. Sem esta verificação,
        # uma afirmação sem fonte passaria como resposta válida.
        sem_citacao = not citacoes
        if sem_citacao:
            logger.error(
                "Agente respondeu sem nenhuma citação apesar de %d trechos recuperados — "
                "resposta marcada como não confiável",
                len(resultados),
            )

        return RespostaAgente(
            texto=texto,
            citacoes=citacoes,
            tipo_fluxo=interpretacao.tipo_fluxo,
            encontrou_no_acervo=True,
            contrato_citacao_ok=not sem_citacao and not invalidos,
            citacoes_invalidas=invalidos,
        )

    # -- nós do grafo ------------------------------------------------------

    def _interpretar(self, pergunta: str, edital: str | None) -> Interpretacao:
        """Traduz a pergunta em consulta de busca + filtros estruturados."""
        bruto = self.llm.completar(
            SYSTEM_AGENTE, [{"role": "user", "content": PROMPT_INTERPRETAR.format(pergunta=pergunta)}]
        )
        dados = _extrair_json(bruto)

        tipo_fluxo = dados.get("tipo_fluxo")
        if tipo_fluxo not in FLUXOS_VALIDOS:
            tipo_fluxo = "analise_edital" if edital else "consulta_historico"

        consulta = (dados.get("consulta") or "").strip() or pergunta

        filtros_brutos = dados.get("filtros")
        filtros = FiltrosBusca()
        if isinstance(filtros_brutos, dict):
            limpos = {k: v for k, v in filtros_brutos.items() if v not in (None, "")}
            try:
                filtros = FiltrosBusca.model_validate(limpos)
            except ValueError:
                # Filtro malformado não pode derrubar a consulta — busca sem filtro.
                logger.warning("Filtros inválidos na interpretação: %r", filtros_brutos)

        return Interpretacao(tipo_fluxo=tipo_fluxo, consulta=consulta, filtros=filtros)

    def _refinar(self, pergunta: str, consulta: str) -> str:
        """Pede ao LLM uma reformulação da consulta que voltou vazia."""
        resposta = self.llm.completar(
            SYSTEM_AGENTE,
            [
                {
                    "role": "user",
                    "content": PROMPT_REFINAR_BUSCA.format(consulta=consulta, pergunta=pergunta),
                }
            ],
        )
        return resposta.strip().strip('"')

    def _responder_com_contexto(
        self,
        pergunta: str,
        resultados: list,
        interpretacao: Interpretacao,
        edital: str | None,
    ) -> str:
        """Gera a resposta final a partir dos trechos numerados do acervo."""
        conteudo = PROMPT_RESPONDER.format(
            contexto=montar_contexto(resultados), pergunta=pergunta
        )
        if interpretacao.tipo_fluxo == "analise_edital" and edital:
            conteudo += PROMPT_ANALISE_EDITAL_SUFIXO.format(edital=edital)
        return self.llm.completar(SYSTEM_AGENTE, [{"role": "user", "content": conteudo}])
