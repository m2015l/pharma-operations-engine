# Plano do Projeto — Solufarma Módulo 2

> Fonte: proposta/timeline da ITA Júnior (`acesso/Timeline_Solufarma_ITAJunior (1).pdf`, datada de 21/07/26).
> Este documento é a versão viva do plano: atualize os checkboxes e datas conforme o trabalho avança.

## Objetivo

Desenvolver um **assistente de IA para validação de licitações** da Solufarma Engenharia, com arquitetura de dados robusta para ingestão, processamento e uso inteligente do acervo histórico de editais, atas e resultados. Respostas devem ser consistentes, contextualizadas, **rastreáveis** (com citação das fontes) e alinhadas ao histórico real de participações.

## Prazo e investimento

- **Prazo**: 12 semanas de desenvolvimento + 2 semanas de suporte;
- **Investimento**: R$ 17.000,00;
- **Custos de API (Claude/OpenAI) e nuvem**: responsabilidade da Solufarma.

## Escopo funcional

### 1. Criação e tratamento do banco de dados
- [ ] Configuração do banco em Supabase / PostgreSQL
- [ ] Ingestão do acervo histórico: editais, atas e resultados
- [ ] OCR em PDFs e documentos escaneados
- [ ] Classificação e sumarização dos documentos via IA
- [ ] Limpeza, padronização e estruturação dos dados

### 2. Base de conhecimento (RAG)
- [ ] Base vetorial para embeddings dos documentos
- [ ] Processamento e indexação de editais, atas e resultados
- [ ] Busca por similaridade semântica (por conceito, não só palavra-chave)
- [ ] Integração da base vetorial ao fluxo da IA
- [ ] Rastreabilidade com citação das fontes originais

### 3. Agente de IA
- [ ] Integração com APIs Claude (Anthropic) e/ou OpenAI
- [ ] Orquestração com LangChain
- [ ] Lógica de interpretação de solicitações sobre licitações
- [ ] Busca automatizada de projetos/equipamentos semelhantes no histórico
- [ ] Análise de novos editais contra o acervo validado
- [ ] Padronização das saídas conforme critérios de decisão da Solufarma

### 4. Engenharia de prompts
- [ ] Desenvolvimento e calibragem de prompts
- [ ] Estruturas de entrada/saída por tipo de consulta
- [ ] Controle de contexto e aderência ao domínio de licitações
- [ ] Ajustes iterativos com casos reais

### 5. Interface e handoff
- [ ] Aplicação web em Streamlit (foco desktop)
- [ ] Chat em linguagem natural com o agente
- [ ] Upload de novos editais para análise imediata
- [ ] Links para os documentos originais de cada resposta
- [ ] Testes, otimizações e treinamento da equipe Solufarma

## Cronograma detalhado

### Semanas 1–4 — Infraestrutura e Dados
- [x] Ambiente Python montado e validado (`pyproject.toml` + `uv`, 33 testes passando) — 07/08/26
- [ ] Configuração do banco Supabase *(pendente: credenciais)*
- [ ] Levantamento e organização do acervo histórico da Solufarma
- [ ] Rotinas de OCR para PDFs e documentos escaneados
  - [x] Detecção de formato por magic number, roteamento nativo/VLM, carry-over entre páginas, cache por hash, lote tolerante a falha, relatório de custo — 07/08/26
  - [ ] **Validação contra o documento real** *(bloqueado: o PDF do SENAI não está no repositório e falta a chave do OpenRouter)*
- [x] Chunking por regime de conteúdo (prosa / tabela / metadados) — 07/08/26
- [ ] Classificação, sumarização e tratamento dos documentos via IA
- [ ] Estruturação inicial da base e preparação para embeddings

**Resultado esperado**: documentos estáticos viram base estruturada, pesquisável e pronta para alimentar a IA.

> **Portão de qualidade (M2 — calibração):** os limiares de roteamento e chunking
> foram derivados de **um** documento e são hipótese. Antes de indexar qualquer
> coisa, rodar o relatório de calibração sobre 20 documentos variados. Indexar
> com limiar errado significa indexar lixo com confiança. Ver `BRIEFING.md`.

### Semanas 5–9 — Agente de IA e Vetorização
- [ ] Criação da base vetorial e geração dos embeddings
- [ ] Indexação de editais, atas e resultados históricos
- [ ] Pipeline de RAG com LangChain
- [ ] Integração com APIs Claude / OpenAI
- [ ] Lógica do agente e fluxos de entrada/saída
- [ ] Busca semântica e respostas com fontes citadas
- [ ] Engenharia de prompts: desenvolvimento, calibragem, iteração

**Resultado esperado**: o "cérebro" da Solufarma — inteligência consultável em linguagem natural.

