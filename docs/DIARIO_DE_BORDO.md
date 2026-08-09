# Diário de Bordo — Solufarma Módulo 2

> Registro cronológico do trabalho. Cada sessão de trabalho relevante ganha uma entrada no topo (mais recente primeiro).
> Formato: data, quem trabalhou, o que foi feito, o que aprendemos, próximos passos.

---

## 2026-08-07 — Pipeline de extração e chunking implementado (M0 + M1) (Roger + Claude)


**O que foi feito:**

*Decisões de arquitetura tomadas antes de codar:*
- **OCR por VLM via OpenRouter** com `anthropic/claude-sonnet-5`, em cascata com extração nativa (ADR-005) — fecha a pendência P3;
- **Código em `src/solufarma/` com `tools/*.py` como CLIs finos**, conciliando o BRIEFING com o framework WAT (ADR-007);
- **Chunking por regime de conteúdo**, sem LangChain nesta fase (ADR-006).

*Estrutura criada (M0):*
- `pyproject.toml` com todas as dependências (pymupdf, pillow, requests, voyageai, supabase, pytest, ruff) e entry points;
- `src/solufarma/config.py` — validação de ambiente **por estágio** (`exigir("extracao")` / `exigir("indexacao")`), falhando com mensagem que nomeia a variável faltante;
- `.gitignore` corrigido: `data/` inteiro e `.cache_ocr/` — antes só cobria `data/raw/` e `data/processed/`, e um documento de cliente colocado em `data/brutos/` teria ido para o GitHub;
- `.env.example` reescrito por estágio (extração agora, indexação no M3);
- `Makefile` com os equivalentes `uv run` documentados (o `make` não está instalado no Windows).

*Pipeline de extração (M1):*
- `formatos.py` — `sniff()` por magic number (`%PDF`, `PK\x03\x04`, `\xff\xd8\xff`, PNG) + renderização de páginas;
- `extracao.py` — detecção de boilerplate global, roteamento por dupla condição (caracteres úteis **E** densidade), chamada ao OpenRouter com carry-over entre páginas, blocos contíguos em paralelo, cache por hash, lote tolerante a falha (`falhas.jsonl`) e relatório de custo;
- `prompts.py` — prompts de transcrição isolados; entram na assinatura do cache;
- `chunking.py` — costura entre páginas, parsing em blocos com caminho de seção, chunkers por regime, extração de linhas de planilha para dados relacionais;
- `cli.py` + `tools/extract_text.py` + `tools/chunk_document.py`;
- `workflows/ocr_escaneados.md` — SOP do marco, com tabela de falhas conhecidas.

*Testes:*
- 4 fixtures **sintéticas** cobrindo os quatro invariantes (`tests/conftest.py`);
- **33 testes passando**, `ruff check` limpo;
- Verificado manualmente: `config.exigir("extracao")` falha com mensagem legível e o CLI retorna erro tratado (exit 2) sem `.env`.

**Aprendizados / observações:**

- **Bug real encontrado no `chunking.py` de origem:** `extrair_linhas_tabela` pulava o separador `|---|---|` mas **não a linha de cabeçalho**. Cada tabela injetaria uma linha lixo em `itens_planilha`, e um `SUM(quantidade)` tentaria converter a string `"Quantidade"` para número. Corrigido (ignora o separador *e* a linha anterior a ele). É exatamente o modo de falha silenciosa que o projeto combate — número errado com cara de certo.
- **Bug secundário:** a leitura do ZIP usava `Path(n).with_suffix(".txt").name`, que descarta o diretório. Se o container tivesse subpastas, o texto nativo irmão nunca seria encontrado. Corrigido preservando o caminho.
- **Ordenação numérica no ZIP é carga crítica:** ordenação alfabética colocaria `pagina_10` antes de `pagina_2`, embaralhando o documento sem erro — e o carry-over passaria contexto da página errada.
- **Conflito de documentação a resolver:** `docs/ARQUITETURA.md` §2.2 fecha em OpenAI `text-embedding-3-large`; o `CLAUDE.md` do BRIEFING fecha em Voyage `voyage-3`. Ainda não resolvido (P2 continua aberta) — só afeta o M3.
- O `make` não existe no ambiente Windows do Roger; os alvos foram duplicados como `uv run` no Makefile e no workflow.

**O que NÃO foi verificado (e por quê):**

