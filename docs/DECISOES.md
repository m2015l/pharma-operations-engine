# Registro de Decisões Técnicas (ADR) — Pharma Operations Platform

> Toda decisão técnica relevante vira uma entrada aqui: o que foi decidido, por quê, e o que foi descartado.
> Formato curto de ADR (Architecture Decision Record). Numeração sequencial.

---

## ADR-001 — Supabase/PostgreSQL com pgvector como banco único

**Data**: 2026-08-04 · **Status**: Aceita (definida pelo escopo da plataforma)

**Contexto**: o escopo prevê Supabase/PostgreSQL como banco estruturado e uma base vetorial para embeddings.

**Decisão**: usar o **pgvector** dentro do próprio Supabase como vector store, em vez de um serviço vetorial separado (Pinecone, Weaviate, Qdrant).

**Justificativa**: um único banco para dados estruturados + vetores simplifica infraestrutura, permite busca híbrida (filtros SQL por metadados + similaridade semântica) numa única query, e não adiciona custo de outro serviço.

**Consequências**: atenção aos limites do plano do Supabase (dimensionar durante a semana 1); índice HNSW/IVFFlat a configurar conforme volume.

---

## ADR-002 — Estrutura de documentação viva no repositório

**Data**: 2026-08-04 · **Status**: Aceita

**Decisão**: o registro do projeto vive em `docs/` — `PLANO_PROJETO.md` (escopo e progresso), `ARQUITETURA.md` (design técnico), `DIARIO_DE_BORDO.md` (cronologia), `DECISOES.md` (este arquivo), `EQUIPE.md` (papéis). Deliverables finais vão para serviços em nuvem; o `docs/` é o registro interno do time de engenharia.

---

## ADR-003 — Ingestão de documentos via upload no frontend

**Data**: 2026-08-05 · **Status**: Aceita (definida pela liderança técnica)

**Contexto**: a proposta original menciona "levantamento e organização do acervo histórico" como atividade das semanas 1–4, o que sugeria uma carga inicial em massa de documentos.

**Decisão**: os documentos podem ser enviados pela equipe **através do frontend** e armazenados no **Supabase** (Storage + PostgreSQL). O upload na plataforma é o ponto de entrada interativo do pipeline de ingestão, enquanto os scripts de `tools/` suportam execução em lote via CLI.

**Justificativa**: simplifica o fluxo operacional e aproveita a infraestrutura existente no Supabase.

**Consequências**:
- O fluxo de upload + processamento fica integrado à API;
- O pipeline de ingestão deve funcionar em modo assíncrono/interativo e ser idempotente (mesmo arquivo enviado duas vezes não duplica);
- Para lotes históricos, os mesmos scripts de `tools/` aceitam execução em lote via CLI.

---

## ADR-004 — Cronograma gerenciado por fases, não por datas

**Data**: 2026-08-05 · **Status**: Aceita (definida pela liderança técnica)

**Decisão**: o projeto não será gerenciado por datas absolutas — apenas pela sequência de fases/semanas relativas do plano (Infra e Dados → Agente e Vetorização → Interface e Handoff → Suporte). Os documentos não devem prender-se a datas de calendário.

---

## ADR-005 — OCR por modelo de visão (Claude Sonnet 5) via OpenRouter

**Data**: 2026-08-07 · **Status**: Aceita · **Resolve**: pendência P3

**Contexto**: o acervo é majoritariamente escaneado. O diagnóstico do
`INSTITUTO_BIOPHARMA_CAT_100200.pdf` (60 páginas) mostrou que as págs. 3–60 são
imagens com um carimbo digital sobreposto, e que as planilhas de quantitativos
atravessam páginas sem repetir o cabeçalho das colunas. Foram avaliados
Tesseract, Google Document AI, Qwen3-VL e Claude.

**Decisão**: **cascata em duas rotas** — extração nativa via PyMuPDF quando a
página tem camada de texto real, e OCR por modelo de visão para o resto,
usando **`anthropic/claude-sonnet-5` através do OpenRouter**. A saída é
**Markdown estruturado**, não texto corrido.

**Justificativa**:
- Sonnet 5 é mais robusto que as alternativas em página degradada, carimbo
  sobreposto e tabela com células mescladas — exatamente o perfil do acervo;
