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

---