Os critérios de aceite do M1 que dependem do documento real **não foram validados** — o `SENAI_CETIQT_CAT_576640.pdf` não está no repositório:
- "2 páginas nativas, 58 via VLM" — não verificável;
- "nenhum carimbo do CAU no markdown final" — não verificável;
- "custo US$ 0,00 na segunda execução" — exige chave da API;
- "tabela das págs. 44–45 com cabeçalho nas duas" — verificado só em fixture sintética.

As fixtures reproduzem numericamente as condições do CLAUDE.md (347 caracteres em área A4 dão 0,000218 char/px², abaixo do limiar de 0,00035, e portanto roteiam para VLM), mas **nenhuma prova que o documento real se comporta assim**.

**Próximos passos:**
1. Roger: criar conta no OpenRouter, carregar crédito (~US$ 25–30 cobre M1 + M2) e preencher `OPENROUTER_API_KEY` no `.env`;
2. Roger: confirmar o slug do modelo em openrouter.ai/models e ajustar `OPENROUTER_MODELO` + os preços se divergir;
3. Roger: colocar `SENAI_CETIQT_CAT_576640.pdf` em `data/brutos/`;
4. Rodar `uv run python tools/extract_text.py` e fechar os critérios de aceite do M1;
5. Trocar as fixtures sintéticas por extratos do documento real;
6. Reunir os 20 documentos variados do Drive para o **M2 (calibração)** — que é portão: não indexar nada antes de os limiares serem confirmados;
7. Implementar `calibracao.py` (M2) — só faz sentido depois da primeira extração real.

---

## 2026-08-06 — Supabase: schema, repositório real e Retriever LangChain (Roger + Claude)


**O que foi feito:**
- `migrations/001_schema_inicial.sql` — schema completo e idempotente, com as duas lacunas de DDL
  resolvidas: `doc_chunks` ganhou `content_hash` + `embedding_content_hash` (indexação incremental);
  `orgao`/`data` continuam só em `licitacoes`, acessados por JOIN, sem duplicar escrita;
- `SupabaseChunkRepository` implementado com psycopg + pgvector (era esqueleto que levantava
  `NotImplementedError`), mais `criar_conexao()`;
- `SolufarmaRetriever` — a busca híbrida exposta como `BaseRetriever` do LangChain, com 8 testes;
- `tools/setup_supabase.py --apply --check` aplica a migração e diagnostica o banco;
- `.env.example` e `config.py` atualizados para as chaves novas do Supabase
  (`sb_publishable_` / `sb_secret_`), com fallback para os nomes antigos;
- 64 testes passando, ruff limpo. **Nada rodou contra o banco real ainda** — falta a senha.

**Duas decisões que mudaram o rumo:**
1. **`langchain-postgres` ficou de fora.** A ressalva da ADR-008 se confirmou: schema próprio,
   sem busca híbrida com filtros sobre `licitacoes`. Usá-lo custaria a rastreabilidade
   chunk → documento → página. O Retriever resolve sem essa troca;
2. **A RPC `busca_hibrida` não entrou no schema.** O RRF já existe em Python e é o que os testes
   cobrem; manter a fusão em duas linguagens deixaria a versão testada fora de produção. O backend
   faz duas consultas e funde em Python. Se a latência incomodar com acervo grande, a RPC volta —
   e aí os testes passam a rodar contra ela.

**Achado de segurança:** o schema estava sem RLS. Tudo em `public` é publicado pela API REST do
Supabase, então sem RLS qualquer um com a publishable key — que por definição vai embutida no
frontend — leria e escreveria o acervo inteiro. A migração agora liga RLS nas 5 tabelas sem
nenhuma policy (nega tudo via API); o backend segue funcionando por conexão direta. O `--check`
verifica isso.

**Bloqueio:** `DATABASE_URL` depende da senha do banco, que a Diva vai passar. Enquanto isso o
schema pode ser aplicado pelo SQL Editor do painel, que não exige a senha.

---

## 2026-08-06 — ADR-008 decidida: LangChain no pipeline, Python puro no agente (Roger + Claude)


**A decisão** (branch `feature/rag-agente`): Roger escolheu a **opção B** da [ADR-008](DECISOES.md),
que destravou o merge. A regra que sai disso, em uma linha: **LangChain é o encanamento do
pipeline de RAG; o grafo do agente e o cliente Anthropic ficam em Python puro.**

