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

## Decisões pendentes

| # | Decisão | Opções em avaliação | Prazo sugerido |
|---|---------|--------------------|----------------|
| P1 | LLM principal | Claude (Anthropic) vs OpenAI vs ambos | Semana 1 |
| P2 | Modelo de embeddings | OpenAI text-embedding-3 vs alternativas | Semana 4 |
| P3 | Estratégia de OCR | Tesseract local vs API de visão LLM vs Document AI | Semana 2 |
| P4 | Orquestração do agente | LangChain puro vs LangChain + LangGraph | Semana 5 |

Ver análise de trade-offs em [ARQUITETURA.md](ARQUITETURA.md).
