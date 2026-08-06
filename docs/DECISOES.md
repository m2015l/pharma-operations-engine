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

## Decisões pendentes

| # | Decisão | Opções em avaliação | Prazo sugerido |
|---|---------|--------------------|----------------|
| P1 | LLM principal | Claude (Anthropic) vs OpenAI vs ambos | Semana 1 |
| P2 | Modelo de embeddings | OpenAI text-embedding-3 vs alternativas | Semana 4 |
| P3 | Estratégia de OCR | Tesseract local vs API de visão LLM vs Document AI | Semana 2 |
| P4 | Orquestração do agente | LangChain puro vs LangChain + LangGraph | Semana 5 |

Ver análise de trade-offs em [ARQUITETURA.md](ARQUITETURA.md).