O cliente do LLM ficou de fora da camada LangChain de propósito — o `AnthropicLLM` atual faz
prompt caching do system prompt e trata `stop_reason == "refusal"` explicitamente, e passar por
wrapper custaria esse controle sem ganho contratual (o entregável nomeia o *pipeline de RAG*).

**O que foi implementado:**
- `OpenAIEmbeddingProvider` deu lugar a `LangChainEmbeddingProvider` + `criar_provedor_openai()`
  em [embeddings.py](../src/solufarma_rag/ingestion/embeddings.py). O adaptador aceita **qualquer**
  `Embeddings` do LangChain — trocar de fornecedor não toca no pipeline. A fábrica lê modelo e
  dimensão do `.env` via `get_settings()` (o provedor antigo hardcodava os valores, divergindo do
  `AnthropicLLM`, que já lia as settings);
- `requirements.txt` passou a listar só o que o código importa: entraram `langchain-core`,
  `langchain-postgres` e `langchain-text-splitters`; saíram `langchain`, `langchain-anthropic` e
  `langchain-community`. Declarar dependência que ninguém importa foi exatamente o que originou
  esta ADR — repetir isso do outro lado não resolveria nada;
- `PLANO_PROJETO.md`: o item "Orquestração com LangChain" foi reescrito, porque a decisão mudou o
  que ele significa — a orquestração **não** será LangChain.
- 56 testes pytest passando e ruff limpo, ainda 100% offline: o import de `langchain_openai` é
  tardio, então a suíte roda sem a biblioteca instalada e sem chave de API.

**Aprendizados / observações:**
- A metade "vector store" da opção B não pôde ser feita: depende do Supabase provisionado e das
  duas lacunas de DDL (pendências 9 e 10), que continuam abertas;
- ⚠️ **Ressalva registrada na ADR**: o `langchain-postgres` traz convenções próprias de schema e
  não executa a busca híbrida com RRF da RPC `busca_hibrida`. Se ele não acomodar o DDL da
  arquitetura, o caminho que preserva o projeto é expor o `HybridSearcher` como um `Retriever` do
  LangChain sobre o pgvector — segue sendo pipeline LangChain de ponta a ponta, sem descartar o
  schema. **Verificar antes de escrever o `SupabaseChunkRepository`, não depois.**

**Próximos passos:**
- Roger comunica a decisão à Diva — não bloqueia mais o merge, mas a gerência precisa saber que a
  forma do entregável 3 mudou;
- Fechar a integração do vector store quando o Supabase estiver de pé (ver ressalva acima).

---

## 2026-08-05 — Frente RAG & Agente: primeira fatia implementada (Roger + Claude)


**O que foi feito** (branch `feature/rag-agente`, ainda não mergeada):
- Pacote `src/solufarma_rag/` com chunking estrutural, pipeline incremental de embeddings, busca híbrida (vetorial + léxica + RRF) e agente com contrato de citação obrigatória;
- Toda dependência externa é injetável (Protocols): `FakeEmbeddingProvider`, `InMemoryChunkRepository` e `FakeLLM` permitem rodar tudo offline, sem Supabase e sem chaves de API;
- CLIs em `tools/chunk_document.py` e `tools/generate_embeddings.py`;
- Rascunho da RPC `busca_hibrida` em SQL — **entrega para a frente de Dados & Infra**, não aplicar daqui;
- 56 testes pytest offline + ruff limpo.

**Revisão dupla por agentes (revisor de código + guardião de escopo). Bugs reais encontrados e corrigidos:**
1. **Resposta sem nenhuma citação passava como sucesso** — quebrava o requisito central de rastreabilidade. `RespostaAgente` ganhou `contrato_citacao_ok` e `citacoes_invalidas`, com log de erro;
2. **Chunks estouravam o teto de tokens** (1143 contra teto de 1000): a contabilidade somava `estimar_tokens` por peça, e o arredondamento da divisão inteira acumulava; o prefixo contextual também não entrava no orçamento. Passou a ser contabilidade em caracteres;
3. **A busca nunca voltava vazia** — sem piso de similaridade, o agente jamais diria "não encontrei no acervo" e o loop de refinamento era código morto;
4. **O provedor fake de embeddings mentia** — com 64 dimensões, colisões de hash davam similaridade alta a textos sem palavra em comum; subido para 1024 (igual à produção);
5. Menores: JSON com BOM quebrava o CLI (Windows grava BOM), trecho da citação era dominado pelo prefixo, import de símbolo privado entre módulos (extraído para `text_utils.py`), divergências entre o Python e o rascunho SQL.

