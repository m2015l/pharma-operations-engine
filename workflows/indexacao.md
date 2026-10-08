# SOP — Indexação (M3): da saída do chunking para o Supabase

> **Estado**: não implementado. Este documento é a especificação para quem for escrever.
> Tudo que ele depende **já existe e está testado** — o que falta é só a peça de encaixe.
> Marco M3 · alvo `make indexar` · ADR-006, ADR-007, ADR-008

---

## 1. Por que este documento existe

Duas frentes construíram metades que se encaixam, mas foram desenhadas separadamente:

- A frente de **extração** (Diva) termina em `data/chunks/<stem>_chunks.json` e
  `data/chunks/<stem>_itens.json`, produzidos por `solufarma.chunking.chunkar_documento()`;
- A frente de **RAG** começa em `SupabaseChunkRepository.upsert_chunks(list[Chunk])`, com o
  `Chunk` de `solufarma_rag.db.models`.

Os dois `Chunk` têm o mesmo nome e **nenhum campo em comum além de `pagina_inicio`/`pagina_fim`**.
A peça que falta é a tradução entre eles. Nada mais.

## 2. O que já está pronto (não reimplementar)

| Peça | Onde | Estado |
|---|---|---|
| Schema no Supabase | `db/migrations/001_schema_inicial.sql` | ✅ aplicado no banco real |
| Repositório (upsert, busca vetorial e léxica, incremental) | `db/repository.py` | ✅ validado contra o banco real |
| Pipeline de embeddings incremental | `ingestion/embeddings.py` | ✅ |
| Busca híbrida + RRF | `retrieval/hybrid_search.py` | ✅ |
| Agente com citação obrigatória | `agent/` | ✅ |
| Diagnóstico e smoke test do banco | `tools/setup_supabase.py --check --smoke` | ✅ |

`python tools/setup_supabase.py --smoke` roda o caminho completo (upsert → embeddings →
busca → filtro) contra o Supabase de verdade e limpa o que criou. **Se ele passa, a camada
de banco está boa** — qualquer erro novo está na peça de encaixe, não abaixo dela.

## 3. O mapeamento, campo a campo

`solufarma.modelos.Chunk` (origem) → `solufarma_rag.db.models.Chunk` (destino):

| Destino | Vem de | Observação |
|---|---|---|
| `conteudo` | `texto` | É o texto **com** cabeçalho contextual — é o que vai para o embedding |
| `pagina_inicio` / `pagina_fim` | iguais | Único par que já casa |
| `secao` | `" > ".join(caminho_secao)` | O destino é string, a origem é lista |
| `token_count` | `n_chars // 4` | Ou usar `estimar_tokens()` de `ingestion.chunking` |
| `content_hash` | `Chunk.calcular_hash(texto)` | **Calcular**, não existe na origem. É a base do incremental |
| `chunk_index` | sequência do `id` (`...#c0007` → `7`) | Ou reenumerar na ordem da lista |
| `documento_id` | **resolver** — ver §4 | A origem traz `hash_documento`, o destino quer o UUID |
| `tipo_documento` | **não vem do chunking** | Vem do cadastro do documento |
| `orgao` / `data` | **não vem do chunking** | Vivem em `licitacoes`, via JOIN |

Três campos do destino não têm origem no chunking, e isso não é falha do chunker: são
metadados do *documento*, não do *pedaço*. Entram no passo de cadastro (§4).

O campo `tipo` da origem (`prosa` | `tabela` | `metadados`) não tem destino hoje. Vale
avaliar guardá-lo — o agente pode querer priorizar prosa em pergunta conceitual.

## 4. O passo que ainda não existe: cadastrar o documento

Hoje nada preenche `licitacoes` e `documentos`. Sem isso não há `documento_id` (UUID) para
o chunk apontar, e `orgao`/`tipo_documento`/`data` ficam sem fonte.

O que o passo precisa fazer, por documento:

1. Subir o PDF original para o Supabase Storage → `documentos.storage_path` (é o que
   sustenta o link de "ver a fonte" na interface);
2. Inserir/achar a linha em `licitacoes` (órgão, número do edital, data de abertura);
3. Inserir a linha em `documentos` com `licitacao_id`, `tipo`, `hash_sha256`, `num_paginas`;
4. Devolver o UUID gerado — é o `documento_id` de todos os chunks daquele arquivo.

**De onde vêm órgão, número do edital e data?** Não do OCR. Ou o usuário informa no upload
(ADR-003: entrada pelo Streamlit), ou um LLM extrai da capa. Essa é a decisão em aberto
mais concreta deste SOP.

`itens_planilha` já aceita gravação **antes** desse cadastro: ela guarda `documento_hash`
(o que o chunking produz) e tem `documento_id` nulo até a resolução. Foi desenhada assim
de propósito, para a ingestão não travar esperando cadastro.

## 5. Ordem de execução

### Passo 0: triagem pelo conteúdo, antes de tudo (desde 29/09)

**Nunca confie no nome do arquivo.** No lote do Drive de 28/09, 19 de 32 PDFs tinham o nome
trocado. A troca era sistemática: com os arquivos em ordem alfabética, o conteúdo de cada um é
o documento que tem o nome do arquivo **anterior** (18 casos bateram pelo nº da CAT, 0
contradições). Um documento do lote (SS WHITE 11686-2010) não estava em arquivo nenhum.

1. `uv run python tools/triar_documentos.py` → `.tmp/triagem_documentos.{md,json}`. Não custa
   nada (só regex): nº CAT, contratante, **executante** (TEP × Solufarma), texto nativo × precisa
   OCR, nome bate × trocado, duplicatas, custo estimado de OCR;
