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

Três extensões do PRECISÃO.md vivem neste módulo: **I5** — a interpretação
pode devolver 1 a 3 consultas (uma por assunto da pergunta), buscadas
separadamente e unidas por `chunk.chave`; **I8** — com `historico`, um passo
extra reescreve a pergunta como autossuficiente antes de interpretar; **I9** —
quando a pergunta pede um quantitativo e há `repo_itens`, complementa a busca
com um SELECT estruturado em `itens_planilha`.

Nota de decisão (formalizada na ADR-008, opção B — docs/DECISOES.md): o núcleo
não importa LangGraph. O grafo tem 5 nós, 1 aresta condicional e nenhum
requisito de persistência/checkpoint, então o custo de manutenção da dependência
não se paga nesta fatia; toda a lógica fica testável offline com fakes. LangChain
fica na camada de RAG (embeddings, splitters, vector store), não aqui. Se o
agente ganhar múltiplas ferramentas, human-in-the-loop ou retomada de estado,
migrar para LangGraph — e abrir nova ADR.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from ..db.models import Chunk, ChunkComScore, ItemPlanilha, RespostaAgente
from ..db.repository import ChunkRepository, FiltrosBusca
from ..retrieval.hybrid_search import Searcher
from ..text_utils import normalizar as _normalizar
from .citations import extrair_citacoes, montar_contexto
from .llm import LLMClient
from .prompts import (
    PROMPT_ANALISE_EDITAL_SUFIXO,
    PROMPT_INTERPRETAR,
    PROMPT_REFINAR_BUSCA,
    PROMPT_RESOLVER_REFERENCIA,
    PROMPT_RESPONDER,
    SYSTEM_AGENTE,
)

logger = logging.getLogger(__name__)

FLUXOS_VALIDOS = ("consulta_historico", "analise_edital")
MSG_SEM_RESULTADOS = (
    "Não encontrei nada no acervo da Solufarma que responda a essa pergunta. "
    "Verifique se os documentos relacionados já foram enviados e indexados."
)

# I5 (PRECISÃO.md): limite duro de consultas por pergunta — mesmo que o LLM
# desrespeite a instrução do prompt e devolva mais, o código corta aqui.
MAX_CONSULTAS = 3

# I9 (PRECISÃO.md): marcadores de pergunta de quantitativo. "quant" cobre
# quanto/quantos/quantas/quantidade/quantitativo num só prefixo.
_MARCADORES_QUANTITATIVO = ("quant", "total de", "m2", "unidade")

# Offset dos chunk_index sintéticos criados a partir de itens_planilha — bem
# acima de qualquer chunk_index real, só para não colidir na chave de dedup.
_OFFSET_CHUNK_INDEX_PLANILHA = 1_000_000

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


def _extrair_consultas(dados: dict, pergunta: str) -> list[str]:
    """Lê `dados["consultas"]` (I5), com fallback para o `"consulta"` singular
    (compatibilidade com um desvio de formato do modelo) e para a pergunta crua.

    Sempre devolve pelo menos 1 item e no máximo `MAX_CONSULTAS` — o limite duro
    não confia só na instrução do prompt, porque o modelo pode desrespeitá-la.
    """
    brutas = dados.get("consultas")
    if isinstance(brutas, list):
        consultas = [c.strip() for c in brutas if isinstance(c, str) and c.strip()]
        if consultas:
            return consultas[:MAX_CONSULTAS]

    unica = dados.get("consulta")
    if isinstance(unica, str) and unica.strip():
        return [unica.strip()]

    return [pergunta]


def _pede_quantitativo(pergunta: str) -> bool:
    """Detecta marcador de quantidade (I9, PRECISÃO.md) para acionar o SELECT
    estruturado sobre `itens_planilha`, em complemento à busca vetorial/léxica.
    """
    texto = _normalizar(pergunta)
    return any(marcador in texto for marcador in _MARCADORES_QUANTITATIVO)