**Aprendizados:**
- Testes com tolerância folgada não pegam bugs: o teste do teto de tokens aceitava 2× o limite e por isso não viu o estouro de 14%;
- Um test double mal dimensionado inverte o resultado dos testes que deveria sustentar;
- Vale rodar revisão de escopo junto com a de código — foi ela que pegou a questão contratual do LangChain, que nenhuma revisão técnica apontaria.

**Onde ler os detalhes:**
- Guia completo do código da frente (estrutura, como rodar, decisões de design, o que falta): [FRENTE_RAG.md](FRENTE_RAG.md);
- Questão do LangChain, com opções e recomendação: [ADR-008 em DECISOES.md](DECISOES.md).

**Pendências abertas por esta sessão** (ver PLANO_PROJETO.md, itens 8–12):
- 🔴 **LangChain**: o código não usa a biblioteca, mas ela é item explícito dos entregáveis contratados. **Decisão da equipe/Diva antes do merge** — não é escolha técnica isolada;
- 🔴 Duas lacunas no DDL bloqueiam o `SupabaseChunkRepository` (frente de Dados & Infra);
- Piso de similaridade precisa de recalibração com embeddings reais;
- Golden set de avaliação ainda não existe (depende de casos reais da Solufarma).

---

## 2026-08-05 — Respostas do kickoff e primeiros workflows (Roger + Claude)


**O que foi feito:**
- Roger respondeu as pendências do kickoff: editais entrarão **via upload no frontend Streamlit** e ficarão no Supabase (ADR-003); conta Supabase já existe (chaves LLM virão depois); cronograma sem datas absolutas (ADR-004); nomes da equipe registrados em `EQUIPE.md` (Diva — gerente; Sparrow, Bia, Mosquitão);
- Criados os dois primeiros workflows WAT: `workflows/ingestao_documento.md` e `workflows/geracao_embeddings.md` (com tabelas de tools a implementar);
- Tabela de pendências do `PLANO_PROJETO.md` atualizada.

**Aprendizados / observações:**
- A ingestão via Streamlit antecipa parte da interface: uma versão mínima de upload precisa existir já na fase de dados (consequência registrada no ADR-003);
- Falta confirmar o GitHub dos integrantes e se algum apelido corresponde ao próprio Roger.

**Próximos passos:**
- Obter credenciais do Supabase existente e preencher `.env`;
- Habilitar pgvector e aplicar o DDL inicial (docs/ARQUITETURA.md §3);
- Implementar `tools/ingest_document.py` e `tools/extract_text.py` (podem começar antes das chaves LLM: upload, hash, triagem e extração nativa não dependem de LLM);
- Push do commit inicial (aguardando confirmação do Roger).

---

## 2026-08-04 — Setup inicial do projeto (Roger + Claude)


**O que foi feito:**
- Leitura e análise da proposta/timeline da ITA Júnior (PDF em `acesso/`);
- Criação da estrutura completa do repositório (docs, tools, workflows, Skills, .tmp);
- Documentos de registro criados: `PLANO_PROJETO.md`, `ARQUITETURA.md`, `DECISOES.md`, `EQUIPE.md` e este diário;
- `README.md`, `.gitignore`, `.env.example` e `requirements.txt` iniciais;
- Agente `ai-engineer` registrado em `.claude/agents/` e usado para redigir a arquitetura técnica;
- Skills de apoio criadas em `Skills/`;
- Repositório git inicializado e conectado a `https://github.com/RgNN988/Solufarma_Mod_2`.

**Aprendizados / observações:**
- O repositório remoto estava vazio — este commit é o marco zero do projeto;
- A pasta do projeto está dentro do OneDrive: atenção a possíveis conflitos de sincronização com o git (avaliar mover para fora do OneDrive se houver problemas).

**Próximos passos:**
- Resolver as pendências da tabela em `PLANO_PROJETO.md` (acervo, Supabase, chaves de API, papéis da equipe);
- Definir data oficial de início da semana 1;
- Montar ambiente Python e validar `requirements.txt`.