- OpenRouter dá um único ponto de billing e permite trocar de modelo mudando
  uma variável de ambiente, sem alterar código;
- Markdown preserva hierarquia (`A.1.1 vinílicos`) e colunas de tabela, que
  são irrecuperáveis se perdidas na transcrição — e resolve o chunking de graça.

**Alternativas descartadas**:
- **Qwen3-VL** — cerca de 8× mais barato e adequado para transcrição em massa,
  mas exigiria manter um segundo provedor e ficou atrás em página degradada.
  Registrado como plano B se o custo virar problema no M2;
- **Tesseract** — mantido apenas como possível votante de conferência numérica,
  não como rota principal: quebra tabelas e sofre em escaneado antigo;
- **Google Document AI** — melhor OCR "puro", mas adiciona fornecedor,
  credencial e setup GCP que o cronograma não comporta.

**Consequências**:
- Custo por documento passa a ser monitorado obrigatoriamente
  (`data/relatorios/custo_extracao.md`) e o cache por hash é o que garante
  que reprocessar não recobra;
- O preço do modelo vive em variável de ambiente junto do slug: trocar um sem
  o outro faz o relatório de custo mentir em silêncio;
- VLM **não retorna score de confiança** — os portões de qualidade precisam
  ser construídos (heurística estrutural, validador de domínio, dupla passagem
  em páginas de tabela). Isso é escopo do M2.

---

## ADR-006 — Chunking por regime de conteúdo, sem LangChain na ingestão

**Data**: 2026-08-07 · **Status**: Aceita

**Contexto**: `RecursiveCharacterTextSplitter` com `chunk_size` fixo é o padrão
do LangChain, mas o acervo tem três regimes que quebram de formas diferentes:
prosa hierárquica, tabela de planilha e metadados de capa.

**Decisão**: chunker próprio, com estratégia por regime — prosa quebra por
seção respeitando a árvore de headings; tabela vira janelas de N linhas com o
cabeçalho repetido em cada uma; metadados de capa viram **colunas de filtro
exato**, não chunks de busca vetorial. Todo chunk recebe um cabeçalho
contextual determinístico (zero chamadas de LLM).

**Justificativa**: um chunk como `QDC-4P-PIL | CJ | 1,00` é um vetor sem sinal
semântico; a tabela inteira num chunk vira a média de 50 linhas heterogêneas e
não casa com nada. A indireção do LangChain também atrapalharia a depuração
desta fase.

**Consequências**: LangChain/LangGraph continuam previstos para o **pipeline RAG**,
não para o chunker de escaneados. As linhas de planilha vão também para uma tabela
relacional — "quanto de piso vinílico já fornecemos?" é um `SUM`, e RAG não soma.

---

## ADR-007 — Lógica em `src/pharma_ops/`, `tools/` como CLIs finos

**Data**: 2026-08-07 · **Status**: Aceita

**Contexto**: o `BRIEFING.md` propunha um pacote em `src/pharma_ops/`,
enquanto o `CLAUDE.md` deste repositório define o framework WAT
(`workflows/` + `tools/`). As duas estruturas pareciam conflitantes.

**Decisão**: manter o framework WAT e encaixar o pipeline nele — a lógica vive
em `src/pharma_ops/` e cada script de `tools/*.py` é um invólucro fino que a
importa. Cada marco ganha um SOP em `workflows/`.

**Justificativa**: não há conflito real — o próprio `ARQUITETURA.md` (§6) já
previa esse arranjo. Preserva a convenção do repositório sem sacrificar a
modularidade e a testabilidade que o BRIEFING pede.

**Consequências**: `tools/` continua sendo a interface de execução (inclusive
para o agente Claude Code); testes e imports apontam para `src/`.

---

## ADR-008 — Orquestração do agente sem LangChain

**Data**: 2026-08-05 · **Decidida em**: 2026-08-06 · **Status**: ✅ **Aceita — Opção B**

> Esta ADR substitui a pendência P4 ("LangChain puro vs LangChain + LangGraph").

### Contexto

O agente da branch `feature/rag-agente` foi implementado em **Python puro**: o fluxo
(interpretar → buscar → refinar → responder → citar) é um encadeamento de 5 funções,
sem LangChain e sem LangGraph.

A especificação do sistema prevê:

> "Pipeline completo de RAG implementado com LangChain"

### Argumento técnico a favor do Python puro