2. Confira no texto o órgão e o objeto de cada documento que vai entrar. Se o nome estiver
   errado, **copie** (não renomeie nem mova) o PDF para `data/brutos/` com o nome certo. O
   nome vira o `storage_path` no Storage, então ele precisa estar correto;
3. Documento com OCR antigo ilegível e sem contratante identificável fica de fora: indexar
   lixo piora a busca dos outros;
4. Gere os chunks com o título tirado do conteúdo:
   `tools/chunk_document.py data/extraidos/<stem>.json --titulo "..."`. O `indexar.py` usa
   esse título e **recusa** um `--titulo` diferente;
5. `tools/indexar.py data/brutos/<stem>.pdf --tipo atestado --orgao "<órgão do conteúdo>"`.

**Para extrair sem risco de custo** (só páginas nativas), substitua
`solufarma.extracao.chamar_vlm` por uma função que levanta erro antes de chamar
`extracao.processar`. Se alguma página cair na rota VLM, a execução para em vez de cobrar.
Exemplo usado em 29/09: `.tmp/lote_nativo/extrair_sem_vlm.py`.

Depois de cada lote relevante: rode `tools/avaliar.py --provedor voyage`. Os controles
negativos do golden set foram escritos para um acervo de 1 documento e precisam ser revistos
conforme o acervo cresce. Recalibre o piso com `--calibrar`.

**Reindexar um documento que já está no banco** (ex.: depois de mudar o chunker): refaça os
chunks com o mesmo `--titulo` e rode o `indexar.py` de novo. Ele atualiza título e método de
extração do documento e remove, numa transação, os `chunk_index` antigos que sumiram (sem
órfãos). Depois, `generate_embeddings.py --documento-id <uuid>` embedda só aquele documento, sem
pegar chunks pendentes de outra sessão. **Não reindexe a CAT do SENAI 576640**: ela tem o patch
manual do I6.

**Aprendido no lote de 07/10 (5 documentos, 837 chunks):**

- **Migrações pendentes travam a indexação no meio.** O `indexar.py` falhou com
  `column "status" of relation "itens_planilha" does not exist` porque a
  `004_qualidade_itens.sql` estava no repositório e não no banco. O
  `setup_supabase.py --apply` só aplica a 001; as demais são aplicadas à mão. A falha
  acontece depois do cadastro e dos chunks, então o documento fica gravado sem linhas de
  planilha: basta aplicar a migração e rodar o `indexar.py` de novo (não duplica);
- **Chunk só com título deixa o documento em `chunked`.** O `generate_embeddings.py`
  pula chunks de ruído (`pulados_ruido`), mas eles continuam contando como pendentes,
  então o documento não vira `indexado` e a tela de Acervo mostra "Em processamento".
  Em 07/10 isso foi resolvido à mão com `repo.marcar_documento_indexado()` em 3
  documentos; a correção de verdade é no código (ruído não deveria contar como pendência);
- **A gravação de `itens_planilha` é lenta** (um `insert` por linha): cerca de 10 minutos
  para 4.000 linhas. Rode em segundo plano;
- Depois do lote: golden set em 22/22, controles 4/4, com 29 documentos e 1.687 chunks.

### Pipeline

```
extrair  →  chunks  →  [cadastrar documento]  →  [traduzir chunks]  →  upsert  →  embeddings
                             ↑ falta              ↑ falta
```

O `upsert` e o `embeddings` já existem: `gerar_embeddings_pendentes(repo, provider)`.

## 6. Duas armadilhas que já custaram caro

**O `content_hash` governa custo.** Ele é SHA-256 do `conteudo` **inteiro**, cabeçalho
contextual incluído. Qualquer mudança no formato do cabeçalho — um traço, uma
capitalização — muda todos os hashes e força reembeddar o acervo inteiro, sem erro nenhum,
só a conta chegando maior. Se o formato do cabeçalho mudar, é decisão consciente.

**O piso de relevância está calibrado contra um provedor falso.**
`SIMILARIDADE_MINIMA_PADRAO = 0.15` em `retrieval/hybrid_search.py` foi ajustado contra o
`FakeEmbeddingProvider` (bag-of-words). A escala de similaridade de um modelo real é outra.
Sem recalibrar, ou a busca volta sempre vazia, ou aceita qualquer coisa — e nos dois casos
**sem erro**, só resposta ruim.

## 7. O que ainda depende de decisão

| # | Decisão | Efeito se adiar |
|---|---|---|
| 1 | **Modelo de embeddings** (Voyage × OpenAI) — em aberto por decisão do Roger (09/08) | Trocar depois de indexar o acervo obriga a recriar a coluna `vector(N)` e reprocessar tudo. Barato agora, caro depois |
| 2 | Origem de `orgao` / `numero_edital` / `data` (usuário no upload × LLM na capa) | Bloqueia o §4 |
| 3 | Guardar o `tipo` do chunk (prosa/tabela/metadados) | Só limita o agente; não bloqueia |

**Decisões já fechadas:** acesso ao banco é por `DATABASE_URL` (psycopg direto), não pela
API REST — a REST não faz operador de vetor nem full-text com filtro (Roger, 09/08). E o
chunker é o de `solufarma.chunking`, porque o acervo é escaneado (Roger, 09/08); o chunker
de edital nativo em `solufarma_rag/ingestion/chunking.py` não tem fonte de entrada neste
fluxo.