### Semanas 10–12 — Interface, Validação e Handoff
- [ ] Aplicação web em Streamlit
- [ ] Chat e upload de novos editais
- [ ] Links para documentos originais em cada resposta
- [ ] Testes com cenários reais e otimização de performance
- [ ] Documentação técnica e treinamento da equipe

**Resultado esperado**: ferramenta pronta para uso diário, sem depender do dono para cada consulta.

### Semanas 13–14 — Suporte Pós-Entrega
- [ ] Acompanhamento do uso em operação real
- [ ] Correções e ajustes finos de prompts
- [ ] Suporte à consolidação da rotina de uso

## Entregáveis

1. Banco de dados estruturado em Supabase com acervo histórico tratado;
2. Base vetorial com editais, atas e resultados indexados;
3. Pipeline completo de RAG com LangChain;
4. Agente de IA funcional integrado às APIs Claude / OpenAI;
5. Backend de dados com scripts de OCR, ingestão e integração;
6. Aplicação web em Streamlit;
7. Prompts calibrados e documentados;
8. Documentação técnica completa e treinamento da equipe.

## Pendências / definições em aberto

| # | Pendência | Responsável | Status |
|---|-----------|-------------|--------|
| 1 | ~~Acesso ao acervo histórico~~ → editais chegam via upload no frontend Streamlit e ficam no Supabase (ver ADR-003) | — | ✅ Resolvido (05/08/26) |
| 2 | ~~Conta Supabase e credenciais~~ → `.env` preenchido e conexão validada contra o banco real (PostgreSQL 17.6, session pooler `sa-east-1`) | Equipe | ✅ Resolvido (09/08/26) |
| 3 | Chaves de API LLM → decidido usar **OpenRouter** (ADR-005); falta criar conta, carregar crédito (~US$ 25–30 cobre M1+M2) e preencher `OPENROUTER_API_KEY` no `.env` | Roger | ⏳ Aguardando |
| 4 | ~~Datas do cronograma~~ → decisão: não gerenciar por datas absolutas, apenas por fases/semanas relativas | — | ✅ Resolvido (05/08/26) |
| 5 | Critérios de decisão da Solufarma para padronizar saídas do agente | Cliente | ⏳ Aberto |
| 6 | ~~Nomes da equipe~~ → registrados em EQUIPE.md; falta confirmar GitHub de cada um e a divisão por frentes | Equipe | 🔶 Parcial |
| 7 | Push do commit inicial para o GitHub (repo remoto ainda vazio) | Roger | ⏳ Aguardando confirmação |
| 8 | **`SENAI_CETIQT_CAT_576640.pdf` em `data/brutos/`** — bloqueia todos os critérios de aceite do M1 e a troca das fixtures sintéticas por reais | Roger | 🔴 Bloqueante |
| 9 | Confirmar o slug do modelo em openrouter.ai/models e ajustar `OPENROUTER_MODELO` + preços no `.env` se divergir | Roger | ⏳ Aguardando |
| 10 | 20 documentos variados do Drive (edital, ata, certidão, memorial, planilha + um problemático) para o M2 | Roger / Solufarma | ⏳ Aberto |
| 11 | Modelo de embeddings (OpenAI × Voyage) — **deixado em aberto por decisão do Roger (09/08)**. Precisa fechar ANTES da primeira carga real: trocar depois obriga a recriar a coluna `vector(N)` e reprocessar tudo | Equipe | ⏳ Aberto |
| 12 | Piso de similaridade da busca (`SIMILARIDADE_MINIMA_PADRAO=0.15`) foi calibrado contra o provedor fake — recalibrar com embeddings reais | Frente RAG | ⏳ Depende do item 11 |
| 13 | **Golden set de avaliação do RAG não existe** — sem ele toda mudança de prompt/chunking é feita no escuro | Frente RAG ↔ Cliente | ⏳ Aberto |
| 14 | **Port de `src/solufarma_rag/` para dentro de `src/solufarma/`** (ADR-007): achatar subpacotes, Pydantic→dataclass, `Settings`→constantes, nomes em português | Frente RAG | 🔴 Em andamento |
| 15 | ~~Reconciliar acesso ao Supabase~~ → decisão do Roger: acesso por `DATABASE_URL` (psycopg direto), porque a REST não faz operador de vetor nem full-text com filtro. `DATABASE_URL` entrou em `VARIAVEIS_POR_ESTAGIO["indexacao"]` | Roger | ✅ Resolvido (09/08/26) |
| 16 | **Ponte chunking → Supabase** (cadastro do documento + tradução do `Chunk`) — especificada em [workflows/indexacao.md](../workflows/indexacao.md), não implementada | Frente RAG | 🔴 Bloqueia o M3 |
| 17 | Origem de `orgao`/`numero_edital`/`data`: usuário informa no upload ou LLM extrai da capa? Bloqueia o cadastro do documento | Roger ↔ Cliente | 🔴 Aberto |
