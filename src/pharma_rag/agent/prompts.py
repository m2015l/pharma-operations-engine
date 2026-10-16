"""Prompts do agente de licitações — contrato de citação obrigatória.

Regra central (docs/ARQUITETURA.md §5.4 e skill rag-licitacoes): toda afirmação
factual referencia [n], onde [n] mapeia para um trecho recuperado do acervo.
Resposta sem fonte rastreável é bug, não feature incompleta.
"""

from pharma_ops.classificacao import DISCIPLINAS

SYSTEM_AGENTE = """\
Você é o assistente de licitações da Pharma Operations Platform. Você responde perguntas sobre o
acervo histórico de licitações (editais, atas, resultados) e analisa novos
editais comparando-os com esse histórico.

REGRAS DE CITAÇÃO (OBRIGATÓRIAS):
1. Toda afirmação factual DEVE referenciar um marcador [n], onde n é o id de um
   dos trechos fornecidos no contexto (ex.: "ganhamos o item de autoclave [2]").
2. Cite APENAS ids de trechos que existem no contexto fornecido.
3. Se a informação não estiver nos trechos fornecidos, diga que ela NÃO ESTÁ
   NOS TRECHOS RECUPERADOS — nunca que "não está no acervo" e nunca que "o
   documento não menciona". Você enxerga 5 a 8 trechos de documentos que têm
   dezenas de páginas; ausência no seu contexto não é prova de ausência no
   acervo. Formule assim: "não encontrei isso nos trechos recuperados; se for
   decisivo para a proposta, refaça a pergunta usando o termo exato do
   documento (ex.: 'postos de utilização', 'atividade técnica realizada')".
   NÃO complete com conhecimento geral.
4. Nunca invente números de edital, valores, datas ou órgãos.

ESTILO:
- Responda em português brasileiro, direto e objetivo;
- A PRIMEIRA linha responde a pergunta. Se pediram um número, ele vem na
  primeira linha, com a citação [n]. Detalhamento, ressalvas e recomendações
  vêm depois, nunca antes;
- Sem títulos em negrito quando a resposta cabe em um parágrafo;
- Ao comparar um novo edital com o histórico, aponte riscos e precedentes com
  a respectiva citação [n].
"""

# Interpretação da pergunta: extrai o fluxo e as consultas de busca. Os filtros
# estruturados saem sempre null (ver docs/DECISOES.md — o acervo de hoje só
# tem o tipo "atestado", fora do enum, e qualquer filtro preenchido zera a
# busca). Usa saída JSON estrita para parsing determinístico.
#
# EXCEÇÃO: "executante_grupo" e "disciplinas" filtram pela classificação por IA
# de cada documento (migração 004) e SÃO preenchidos — mas só quando o usuário
# pede a restrição explicitamente. O código (agent.py) descarta valor fora do
# vocabulário de `pharma_ops.classificacao`.
#
# "consultas" (plural, I5 do PRECISÃO.md): pergunta com mais de um assunto
# ("sala limpa ISO 7" + "manutenção predial") vira uma consulta por assunto —
# um vetor médio dos dois não casa direito com nenhum. Limite de 3 é aplicado
# no código (agent.py), não confiar só na instrução do prompt.
PROMPT_INTERPRETAR = """\
Analise a pergunta do usuário e responda APENAS com um JSON válido, sem
comentários, no formato:

{{
  "tipo_fluxo": "consulta_historico" | "analise_edital",
  "consultas": ["<termos de busca no acervo, curtos e específicos>"],
  "filtros": {{
    "orgao": null,
    "tipo_documento": null,
    "data_inicio": null,
    "data_fim": null,
    "executante_grupo": null,
    "disciplinas": []
  }}
}}

Use "analise_edital" somente se o usuário enviou um edital para análise.

REGRAS PARA "consultas":
- Escreva os termos que apareceriam NO DOCUMENTO do acervo, não os termos da
  pergunta. "quero comprovar 3000 m² num edital" vira "área construída total
  da obra por pavimento", não "edital 3000 m²".
- Nunca inclua palavras sobre o processo licitatório do usuário (edital,
  envelope, habilitação, proposta, certame) na consulta: o acervo é feito de
  atestados e documentos de obra, não do edital que o usuário tem na mão.
- Se a pergunta trata de mais de um assunto (ex.: "sala limpa ISO 7" E
  "manutenção predial 5 anos"), devolva UMA consulta por assunto. Nunca junte
  assuntos diferentes numa consulta só. No máximo 3 consultas.
- Se a pergunta trata de um assunto só, devolva uma lista com 1 item.
- Não invente filtros. "orgao", "tipo_documento", "data_inicio" e "data_fim"
  são sempre null.

REGRAS PARA "executante_grupo" e "disciplinas" (filtros pela classificação do
documento — só preencha quando o usuário PEDE EXPLICITAMENTE a restrição):
- "executante_grupo": "principal" quando o usuário restringe aos atestados da
  Pharma Operations Platform ("só atestados da Pharma Operations Platform", "comprovação em nome da Pharma Operations Platform",
  "executados pela Pharma Operations Platform"); "coligada" quando restringe aos da Enterprise Vendor Hub. Mencionar a
  Pharma Operations Platform de passagem ("a Pharma Operations Platform já fez sala limpa?") NÃO é restrição:
  deixe null. Valores possíveis: principal, coligada, consorcio, outra.
- "disciplinas": só quando o usuário restringe por disciplina ("atestados de
  HVAC", "só os de elétrica"). Use apenas estas chaves: {disciplinas}.
  Caso contrário, lista vazia.

Pergunta do usuário:
{pergunta}
""".replace("{disciplinas}", ", ".join(DISCIPLINAS))

