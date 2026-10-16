# Frente RAG & Agente — guia do código

> **Comece por aqui** se você vai mexer no pipeline RAG ou no agente.
> Branch: `feature/rag-agente` · Estado: implementado e testado offline.
> A decisão do LangChain foi tomada — **opção B**, ver [ADR-008 em DECISOES.md](DECISOES.md):
> LangChain no pipeline de RAG (embeddings, splitters, vector store), Python puro no
> grafo do agente.

---

## 1. Em uma frase

O pacote `src/pharma_rag/` transforma documentos de licitação em chunks indexados e responde perguntas sobre eles citando as fontes. **Nada depende de Supabase ou de chaves de API para rodar**: toda dependência externa é um Protocol com implementação fake.

## 2. Como rodar (do zero, 2 minutos)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install pydantic pytest ruff

.venv/Scripts/python.exe -m pytest              # testes offline, sem rede
.venv/Scripts/python.exe -m ruff check src/ tests/ tools/
```

Os CLIs (framework WAT):

```bash
# Chunking de um documento já extraído (JSON de entrada descrito no --help)
.venv/Scripts/python.exe tools/chunk_document.py documento.json > chunks.json

# Pipeline de embeddings — --dry-run funciona sem banco
.venv/Scripts/python.exe tools/generate_embeddings.py --dry-run
```

> `requirements.txt` tem a lista completa do projeto;
> para rodar só os testes bastam `pydantic`, `pytest` e `ruff`.

## 3. Mapa do código

```
src/pharma_rag/
├── config.py              Lê .env (Supabase, chaves, modelos). Sem pydantic-settings.
├── text_utils.py          normalizar() e tokenizar() — espelham unaccent+FTS do Postgres.
├── db/
│   ├── models.py          Contratos Pydantic: Chunk, Citacao, RespostaAgente...
│   ├── repository.py      Protocol ChunkRepository + InMemoryChunkRepository (testes)
│   │                      + SupabaseChunkRepository (psycopg+pgvector) + criar_conexao()
│   └── migrations/
│       ├── 001_schema_inicial.sql        Schema completo, idempotente, com RLS.
│       │                                 Aplicar: tools/setup_supabase.py --apply
│       └── rascunho_busca_hibrida.sql    Supersedido — RPC que não entrou (ver cabeçalho)
├── ingestion/
│   ├── chunking.py        Quebra estrutural por seções de edital → Chunk com metadados
│   └── embeddings.py      Pipeline incremental + FakeEmbeddingProvider /
│                          LangChainEmbeddingProvider (camada LangChain — ADR-008)
├── retrieval/
│   ├── hybrid_search.py   Vetorial + léxica fundidas por RRF, com piso de relevância
│   └── langchain_retriever.py
│                          HybridSearcher exposto como BaseRetriever do LangChain
└── agent/
    ├── agent.py           Orquestração: interpretar → buscar → refinar → responder → citar
    ├── prompts.py         Prompts + regras de citação obrigatória
    ├── citations.py       Monta contexto numerado e resolve [n] → chunk → documento → página
    └── llm.py             Protocol LLMClient + FakeLLM (testes) / AnthropicLLM (produção)

tests/                     Testes offline. conftest.py tem as fixtures compartilhadas.
tools/                     CLIs finos sobre o pacote (chunk_document, generate_embeddings,
                           setup_supabase)
```

## 4. O padrão que sustenta tudo: dependências injetáveis

Cada fronteira externa é um `Protocol`:

| Fronteira | Protocol | Fake (testes) | Real (produção) |
|---|---|---|---|
| Banco de dados | `ChunkRepository` | `InMemoryChunkRepository` | `SupabaseChunkRepository` (✅ validado contra o banco real — `--smoke`) |
| Embeddings | `EmbeddingProvider` | `FakeEmbeddingProvider` | `criar_provedor_openai()` / `criar_provedor_voyage()` → `LangChainEmbeddingProvider` |
| LLM | `LLMClient` | `FakeLLM` | `AnthropicLLM` / `OpenRouterLLM` |
| Busca | `Searcher` | `SearcherStub` (em `tests/test_agent.py`) | `HybridSearcher` |

Consequência prática: **nenhum código de domínio muda entre teste e produção** — troca-se o `InMemoryChunkRepository` pelo `SupabaseChunkRepository` e o fake de embeddings pelo real.

## 5. Decisões de design que não são óbvias no código

**Chunking conta caracteres, não tokens.** `estimar_tokens` é `len // 4`; somar isso peça por peça subestima o total (cada peça perde até 3 caracteres no arredondamento) e o erro acumula. Era a causa de chunks 14% acima do teto. Ver `_orcamento_corpo_chars` em [chunking.py](../src/pharma_rag/ingestion/chunking.py).

