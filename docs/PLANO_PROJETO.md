# Plano do Projeto — Pharma Operations Platform · Enterprise Vendor Hub

> Este documento é a versão viva do plano: atualize os checkboxes e marcos conforme o trabalho avança.

## Objetivo

Desenvolver um **assistente de IA para validação de licitações e acervo técnico** da Pharma Operations Platform (Enterprise Vendor Hub), com arquitetura de dados robusta para ingestão, processamento e uso inteligente do acervo histórico de atestados de capacidade técnica, CATs e editais. Respostas devem ser consistentes, contextualizadas, **rastreáveis** (com citação das fontes) e alinhadas ao histórico real de participações.

## Estado atual da arquitetura

> **Pipeline ponta a ponta operacional.** O encanamento completo existe e é testado:
> OCR, chunking, banco, vetores, busca híbrida, reranking, agente com citação, API FastAPI, frontend Next.js e as ferramentas de
> ponta a ponta.

## Prazo e escopo de fases

- **Ciclo**: 12 semanas de desenvolvimento + 2 semanas de suporte operacional;
- **Custos de API (Claude/OpenAI/Voyage) e nuvem**: monitorados por lote e por consulta.

## Escopo funcional

### 1. Criação e tratamento do banco de dados
- [x] Configuração do banco em Supabase / PostgreSQL
- [x] Ingestão do acervo histórico: atestados e CATs (`upload_documento`, `cadastro`, `indexar`)
- [x] OCR em PDFs e documentos escaneados
- [x] Classificação dos documentos via IA (`documentos.classificacao`)
- [x] Limpeza, padronização e estruturação dos dados — remoção de boilerplate, costura entre páginas, chunking por regime

### 2. Base de conhecimento (RAG)
- [x] Base vetorial para embeddings dos documentos — `vector(1024)` + índice HNSW no Supabase
- [x] Processamento e indexação do acervo técnico — pipeline incremental validado contra o banco real
- [x] Busca por similaridade semântica (por conceito, não só palavra-chave) — híbrida (vetorial + léxica + RRF) + reranker Voyage
- [x] Integração da base vetorial ao fluxo da IA
- [x] Rastreabilidade com citação das fontes originais — com verificação de citação alucinada (`contrato_citacao_ok`)

### 3. Agente de IA
- [x] Integração com APIs Claude (Anthropic) / OpenRouter e Voyage
- [x] Orquestração de RAG com LangChain (ADR-008)
- [x] Lógica de interpretação de solicitações sobre licitações
- [x] Busca automatizada de projetos/equipamentos semelhantes no histórico
- [x] Análise de novos editais contra o acervo validado — fluxo `analise_edital`
- [x] Padronização das saídas conforme critérios de rastreabilidade técnica

### 4. Engenharia de prompts
- [x] Desenvolvimento e calibragem de prompts
- [x] Estruturas de entrada/saída por tipo de consulta — `consulta_historico` e `analise_edital`
- [x] Controle de contexto e aderência ao domínio de licitações — o agente recusa responder fora do acervo
- [x] Ajustes iterativos com casos reais (`PRECISÃO.md`)

### 5. Interface e handoff
- [x] Aplicação web em Next.js + API FastAPI (foco desktop)
- [x] Chat em linguagem natural com o agente e memória de conversa
- [x] Upload de novos documentos com acompanhamento de progresso
- [x] Links assinados e visualizador pdf.js para os documentos originais de cada resposta
- [x] Exportação de conversas e respostas isoladas para Word (`.docx`)

## Cronograma detalhado

### Semanas 1–4 — Infraestrutura e Dados
- [x] Ambiente Python montado e validado (`pyproject.toml` + `uv`) — 07/08/26
- [x] Configuração do banco Supabase — schema aplicado no banco real, RLS ligado, repositório validado por smoke test — 09/08/26
- [x] Levantamento e triagem do acervo histórico da Pharma Operations Platform
- [x] Rotinas de OCR para PDFs e documentos escaneados
  - [x] Detecção de formato por magic number, roteamento nativo/VLM, carry-over entre páginas, cache por hash, lote tolerante a falha, relatório de custo — 07/08/26
  - [x] Validação contra documentos reais do acervo
- [x] Chunking por regime de conteúdo (prosa / tabela / metadados) — 07/08/26
- [x] Classificação estruturada dos documentos via IA — 29/09/26
- [x] Estruturação inicial da base e preparação para embeddings — schema, Storage, cadastro do documento e ponte chunking→banco — 11/08/26

**Resultado esperado**: documentos estáticos viram base estruturada, pesquisável e pronta para alimentar a IA.