# Regra de negócio vigente (pendência 26 do plano): atestado cuja executante é a
# Enterprise Vendor Hub serve só como consulta interna — não comprova capacidade técnica da
# Pharma Operations Platform. Anexado ao PROMPT_RESPONDER quando a pergunta é de comprovação e há
# trecho da Enterprise Vendor Hub no contexto; o agente ainda acrescenta, em código, a lista do
# executante de cada documento citado (não depende do modelo obedecer).
PROMPT_EXECUTANTE_SUFIXO = """

ATENÇÃO — EXECUTANTE DOS ATESTADOS: a pergunta é sobre comprovação de
capacidade técnica e há, entre os trechos, atestados cuja executante é a Enterprise Vendor Hub
(atributo executante_grupo="coligada"). Para CADA atestado que você citar, diga
explicitamente quem é a executante (Pharma Operations Platform, Enterprise Vendor Hub, consórcio ou outra). Deixe
claro que atestado da Enterprise Vendor Hub serve apenas como referência interna e NÃO comprova
capacidade técnica da Pharma Operations Platform. Não some quantitativos de atestados da Enterprise Vendor Hub aos
da Pharma Operations Platform.
"""

# Reescrita de referência (I8 do PRECISÃO.md): roda ANTES de PROMPT_INTERPRETAR
# quando há histórico de conversa. "E a área disso", "o sistema de gases que vc
# mencionou antes", "aquilo lá" chegam à interpretação sem antecedente — o
# retrieval nunca tem chance de achar o trecho certo a partir de um pronome.
PROMPT_RESOLVER_REFERENCIA = """\
Reescreva a última pergunta do usuário como uma pergunta autossuficiente,
resolvendo pronomes e elipses com o que já foi dito na conversa. Não responda
à pergunta, não acrescente informação nova, não invente contexto. Se a
pergunta já for autossuficiente, devolva-a sem alterações. Se não houver
contexto suficiente para resolver a referência, devolva-a sem alterações.
Responda APENAS com a pergunta reescrita.

Conversa até aqui:
{historico}

Última pergunta:
{pergunta}
"""

PROMPT_REFINAR_BUSCA = """\
A busca no acervo com a consulta "{consulta}" não retornou resultados.
Reformule a consulta com sinônimos ou termos mais genéricos do domínio de
licitações/equipamentos hospitalares. Responda APENAS com a nova consulta,
sem explicações.

Pergunta original do usuário:
{pergunta}
"""

PROMPT_RESPONDER = """\
Trechos recuperados do acervo:

{contexto}

Pergunta do usuário:
{pergunta}

Responda seguindo as regras de citação: toda afirmação factual com [n].
Se os trechos não contêm a resposta, diga que não encontrou NOS TRECHOS
RECUPERADOS — não afirme que a informação não existe no acervo, e não afirme
que a lista que você deu é completa.
"""

PROMPT_ANALISE_EDITAL_SUFIXO = """\

O usuário enviou um novo edital para análise. Conteúdo (por página):

{edital}

Compare as exigências e itens deste edital com o histórico do acervo (trechos
acima), apontando: itens com histórico favorável, riscos identificados e
precedentes relevantes — cada afirmação com citação [n].
"""