- O grafo tem 5 nós e 1 aresta condicional. Não há checkpoint, persistência de estado,
  human-in-the-loop nem múltiplas ferramentas — nada do que justifica LangGraph;
- Sem a dependência pesada no grafo, todo o agente roda offline com fakes, o que permitiu escrever 56
  testes sem Supabase e sem chaves de API;
- Menos superfície de manutenção.

### Opções

| # | Opção | Cumpre a especificação? | Custo |
|---|---|---|---|
| A | Manter Python puro, sem LangChain | ❌ Não | Zero |
| B | **Python puro no agente + LangChain como camada fina** (`langchain-openai` para embeddings, `BaseRetriever` para o vector store) | ✅ Sim — há pipeline RAG com LangChain de fato | Baixo: 1–2 dias, refatoração dos adaptadores |
| C | Reescrever tudo com LangChain/LangGraph | ✅ Sim | Alto: descarta código testado, adiciona complexidade sem ganho funcional |

A opção B é a que a própria [ARQUITETURA.md](ARQUITETURA.md) §2.4 já sugeria:
*"LangChain para o encanamento: loaders, splitters, integração de embeddings, retrievers"*.

### Decisão

**Opção B**, decidida em 2026-08-06.

Vale a divisão explícita, porque é ela que sustenta as duas metades da decisão:

| Camada | Implementação | Por quê |
|---|---|---|
| **Pipeline de RAG** — embeddings, splitters, vector store | **LangChain** | É o "encanamento" genérico; a abstração paga por si (trocar de fornecedor sem tocar no pipeline) |
| **Núcleo do agente** — grafo `interpretar → buscar → refinar → responder → citar` | **Python puro** | 5 nós, 1 aresta condicional, sem estado persistido; a abstração só adicionaria custo |
| **Cliente do LLM do agente** | **SDK `anthropic` direto** | O cliente atual faz prompt caching do system prompt e trata `stop_reason == "refusal"` explicitamente; passar por wrapper perderia controle sem ganho |

### Consequências

**Já implementado** (2026-08-06):
- `OpenAIEmbeddingProvider` deu lugar a `LangChainEmbeddingProvider` + `criar_provedor_openai()`
  em [embeddings.py](../src/pharma_rag/ingestion/embeddings.py): o adaptador aceita **qualquer**
  `Embeddings` do LangChain, e a fábrica monta o padrão da arquitetura lendo o `.env`;
- `requirements.txt` passou a listar só o que o código importa (`langchain-core`,
  `langchain-openai`, `langchain-postgres`, `langchain-text-splitters`);
- O `EmbeddingProvider` continua sendo Protocol e o `FakeEmbeddingProvider` não mudou:
  os testes seguem offline, sem LangChain instalado e sem chave de API.

**Vector store — resolvido em 06/08/26, sem `langchain-postgres`**:

A ressalva se confirmou: o `langchain-postgres` impõe schema próprio (tabelas `langchain_pg_*`
com metadados em JSONB) e não faz busca híbrida com filtros SQL sobre `licitacoes`. Adotá-lo
custaria ou duplicar o armazenamento vetorial, ou abrir mão da rastreabilidade
chunk → documento → página, que é requisito central do projeto.

Caminho adotado: o pgvector é acessado pelo `SupabaseChunkRepository` (psycopg direto) e a busca
é exposta ao LangChain como `PharmaRetriever`
([langchain_retriever.py](../src/pharma_rag/retrieval/langchain_retriever.py)). O pipeline
continua LangChain de ponta a ponta — `Embeddings` → `Retriever` → resposta — sem que o schema
tenha de se dobrar à biblioteca. 8 testes cobrem essa fronteira, incluindo a preservação dos
metadados de citação.

---

## ADR-009 — O acervo é de atestados, não de editais e atas; sem tela de login por ora

**Data:** 29/09/26 · **Decisão:** Liderança de Engenharia e Produto

**Contexto:** a proposta inicial falava em indexar "editais, atas e resultados". O acervo real recebido
é todo de atestados de capacidade técnica e CATs. Editais e atas são documentos do começo ou do
meio de um processo; o que a empresa quer consultar é o **resultado final da obra**, o atestado.

**Decisão:**
1. O acervo do RAG é de **atestados de capacidade técnica e CATs**. Editais e atas ficam fora
   do acervo. O tipo padrão na ingestão e no upload é `atestado`;
