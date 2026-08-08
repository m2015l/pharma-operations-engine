# Registro de Decisões Técnicas (ADR) — Solufarma Módulo 2

> Toda decisão técnica relevante vira uma entrada aqui: o que foi decidido, por quê, e o que foi descartado.
> Formato curto de ADR (Architecture Decision Record). Numeração sequencial.

---

## ADR-001 — Supabase/PostgreSQL com pgvector como banco único

**Data**: 2026-08-04 · **Status**: Aceita (definida pelo escopo contratado)

**Contexto**: o escopo prevê Supabase/PostgreSQL como banco estruturado e uma base vetorial para embeddings.

**Decisão**: usar o **pgvector** dentro do próprio Supabase como vector store, em vez de um serviço vetorial separado (Pinecone, Weaviate, Qdrant).

**Justificativa**: um único banco para dados estruturados + vetores simplifica infraestrutura, permite busca híbrida (filtros SQL por metadados + similaridade semântica) numa única query, e não adiciona custo de outro serviço — os custos de nuvem são do cliente.

**Consequências**: atenção aos limites do plano do Supabase (dimensionar durante a semana 1); índice HNSW/IVFFlat a configurar conforme volume.

---

## ADR-002 — Estrutura de documentação viva no repositório

**Data**: 2026-08-04 · **Status**: Aceita

**Decisão**: o registro do projeto vive em `docs/` — `PLANO_PROJETO.md` (escopo e progresso), `ARQUITETURA.md` (design técnico), `DIARIO_DE_BORDO.md` (cronologia), `DECISOES.md` (este arquivo), `EQUIPE.md` (papéis). Deliverables finais para o cliente vão para serviços em nuvem; o `docs/` é o registro interno do time.

---

## ADR-003 — Ingestão de editais via upload no frontend Streamlit

**Data**: 2026-08-05 · **Status**: Aceita (definida pelo Roger)

**Contexto**: a proposta original menciona "levantamento e organização do acervo histórico" como atividade das semanas 1–4, o que sugeria uma carga inicial em massa de documentos.

**Decisão**: os editais serão enviados pela própria equipe/cliente **através do frontend Streamlit** e armazenados no **Supabase** (Storage + PostgreSQL). O upload no Streamlit é o ponto de entrada oficial do pipeline de ingestão — não haverá processo separado de carga em massa por enquanto.

**Justificativa**: simplifica o fluxo (um único caminho de entrada), e a conta Supabase já existe.

**Consequências**:
- O fluxo de upload + processamento precisa ficar pronto **mais cedo** do que o cronograma original sugeria (a interface deixa de ser "só semanas 10–12" — uma versão mínima de upload é necessária já na fase de dados);
- O pipeline de ingestão deve funcionar em modo síncrono/interativo (usuário espera o processamento) e ser idempotente (mesmo edital enviado duas vezes não duplica);
- Se um acervo histórico em massa aparecer depois, os mesmos scripts de `tools/` devem aceitar execução em lote via CLI.

---

## ADR-004 — Cronograma gerenciado por fases, não por datas

**Data**: 2026-08-05 · **Status**: Aceita (definida pelo Roger)

**Decisão**: o projeto não será gerenciado por datas absolutas — apenas pela sequência de fases/semanas relativas do plano (Infra e Dados → Agente e Vetorização → Interface e Handoff → Suporte). Os documentos não devem prender-se a datas de calendário.

---

## ADR-005 — OCR por modelo de visão (Claude Sonnet 5) via OpenRouter

**Data**: 2026-08-07 · **Status**: Aceita (definida pelo Roger) · **Resolve**: pendência P3

**Contexto**: o acervo é majoritariamente escaneado. O diagnóstico do
`SENAI_CETIQT_CAT_576640.pdf` (60 páginas) mostrou que as págs. 3–60 são
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

**Consequências**: LangChain/LangGraph continuam previstos para o **agente**
(P4), não para a ingestão. As linhas de planilha vão também para uma tabela
relacional — "quanto de piso vinílico já fornecemos?" é um `SUM`, e RAG não soma.

---

## ADR-007 — Lógica em `src/solufarma/`, `tools/` como CLIs finos

**Data**: 2026-08-07 · **Status**: Aceita (definida pelo Roger)

**Contexto**: o `BRIEFING.md` propunha um repositório novo com `src/solufarma/`,
enquanto o `CLAUDE.md` deste repositório define o framework WAT
(`workflows/` + `tools/`). As duas estruturas pareciam conflitantes.

**Decisão**: manter o framework WAT e encaixar o pipeline nele — a lógica vive
em `src/solufarma/` e cada script de `tools/*.py` é um invólucro fino que a
importa. Cada marco ganha um SOP em `workflows/`.

**Justificativa**: não há conflito real — o próprio `ARQUITETURA.md` (§6) já
previa esse arranjo. Preserva a convenção do repositório sem sacrificar a
modularidade e a testabilidade que o BRIEFING pede.

**Consequências**: `tools/` continua sendo a interface de execução (inclusive
para o agente Claude Code); testes e imports apontam para `src/`.

---

## Decisões pendentes

| # | Decisão | Opções em avaliação | Prazo sugerido |
|---|---------|--------------------|----------------|
| P1 | LLM do **agente** (o de OCR foi decidido no ADR-005) | Claude Sonnet 5 vs Opus 5 conforme complexidade | Semana 5 |
| P2 | Modelo de embeddings — **conflito a resolver**: `ARQUITETURA.md` §2.2 diz OpenAI `text-embedding-3-large`; o `CLAUDE.md` do BRIEFING diz Voyage `voyage-3` | OpenAI vs Voyage | Antes do M3 |
| P4 | Orquestração do agente | LangChain puro vs LangChain + LangGraph | Semana 5 |
| P5 | Limiares de roteamento e chunking (`MIN_DENSIDADE`, `ALVO_CHARS`, etc.) | valores atuais são hipótese de **um** documento | M2 (portão) |

~~P3 — Estratégia de OCR~~ → resolvida pelo ADR-005.

Ver análise de trade-offs em [ARQUITETURA.md](ARQUITETURA.md).
