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

## ADR-005 — Orquestração do agente sem LangChain

**Data**: 2026-08-05 · **Status**: 🔴 **PROPOSTA — pendente de decisão da equipe. Bloqueia o merge de `feature/rag-agente`.**

> Esta ADR substitui a pendência P4 ("LangChain puro vs LangChain + LangGraph"), que
> não previa a possibilidade que o código acabou tomando: nenhuma das duas.

### Contexto

O agente da branch `feature/rag-agente` foi implementado em **Python puro**: o fluxo
(interpretar → buscar → refinar → responder → citar) é um encadeamento de 5 funções,
sem LangChain e sem LangGraph. Nenhum arquivo do projeto importa essas bibliotecas
(elas constam apenas do `requirements.txt`).

**O problema não é técnico, é contratual.** A proposta assinada com a Solufarma cita
LangChain em quatro pontos, incluindo — o mais grave — a lista de **Entregáveis**:

> "Pipeline completo de RAG implementado com LangChain"

Ou seja: um item que o cliente contratou pelo nome não existe no código.

### Argumento técnico a favor do Python puro

- O grafo tem 5 nós e 1 aresta condicional. Não há checkpoint, persistência de estado,
  human-in-the-loop nem múltiplas ferramentas — nada do que justifica LangGraph;
- Sem a dependência, todo o agente roda offline com fakes, o que permitiu escrever 56
  testes sem Supabase e sem chaves de API;
- Menos superfície de manutenção para uma equipe júnior em um projeto de 12 semanas.

### Argumento contra

- É item de entregável contratado. Um cliente (ou auditor) que abrir o repositório e
  não encontrar a palavra "langchain" tem motivo legítimo de reclamação;
- A decisão foi tomada dentro de um docstring, sem passar pela gerência do projeto —
  falha de processo, independentemente do mérito técnico.

### Opções

| # | Opção | Cumpre o contrato? | Custo |
|---|---|---|---|
| A | Manter Python puro, sem LangChain | ❌ Não | Zero, mas mantém a exposição contratual |
| B | **Python puro no agente + LangChain como camada fina** (`langchain-openai` para embeddings, `langchain-postgres` para o vector store) | ✅ Sim — há pipeline RAG com LangChain de fato | Baixo: 1–2 dias, refatoração dos adaptadores |
| C | Reescrever tudo com LangChain/LangGraph | ✅ Sim | Alto: descarta código testado, adiciona complexidade sem ganho funcional |

A opção B é a que a própria [ARQUITETURA.md](ARQUITETURA.md) §2.4 já sugeria:
*"LangChain para o encanamento: loaders, splitters, integração de embeddings, retrievers"*.

### Decisão proposta

**Opção B.** Manter o grafo do agente em Python puro (a justificativa técnica é sólida e
está documentada em `agent/agent.py`) e adotar LangChain como camada de integração do
pipeline de RAG, cumprindo a letra do entregável.

### Ação necessária antes do merge

- [ ] Roger apresenta esta ADR à **Diva** (gerente do projeto);
- [ ] Equipe decide entre A, B e C;
- [ ] Se a escolha for A, avaliar se cabe alinhar com o cliente uma mudança formal do entregável;
- [ ] Atualizar o status desta ADR para "Aceita" com a opção escolhida e a data.

---

## Decisões pendentes

| # | Decisão | Opções em avaliação | Prazo sugerido |
|---|---------|--------------------|----------------|
| P1 | LLM principal | Claude (Anthropic) vs OpenAI vs ambos | Semana 1 |
| P2 | Modelo de embeddings | OpenAI text-embedding-3 vs alternativas | Semana 4 |
| P3 | Estratégia de OCR | Tesseract local vs API de visão LLM vs Document AI | Semana 2 |
| ~~P4~~ | ~~Orquestração do agente~~ | Substituída pela **ADR-005** acima | 🔴 Bloqueia merge |
| P5 | `doc_chunks` precisa de `content_hash` e de decisão sobre `orgao`/`data` | Denormalizar em `doc_chunks` vs usar JOIN | Antes do `SupabaseChunkRepository` |

Ver análise de trade-offs em [ARQUITETURA.md](ARQUITETURA.md).