**O prefixo contextual entra no orçamento do chunk.** Cada chunk começa com `[Edital PE 045/2023 – Órgão – Seção: X]` para o embedding carregar contexto. Esse prefixo conta no `token_count`, então sai do orçamento do corpo — e ele cresce com o tamanho do nome do órgão.

**A busca tem piso de similaridade** (`SIMILARIDADE_MINIMA_PADRAO = 0.15`). Sem ele, a busca vetorial devolve sempre os k mais próximos por mais irrelevantes que sejam: o agente nunca conseguiria dizer "não encontrei no acervo", e responderia qualquer pergunta com contexto aleatório. **Este valor padrão foi calibrado contra o provedor fake e é recalibrado em produção com embeddings reais.**

**O provedor fake usa 1024 dimensões, igual à produção.** Não é simetria estética: com 64 dimensões, colisões de hash davam similaridade alta a textos sem nenhuma palavra em comum (`"inexistente zzz"` pontuava acima de `"autoclave"` contra um edital de autoclaves), o que invertia o resultado dos testes de relevância.

**A busca busca 2× candidatos antes de fundir** — mesma proporção do `match_count * 2` da RPC SQL, para que o comportamento testado offline seja representativo do de produção.

**LangChain entra no pipeline, não no agente** (ADR-008, opção B). `LangChainEmbeddingProvider` adapta qualquer `Embeddings` do LangChain ao Protocol `EmbeddingProvider` — trocar OpenAI por outro fornecedor é trocar o objeto passado ao adaptador, sem tocar no pipeline. O grafo do agente segue em Python puro, e o cliente Anthropic segue no SDK direto (o wrapper perderia o prompt caching e o tratamento de `refusal`). O import de `langchain_openai` é tardio, então os testes rodam sem a biblioteca instalada.

**Indexação é incremental por hash.** Cada chunk tem `content_hash` (SHA-256, não `hash()` do Python, que é salteado por processo). Só é re-embeddado o que mudou.

## 6. O contrato de citação (requisito central do projeto)

Toda afirmação do agente deve referenciar `[n]`, que resolve para chunk → documento → página.

`RespostaAgente` carrega o resultado dessa verificação:

| Campo | Significado |
|---|---|
| `citacoes` | Citações resolvidas, com documento, seção e páginas |
| `citacoes_invalidas` | Marcadores `[n]` que não existem no contexto (alucinação de fonte) |
| `contrato_citacao_ok` | **False** se houve marcador inválido OU se a resposta não citou nada apesar de haver contexto |
| `encontrou_no_acervo` | False quando a busca não achou nada acima do piso de relevância |

> **Para a frente de Interface:** `contrato_citacao_ok == False` significa resposta **não confiável** — não deve ser exibida como resposta normal ao usuário.

## 7. Evolução e Integração

| Item | Estado | Responsável |
|---|---|---|
| **Ponte chunking → Supabase** | Especificada em [workflows/indexacao.md](../workflows/indexacao.md) e implementada em `ingestion/cadastro.py` e `ingestion/traducao.py` | Frente RAG |
| `tools/setup_supabase.py --check --smoke` | Valida schema e repositório contra o banco real | Frente RAG |
| Reranker concreto (Voyage `rerank-2.5`) | Integrado após fusão RRF (ADR-011) | Frente RAG |
| **Golden set de avaliação** | Implementado em `data/golden_set.json` e avaliado via `tools/avaliar.py` | Frente RAG |

## 8. Decisões de banco já fechadas (06/08/26)

As duas lacunas de DDL que bloqueavam o repositório foram resolvidas em [001_schema_inicial.sql](../src/pharma_rag/db/migrations/001_schema_inicial.sql):

1. **`content_hash` + `embedding_content_hash` em `doc_chunks`.** São dois campos, não um: o primeiro é o hash do conteúdo atual, o segundo é o hash do que foi de fato embeddado. Pendente = `embedding is null OR os dois diferem`. Com um campo só não dá para saber se o embedding está velho.
2. **`orgao` e `data` continuam só em `licitacoes`**, acessados por JOIN — sem duplicar escrita. `FiltrosBusca` não mudou: no Supabase os filtros viram cláusulas SQL sobre o JOIN, e o `aceita()` em Python segue servindo só ao repositório em memória.

**RLS ligado, sem policies.** Tudo em `public` é publicado pela API REST do Supabase; sem RLS a publishable key (que vai no frontend) lê e escreve o acervo. O backend passa por conexão direta, que não é afetada. Policies para `authenticated` entram quando houver login.

## 9. Operação contínua

1. `make banco` (ou `python tools/setup_supabase.py --check --smoke`) reconfere schema e repositório contra o banco real a qualquer momento;
2. Indexação e tradução seguem o fluxo documentado em [workflows/indexacao.md](../workflows/indexacao.md);
3. Ao alterar modelos de embedding ou expandir o acervo, recalibrar o piso de similaridade e rodar `tools/avaliar.py` contra o golden set.