### Semanas 5–9 — Agente de IA e Vetorização
- [x] Criação da base vetorial e geração dos embeddings — pipeline incremental por hash, dois provedores (Voyage/OpenAI) com interruptor — 11/08/26
- [x] Indexação de atestados e CATs históricos (`tools/indexar.py`)
- [x] Pipeline de RAG com LangChain — embeddings + retriever, na forma do **ADR-008** — 06/08/26
- [x] Integração com APIs Claude / OpenRouter / Voyage
- [x] Lógica do agente e fluxos de entrada/saída — interpretar → buscar → refinar → responder → citar
- [x] Busca semântica e respostas com fontes citadas — busca validada contra o banco real
- [x] Engenharia de prompts: desenvolvimento, calibragem, iteração (`PRECISÃO.md`)

**Resultado esperado**: inteligência operacional consultável em linguagem natural.

### Semanas 10–12 — Interface, Validação e Handoff
- [x] Aplicação web em Next.js + FastAPI
- [x] Chat e upload de novos documentos
- [x] Links para documentos originais em cada resposta
- [x] Testes com cenários reais e otimização de performance (Golden Set 22/22)
- [x] Documentação técnica da plataforma

**Resultado esperado**: ferramenta pronta para uso diário.

### Semanas 13–14 — Suporte Pós-Entrega
- [ ] Acompanhamento do uso em operação real
- [ ] Correções e ajustes finos de prompts
- [ ] Suporte à consolidação da rotina de uso

## Entregáveis

1. Banco de dados estruturado em Supabase com acervo histórico tratado;
2. Base vetorial com atestados e CATs indexados;
3. Pipeline completo de RAG com LangChain;
4. Agente de IA funcional integrado às APIs de LLM e embeddings;
5. Backend de dados com scripts de OCR, ingestão e integração;
6. Aplicação web (Next.js + FastAPI);
7. Prompts calibrados e documentados;
8. Documentação técnica completa.

## Registro de Pendências e Definições

