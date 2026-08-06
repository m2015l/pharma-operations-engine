# Frente RAG & Agente — guia do código

> **Comece por aqui** se você vai mexer no pipeline RAG ou no agente.
> Branch: `feature/rag-agente` · Estado: implementado e testado offline, **não mergeado**
> (há uma decisão pendente — ver [ADR-005 em DECISOES.md](DECISOES.md)).

---

## 1. Em uma frase

O pacote `src/solufarma_rag/` transforma documentos de licitação em chunks indexados e responde perguntas sobre eles citando as fontes. **Nada depende de Supabase ou de chaves de API para rodar**: toda dependência externa é um Protocol com implementação fake.

## 2. Como rodar (do zero, 2 minutos)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install pydantic pytest ruff

.venv/Scripts/python.exe -m pytest              # 56 testes, ~0.2s, sem rede
.venv/Scripts/python.exe -m ruff check src/ tests/ tools/
```

Os CLIs (framework WAT):

```bash
# Chunking de um documento já extraído (JSON de entrada descrito no --help)
.venv/Scripts/python.exe tools/chunk_document.py documento.json > chunks.json

# Pipeline de embeddings — só --dry-run funciona até o Supabase existir
.venv/Scripts/python.exe tools/generate_embeddings.py --dry-run
```

> Python local usado: 3.14. `requirements.txt` tem a lista completa do projeto;
> para rodar só os testes bastam `pydantic`, `pytest` e `ruff`.

## 3. Mapa do código

```
src/solufarma_rag/
├── config.py              Lê .env (Supabase, chaves, modelos). Sem pydantic-settings.
├── text_utils.py          normalizar() e tokenizar() — espelham unaccent+FTS do Postgres.
├── db/
│   ├── models.py          Contratos Pydantic: Chunk, Citacao, RespostaAgente...
│   ├── repository.py      Protocol ChunkRepository + InMemoryChunkRepository (testes)
│   │                      + SupabaseChunkRepository (esqueleto — levanta NotImplementedError)
│   └── migrations/rascunho_busca_hibrida.sql
│                          ENTREGA para a frente de Dados & Infra. NÃO aplicar daqui.
├── ingestion/
│   ├── chunking.py        Quebra estrutural por seções de edital → Chunk com metadados
│   └── embeddings.py      Pipeline incremental + FakeEmbeddingProvider / OpenAIEmbeddingProvider
├── retrieval/
│   └── hybrid_search.py   Vetorial + léxica fundidas por RRF, com piso de relevância
└── agent/
    ├── agent.py           Orquestração: interpretar → buscar → refinar → responder → citar
    ├── prompts.py         Prompts + regras de citação obrigatória
    ├── citations.py       Monta contexto numerado e resolve [n] → chunk → documento → página
    └── llm.py             Protocol LLMClient + FakeLLM (testes) / AnthropicLLM (produção)

tests/                     56 testes offline. conftest.py tem as fixtures compartilhadas.
tools/                     CLIs finos sobre o pacote (chunk_document, generate_embeddings)
```

## 4. O padrão que sustenta tudo: dependências injetáveis

Como Supabase e chaves de LLM ainda não existem, cada fronteira externa é um `Protocol`:

| Fronteira | Protocol | Fake (testes) | Real (produção) |
|---|---|---|---|
| Banco de dados | `ChunkRepository` | `InMemoryChunkRepository` | `SupabaseChunkRepository` (a implementar) |
| Embeddings | `EmbeddingProvider` | `FakeEmbeddingProvider` | `OpenAIEmbeddingProvider` (escrito, sem chave) |
| LLM | `LLMClient` | `FakeLLM` | `AnthropicLLM` (escrito, sem chave) |
| Busca | `Searcher` | `SearcherStub` (em `tests/test_agent.py`) | `HybridSearcher` |

Consequência prática: **quando as credenciais chegarem, só o repositório precisa ser escrito** — o resto do código não muda.

## 5. Decisões de design que não são óbvias no código

**Chunking conta caracteres, não tokens.** `estimar_tokens` é `len // 4`; somar isso peça por peça subestima o total (cada peça perde até 3 caracteres no arredondamento) e o erro acumula. Era a causa de chunks 14% acima do teto. Ver `_orcamento_corpo_chars` em [chunking.py](../src/solufarma_rag/ingestion/chunking.py).

**O prefixo contextual entra no orçamento do chunk.** Cada chunk começa com `[Edital PE 045/2023 – Órgão – Seção: X]` para o embedding carregar contexto. Esse prefixo conta no `token_count`, então sai do orçamento do corpo — e ele cresce com o tamanho do nome do órgão.

**A busca tem piso de similaridade** (`SIMILARIDADE_MINIMA_PADRAO = 0.15`). Sem ele, a busca vetorial devolve sempre os k mais próximos por mais irrelevantes que sejam: o agente nunca conseguiria dizer "não encontrei no acervo", e responderia qualquer pergunta com contexto aleatório. **Este valor foi calibrado contra o provedor fake e PRECISA ser recalibrado com embeddings reais.**

**O provedor fake usa 1024 dimensões, igual à produção.** Não é simetria estética: com 64 dimensões, colisões de hash davam similaridade alta a textos sem nenhuma palavra em comum (`"inexistente zzz"` pontuava acima de `"autoclave"` contra um edital de autoclaves), o que invertia o resultado dos testes de relevância.

**A busca busca 2× candidatos antes de fundir** — mesma proporção do `match_count * 2` da RPC SQL, para que o comportamento testado offline seja representativo do de produção.

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

## 7. O que ficou faltando (e por quê)

| Item | Por que não foi feito | Dono |
|---|---|---|
| `SupabaseChunkRepository` | Faltam credenciais **e** duas decisões de DDL (ver §8) | Frente RAG, após Dados & Infra |
| `tools/verify_index.py` | Depende do Supabase provisionado | Frente RAG |
| Reranker concreto (Haiku) | O hook injetável existe; falta chave de API | Frente RAG |
| **Golden set de avaliação** | Depende de casos reais da Solufarma. **É a lacuna mais séria** — a skill `rag-licitacoes` pede avaliação desde o início, e sem ela toda mudança de prompt/chunking é feita no escuro | Frente RAG ↔ Cliente |
| Integração LangChain | Decisão pendente da equipe — [ADR-005](DECISOES.md) | Equipe/Diva |

## 8. Pendências que bloqueiam a frente de Dados & Infra

Levantadas na revisão de código; estão detalhadas no rodapé de [rascunho_busca_hibrida.sql](../src/solufarma_rag/db/migrations/rascunho_busca_hibrida.sql):

1. **`doc_chunks` não tem coluna `content_hash`** no DDL da arquitetura. Toda a indexação incremental depende dela. `documentos.hash_sha256` não serve — é dedup do arquivo inteiro, não do chunk.
2. **`orgao` e `data` vivem no `Chunk` do Python, mas só em `licitacoes` no DDL.** Decidir: denormalizar as colunas em `doc_chunks`, ou fazer `FiltrosBusca` operar sobre o JOIN.

## 9. Por onde continuar

1. Resolver a decisão do LangChain ([ADR-005](DECISOES.md)) — bloqueia o merge;
2. Alinhar as duas pendências de DDL com a frente de Dados & Infra;
3. Com o Supabase de pé: implementar `SupabaseChunkRepository` (o Protocol já define exatamente o que ele precisa fazer);
4. Com as chaves de LLM: trocar os fakes pelos reais e **recalibrar o piso de similaridade**;
5. Montar o golden set com casos reais e passar a rodá-lo a cada mudança de prompt ou chunking.