def _item_planilha_para_resultado(item: ItemPlanilha, indice: int) -> ChunkComScore:
    """Converte uma linha de `itens_planilha` num `ChunkComScore` sintético.

    Assim ela entra no contexto do LLM como um trecho numerado normal (mesmo
    `montar_contexto`/`extrair_citacoes` dos chunks de verdade) e continua
    rastreável por [n] — sem isso, um SELECT estrutural ficaria fora do
    contrato de citação do resto do sistema.
    """
    conteudo = " | ".join(item.celulas)
    chunk = Chunk(
        documento_id=item.documento_id or "itens_planilha",
        chunk_index=_OFFSET_CHUNK_INDEX_PLANILHA + indice,
        tipo_documento=item.tipo_documento,
        orgao=item.orgao,
        secao=item.secao,
        pagina_inicio=item.pagina or 1,
        pagina_fim=item.pagina or 1,
        conteudo=conteudo,
        token_count=max(1, len(conteudo.split())),
        content_hash=Chunk.calcular_hash(f"itens_planilha:{indice}:{conteudo}"),
    )
    return ChunkComScore(chunk=chunk, score=1.0)


def _formatar_historico(historico: list[dict]) -> str:
    """Formata o histórico acumulado (pares pergunta/resposta) para o prompt de
    reescrita de referência (I8). Formato de cada item: {"pergunta": ..., "resposta": ...}.
    """
    linhas: list[str] = []
    for turno in historico:
        pergunta = (turno.get("pergunta") or "").strip()
        resposta = (turno.get("resposta") or "").strip()
        if pergunta:
            linhas.append(f"Usuário: {pergunta}")
        if resposta:
            linhas.append(f"Assistente: {resposta}")
    return "\n".join(linhas)


@dataclass
class Interpretacao:
    """Resultado do nó de interpretação da pergunta."""

    tipo_fluxo: str
    consultas: list[str]
    filtros: FiltrosBusca = field(default_factory=FiltrosBusca)