2. **Sem tela de login** nesta fase (fatia F8 do `frontend/PLANO_V2.md` suspensa). Se voltar,
   é decisão nova.

**Consequências:**
- Deixa de ser lacuna a falta de editais/atas no acervo, e o golden set e a heurística de
  folha de rosto (calibrados em CATs) cobrem o tipo de documento que importa;
- O fluxo `analise_edital` do agente continua existindo (comparar um edital novo com o acervo
  de atestados), mas o edital é **entrada da pergunta**, não parte do acervo;
- Sem login, não há histórico persistido por usuário nem autor no .docx.

---

## ADR-010 — Classificação dos atestados por IA e filtros no agente

**Data:** 29/09/26 · **Decisão:** Arquitetura de IA

**Decisão:**
1. Cada documento ganha `documentos.classificacao jsonb` (migração 004, só aditiva) com
   vocabulário fechado: tipo, contratante, executante e grupo (`principal`/`coligada`/`consorcio`/`outra`),
   disciplinas, tipo de instalação, ISO, período, valor, local. Cada campo é **validado em
   código contra o texto** (página existe, trecho de evidência confere, dígitos do valor
   aparecem). O que não confere é descartado, nunca inventado;
2. Modelo barato e configurável (`CLASSIFICACAO_MODELO`, hoje `google/gemini-3.1-flash-lite`,
   ~US$ 0,005/documento), com teto de custo por execução medido pelo `usage.cost` real;
3. O agente só aplica filtro de classificação (executante, disciplina) quando o usuário
   **pede a restrição explicitamente**. Sem filtro, documento não classificado continua na
   busca; com filtro, fica fora e isso vai para o log;
4. Em pergunta de comprovação de capacidade técnica, a resposta lista o executante de cada
   atestado citado, **montado em código a partir do banco** (não depende do modelo), com a
   coligada marcada como consulta interna.

**Consequência:** enquanto houver documento sem classificação, os filtros deixam parte do
acervo de fora. Classificar todo documento novo faz parte da ingestão (etapa do upload, com
falha suave).

---

## ADR-011 — Reranker Voyage depois da fusão RRF

**Data:** 29/09/26 · **Decisão:** Arquitetura de IA

**Contexto:** com 24 atestados, em 10 de 22 perguntas do golden set um trecho de outro
documento ficava à frente do certo. O trecho certo estava no pool; faltava ordenar.

**Decisão:** os 15 primeiros resultados da busca híbrida (RRF) passam pelo Voyage
`rerank-2.5` e são cortados em `top_k`. Configurável por `RERANKER=voyage|nenhum` (padrão
`voyage`). Se a API falhar, a busca devolve a ordem do RRF e registra aviso, sem derrubar a
resposta. `rerank-2.5` ganhou do `rerank-3` no golden set (MRR 0,81 × 0,79). Custo:
cota gratuita de 200M tokens, depois ~US$ 0,0002 por pergunta.

**Resultado medido no banco real:** 5 primeiros 20→21/22, 8 primeiros 21→22/22, controles
4/4, MRR 0,66→0,81.

**Piso do reranker (`RERANK_MINIMO`):** fica desligado (0). O piso de similaridade já barra
os 4 controles negativos, e um segundo piso só acrescentaria risco de recusa falsa, que é o
modo de falha mais grave deste projeto. Reavaliar se aparecer falso positivo na auditoria.

---

## Decisões pendentes

| # | Decisão | Opções em avaliação | Prazo sugerido |
|---|---------|--------------------|----------------|
| P1 | LLM do **agente** (o de OCR foi decidido no ADR-005) | Claude Sonnet 5 vs Opus 5 conforme complexidade | Semana 5 |
| P2 | Modelo de embeddings | OpenAI vs Voyage (Voyage ativo em produção) | Resolvido |
| P4 | Orquestração do agente | Resolvido pelo ADR-008 | Semana 5 |
| P5 | Limiares de roteamento e chunking (`MIN_DENSIDADE`, `ALVO_CHARS`, etc.) | Calibração contínua sobre o acervo | M2 (portão) |

~~P3 — Estratégia de OCR~~ → resolvida pelo ADR-005.

Ver análise de trade-offs em [ARQUITETURA.md](ARQUITETURA.md).