| # | Pendência | Responsável | Status |
|---|-----------|-------------|--------|
| 1 | ~~Acesso ao acervo histórico~~ → documentos chegam via upload no frontend ou CLI e ficam no Supabase (ver ADR-003) | — | ✅ Resolvido (05/08/26) |
| 2 | ~~Conta Supabase e credenciais~~ → `.env` configurado e conexão validada contra o banco real (PostgreSQL 17.6, session pooler `sa-east-1`) | Equipe | ✅ Resolvido (09/08/26) |
| 3 | ~~Chaves de API LLM~~ → decidido usar **OpenRouter** (ADR-005) | Equipe | ✅ Resolvido |
| 4 | ~~Datas do cronograma~~ → decisão: não gerenciar por datas absolutas, apenas por fases/semanas relativas | — | ✅ Resolvido (05/08/26) |
| 5 | Critérios adicionais de decisão para padronizar saídas do agente | Produto | ⏳ Aberto |
| 6 | ~~Estrutura da equipe~~ → registrada em EQUIPE.md | Equipe | ✅ Resolvido |
| 7 | ~~Push do commit inicial~~ → repositório ativo, `main` sincronizada | Equipe | ✅ Resolvido |
| 8 | ~~`INSTITUTO_BIOPHARMA_CAT_100200.pdf` em `data/brutos/`~~ → indexado e auditado desde 17/08 | Equipe | ✅ Resolvido |
| 9 | ~~Confirmar o slug do modelo em openrouter.ai/models e ajustar `OPENROUTER_MODELO` + preços no `.env`~~ | Equipe | ✅ Resolvido |
| 10 | ~~Lote completo de documentos para o M2~~ → **Situação em 08/10: os 33 PDFs estão indexados** (2.487 chunks, golden set 22/22 e controles 4/4) | Equipe | ✅ Resolvido — 33/33 (08/10/26) |
| 11 | ~~Modelo de embeddings~~ → **Voyage** (`voyage-4-large-1024`) em produção desde 28/09, piso recalibrado (`SIMILARIDADE_MINIMA=0.4472` via `tools/avaliar.py --calibrar`). Golden set: 100% recall + 4/4 controles negativos | Equipe | ✅ Resolvido (28/09/26) |
| 12 | ~~Piso de similaridade~~ — recalibrado com o acervo expandido e reranker Voyage (ADR-011) | Frente RAG | ✅ Resolvido |
| 13 | ~~Golden set de avaliação~~ → criado em 28/09: `data/golden_set.json`, páginas verificadas direto contra o texto indexado. Recall 100% medido com `tools/avaliar.py` | Frente RAG | ✅ Resolvido (28/09/26) |
| 14 | Consolidação de `src/pharma_rag/` e `src/pharma_ops/` (ADR-007) | Frente RAG | 🔶 Em evolução |
| 15 | ~~Reconciliar acesso ao Supabase~~ → acesso por `DATABASE_URL` (psycopg direto), porque a REST não faz operador de vetor nem full-text com filtro. `DATABASE_URL` entrou em `VARIAVEIS_POR_ESTAGIO["indexacao"]` | Equipe | ✅ Resolvido (09/08/26) |
| 16 | ~~Ponte chunking → Supabase~~ → implementada em 11/08: `ingestion/cadastro.py`, `ingestion/traducao.py`, `tools/indexar.py`, `tools/upload_documento.py` | Frente RAG | ✅ Resolvido (11/08/26) |
| 17 | Origem de `orgao`/`numero_edital`/`data`: `cadastrar_documento()` recebe os três por parâmetro, agnóstico à origem | Produto | 🔶 Não bloqueante |
| 18 | ~~Interface web~~ → implementada com **frontend Next.js + API FastAPI** (29/09), padrão visual corporativo e exportação `.docx` (`frontend/PLANO_V2.md`) | Frente Interface | ✅ Resolvido (29/09/26) |
| 19 | ~~Classificação dos documentos via IA~~ → implementada (ADR-010) | Frente Dados | ✅ Resolvido (29/09/26) |
| 20 | Ampliar cobertura de testes unitários de CLIs (`indexar`, `perguntar`, `avaliar`) | Frente RAG | ⏳ Aberto |
| 21 | ~~Aplicar as instruções do `PRECISÃO.md`~~ → as 10 aplicadas e mescladas em `main` em 28/09. Testes passando | Frente RAG | ✅ Resolvido (28/09/26) |
| 22 | ~~Recusas falsas~~ → I1/I2/I3 corrigem a causa (filtros zerando busca + linguagem de recusa). Verificado ao vivo | Frente RAG | ✅ Resolvido (28/09/26) |
| 23 | ~~`itens_planilha` não é consultada~~ → I9 implementada e ligada ao CLI (`tools/perguntar.py`), verificada contra o Supabase real | Frente RAG | ✅ Resolvido (28/09/26) |
| 24 | ~~Sem memória de conversa~~ → I8 implementada e confirmada em 28/09: pronomes soltos resolvidos corretamente, sem vazar entre sessões | Frente RAG / Interface | ✅ Resolvido (28/09/26) |
| 25 | **Refazer a bateria completa de 20 turnos após as mudanças** — 4 turnos graves já reconfirmados individualmente (item 22) | Frente RAG | ⏳ Aberto |
| 26 | **Vínculo de executante (`principal` vs. `coligada`) nos documentos do acervo** — distinção entre atestados da Pharma Operations Platform (principal) e da coligada (Enterprise Vendor Hub), tratada via classificação estruturada (ADR-010) | Produto | ✅ Resolvido (29/09/26) |
| 27 | ~~Confiabilidade dos nomes de arquivo~~ → `tools/triar_documentos.py` confere nome × conteúdo sem custo; passo 0 no `workflows/indexacao.md` | Frente RAG | ✅ Resolvido (29/09/26) |
| 28 | ~~Generalizar a folha de rosto sem heading (P6/I6)~~ → `_rotulo_secao_prosa` em `src/pharma_ops/chunking.py` (lista fechada de rótulos de CAT/atestado) | Frente RAG | ✅ Resolvido (29/09/26) |
| 29 | ~~Bug do `--titulo` no `indexar.py`~~ → título vai para o cabeçalho dos chunks via `chunk_document.py --titulo`; o `indexar.py` recusa título divergente | Frente RAG | ✅ Resolvido (29/09/26) |
| 30 | ~~Lacunas de carimbo não são marcadas para revisão~~ → corrigido em 09/10 em `chunking.py` (código com sufixo de letras, frase partida em abreviação, marcadores novos; linha preenchida com valor inferido vira `suspeita`) | Frente Dados | ✅ Resolvido (09/10/26) |
| 31 | ~~Documento preso em `chunked` por chunk de ruído~~ → corrigido em 09/10: ruído não conta como pendência em `gerar_embeddings_pendentes` | Frente RAG | ✅ Resolvido (09/10/26) |
| 32 | **OCR antiga embutida passa por texto nativo** → corrigido em 09/10 para documentos novos: folha escaneada (imagem cobrindo 85% ou mais da página) vai para o VLM mesmo com texto (`PHARMA_OPS_OCR_EMBUTIDO_VLM`) | Frente Dados | ✅ Resolvido (09/10/26) |
| 33 | ~~Resposta do VLM cortada no teto de 8.000 tokens~~ → corrigido em 09/10: `chamar_vlm` repete a chamada (até 2 vezes) e nunca grava no cache a resposta cortada ou fora do formato | Frente Dados | ✅ Resolvido (09/10/26) |
| 34 | ~~Classificação por IA dos documentos novos~~ → os 33 documentos do acervo estão classificados (`principal`, `consorcio`, `coligada`) | Frente RAG | ✅ Resolvido (08/10/26) |