@dataclass
class AgenteLicitacoes:
    """Agente RAG do acervo de licitações da Solufarma.

    Dependências injetadas (`searcher` e `llm`) são Protocols: nos testes recebem
    fakes offline; em produção, `HybridSearcher` sobre o Supabase e `AnthropicLLM`.
    `repo_itens` é opcional (I9): quando presente e a pergunta pede um
    quantitativo, complementa a busca com um SELECT estruturado em
    `itens_planilha`, em vez de depender só do retrieval vetorial/léxico.
    """

    searcher: Searcher
    llm: LLMClient
    top_k: int = 5
    max_refinamentos: int = 1
    repo_itens: ChunkRepository | None = None
    limite_itens_planilha: int = 10

    def responder(
        self,
        pergunta: str,
        edital: str | None = None,
        historico: list[dict] | None = None,
    ) -> RespostaAgente:
        """Executa o fluxo completo e devolve a resposta com citações resolvidas.

        `historico` (I8, PRECISÃO.md) é a lista de turnos anteriores da conversa
        (`[{"pergunta": ..., "resposta": ...}, ...]`). Quando presente, a
        pergunta é reescrita como autossuficiente ANTES de interpretar — sem
        isso, "e a área disso" ou "aquilo lá" chegam à interpretação sem
        antecedente e o retrieval não tem como achar o trecho certo.
        """
        if historico:
            pergunta = self._resolver_referencia(pergunta, historico)

        interpretacao = self._interpretar(pergunta, edital)
        resultados = self._buscar(pergunta, interpretacao)

        tentativas = 0
        while not resultados and tentativas < self.max_refinamentos:
            tentativas += 1
            nova_consulta = self._refinar(pergunta, " | ".join(interpretacao.consultas))
            if not nova_consulta or nova_consulta in interpretacao.consultas:
                break
            interpretacao.consultas = [nova_consulta]
            # Segunda tentativa sem filtros: se foi um filtro que zerou a busca
            # (tipo/órgão que não casa com o acervo), refinar só a consulta não
            # tem como salvar — a segunda chamada nasce condenada.
            resultados = self.searcher.buscar(nova_consulta, FiltrosBusca(), self.top_k)

        if not resultados:
            return RespostaAgente(
                texto=MSG_SEM_RESULTADOS,
                citacoes=[],
                tipo_fluxo=interpretacao.tipo_fluxo,
                encontrou_no_acervo=False,
                trechos_recuperados=0,
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
            trechos_recuperados=len(resultados),
        )

    # -- nós do grafo ------------------------------------------------------

    def _resolver_referencia(self, pergunta: str, historico: list[dict]) -> str:
        """Reescreve a pergunta como autossuficiente usando o histórico (I8).

        Sempre loga pergunta original e reescrita: o modo de falha novo (a
        reescrita injeta contexto errado numa pergunta que mudou de assunto,
        contaminando o retrieval) não deixa nenhum rastro se não for logado.
        """
        bruto = self.llm.completar(
            SYSTEM_AGENTE,
            [
                {
                    "role": "user",
                    "content": PROMPT_RESOLVER_REFERENCIA.format(
                        historico=_formatar_historico(historico), pergunta=pergunta
                    ),
                }
            ],
        )
        reescrita = bruto.strip().strip('"') or pergunta
        logger.info("Reescrita de referência (I8): original=%r reescrita=%r", pergunta, reescrita)
        return reescrita

    def _buscar(self, pergunta: str, interpretacao: Interpretacao) -> list[ChunkComScore]:
        """Busca híbrida (I5: uma chamada por consulta) + itens_planilha (I9).

        Uma consulta por assunto evita que um vetor médio de dois assuntos não
        case com nenhum. Quando a pergunta pede um quantitativo e há
        `repo_itens`, complementa com um SELECT estruturado — resolve exato o
        que a busca vetorial/léxica só aproxima. Tudo deduplicado por
        `chunk.chave`, preservando a ordem de RRF dentro de cada busca.
        """
        vistos: set[str] = set()
        unidos: list[ChunkComScore] = []

        for consulta in interpretacao.consultas:
            for resultado in self.searcher.buscar(consulta, interpretacao.filtros, self.top_k):
                chave = resultado.chunk.chave
                if chave in vistos:
                    continue
                vistos.add(chave)
                unidos.append(resultado)

        if self.repo_itens is not None and _pede_quantitativo(pergunta):
            indice = 0
            for consulta in interpretacao.consultas:
                itens = self.repo_itens.buscar_itens_planilha(
                    consulta, limite=self.limite_itens_planilha
                )
                for item in itens:
                    indice += 1
                    resultado = _item_planilha_para_resultado(item, indice)
                    chave = resultado.chunk.chave
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    unidos.append(resultado)

        return unidos

    def _interpretar(self, pergunta: str, edital: str | None) -> Interpretacao:
        """Traduz a pergunta em consultas de busca + filtros estruturados."""
        bruto = self.llm.completar(
            SYSTEM_AGENTE, [{"role": "user", "content": PROMPT_INTERPRETAR.format(pergunta=pergunta)}]
        )
        dados = _extrair_json(bruto)

        tipo_fluxo = dados.get("tipo_fluxo")
        if tipo_fluxo not in FLUXOS_VALIDOS:
            tipo_fluxo = "analise_edital" if edital else "consulta_historico"

        consultas = _extrair_consultas(dados, pergunta)

        filtros_brutos = dados.get("filtros")
        filtros = FiltrosBusca()
        if isinstance(filtros_brutos, dict):
            limpos = {k: v for k, v in filtros_brutos.items() if v not in (None, "")}
            try:
                filtros = FiltrosBusca.model_validate(limpos)
            except ValueError:
                # Filtro malformado não pode derrubar a consulta — busca sem filtro.
                logger.warning("Filtros inválidos na interpretação: %r", filtros_brutos)

        return Interpretacao(tipo_fluxo=tipo_fluxo, consultas=consultas, filtros=filtros)

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
