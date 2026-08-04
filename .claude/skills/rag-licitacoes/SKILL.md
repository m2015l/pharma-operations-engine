---
name: rag-licitacoes
description: Guia de implementação do pipeline RAG do projeto Solufarma - chunking de editais, embeddings, busca híbrida no pgvector, citação de fontes e avaliação de qualidade do retrieval. Use ao implementar ou revisar qualquer parte do pipeline de RAG, base vetorial ou lógica do agente de licitações.
---

# RAG para Licitações — Guia de Implementação

Regras e padrões para o pipeline RAG do projeto. Consulte `docs/ARQUITETURA.md` para o design completo; este skill resume as regras operacionais.

## Chunking de editais

- Editais são longos e estruturados em seções (objeto, habilitação, itens/lotes, anexos). **Chunking por estrutura** (seções/cláusulas) antes de chunking por tamanho;
- Tamanho alvo: 500–1000 tokens por chunk com overlap de ~10–15%;
- Cada chunk carrega metadados obrigatórios: `documento_id`, `tipo_documento` (edital/ata/resultado), `orgao`, `data`, `secao`, `pagina` — a página é essencial para a citação de fontes;
- Tabelas de itens/equipamentos: extrair também como dados estruturados (linhas na tabela de itens), não apenas como texto.

## Embeddings e indexação

- Gerar embeddings em lote (batch API quando disponível — mais barato);
- Armazenar no pgvector com índice HNSW; registrar o modelo de embedding usado em cada linha (permite migração futura);
- Nunca reindexar tudo por mudança pequena: pipeline deve ser incremental (hash do conteúdo do chunk).

## Retrieval

- **Busca híbrida**: similaridade vetorial + filtros SQL por metadados (órgão, período, tipo de documento) + full-text search do Postgres quando a consulta tem termos exatos (números de edital, códigos de item);
- Top-k inicial generoso (20–30) seguido de reranking para 5–8 chunks finais;
- Toda resposta do agente DEVE citar as fontes: documento, seção e página de cada chunk usado. Resposta sem fonte rastreável é bug, não feature incompleta.

## Avaliação (fazer desde o início, não no final)

- Manter um conjunto de perguntas-teste com respostas esperadas (golden set) baseado em casos reais da Solufarma;
- Métricas mínimas: o chunk correto está no top-k? (recall) / a resposta cita a fonte certa? / a resposta contradiz o acervo?
- Rodar o golden set a cada mudança de prompt, chunking ou modelo — registrar resultados no `DIARIO_DE_BORDO.md`.

## Custos

- Logar tokens de entrada/saída de toda chamada LLM (tabela de log no banco);
- Preferir modelos menores para classificação/sumarização em massa; reservar o modelo top para o agente conversacional.
