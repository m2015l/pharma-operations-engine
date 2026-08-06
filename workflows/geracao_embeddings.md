# Workflow: Geração de Embeddings e Indexação

## Objetivo

Gerar embeddings dos chunks de documentos com status `pronto_para_embedding` e indexá-los no pgvector (Supabase), deixando-os disponíveis para a busca híbrida do RAG.

## Entradas necessárias

- Documentos com status `pronto_para_embedding` no banco (produzidos pelo workflow `ingestao_documento.md`);
- Credenciais no `.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY` (embeddings), `EMBEDDING_MODEL`.

## Ferramentas

| Etapa | Tool | Status |
|-------|------|--------|
| Geração + gravação dos embeddings | `tools/generate_embeddings.py` (lógica em `src/solufarma_rag/ingestion/embeddings.py`) | ✅ implementado — só `--dry-run` até o Supabase existir |
| Busca híbrida (vetorial + léxica + RRF) | `src/solufarma_rag/retrieval/hybrid_search.py` | ✅ implementado (offline) |
| Verificação da indexação / smoke test de busca | `tools/verify_index.py` | 🔲 a implementar (depende do Supabase provisionado) |

> Cobertura de testes offline: `tests/test_embeddings.py` e `tests/test_hybrid_search.py`.
> A função RPC `busca_hibrida` está rascunhada em
> `src/solufarma_rag/db/migrations/rascunho_busca_hibrida.sql` — **aplicação é da
> frente de Dados & Infraestrutura**.

> Regras detalhadas: skill `rag-licitacoes` (Skills/rag-licitacoes/SKILL.md). Modelo recomendado: `text-embedding-3-large` com `dimensions=1024` (ver docs/ARQUITETURA.md §2.2).

## Sequência

1. **Selecionar chunks pendentes**: chunks sem embedding OU cujo `content_hash` mudou desde a última indexação (incremental — nunca reindexar tudo por mudança pequena).
2. **Gerar embeddings em lote** (batches de ~100 chunks por chamada; usar Batch API quando o volume justificar — mais barato). Registrar em cada linha o modelo e a dimensão usados (`embedding_model`).
3. **Gravar no pgvector** em transação por documento; ao concluir todos os chunks, status do documento → `indexado`.
4. **Verificar**: rodar smoke test — uma consulta semântica com termo do próprio documento deve retornar chunks dele no top-k. Falhou → status `erro` e investigar antes de prosseguir.
5. **Registrar custo** (tokens de embedding consumidos no lote) no log.

## Saídas esperadas

- Todos os chunks do lote com embedding gravado e índice HNSW atualizado;
- Documentos com status `indexado`;
- Log com contagem de chunks, custo e resultado do smoke test.

## Casos de borda e regras

- **Rate limit / falha de API no meio do lote**: retomar apenas os chunks faltantes (o estado por chunk garante isso); backoff exponencial;
- **Troca de modelo de embedding**: NUNCA misturar modelos no mesmo índice de busca — migração exige reindexação completa registrada como ADR;
- **Chunk vazio ou só ruído de OCR** (ex.: página de carimbos): pular e marcar, não indexar lixo — retrieval ruim é pior que acervo menor;
- **Primeiro uso**: conferir que a extensão `vector` está habilitada no Supabase e o índice HNSW criado (DDL em docs/ARQUITETURA.md §3).

## Aprendizados

_(registrar aqui limites de batch, latências e comportamentos observados)_
