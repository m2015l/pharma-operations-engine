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
- [ ] Orquestração do agente — grafo em Python puro por decisão da ADR-005 (opção B); LangChain fica no pipeline de RAG, não na orquestração
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
- [ ] Configuração do ambiente de dados, repositórios e banco Supabase
- [ ] Levantamento e organização do acervo histórico da Solufarma
- [ ] Rotinas de OCR para PDFs e documentos escaneados
- [ ] Classificação, sumarização e tratamento dos documentos via IA
- [ ] Estruturação inicial da base e preparação para embeddings

**Resultado esperado**: documentos estáticos viram base estruturada, pesquisável e pronta para alimentar a IA.

### Semanas 5–9 — Agente de IA e Vetorização
- [ ] Criação da base vetorial e geração dos embeddings
- [ ] Indexação de editais, atas e resultados históricos
- [ ] Pipeline de RAG com LangChain (embeddings feitos; falta o vector store — ADR-005)
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
| 2 | ~~Conta Supabase~~ → conta existe e Roger tem acesso ao painel; falta só a senha do banco (item 13) | Equipe | 🔶 Parcial |
| 3 | Chaves de API LLM (Claude / OpenAI) — serão providenciadas mais tarde | Cliente ↔ Equipe | ⏳ Aguardando |
| 4 | ~~Datas do cronograma~~ → decisão: não gerenciar por datas absolutas, apenas por fases/semanas relativas | — | ✅ Resolvido (05/08/26) |
| 5 | Critérios de decisão da Solufarma para padronizar saídas do agente | Cliente | ⏳ Aberto |
| 6 | ~~Nomes da equipe~~ → registrados em EQUIPE.md; falta confirmar GitHub de cada um e a divisão por frentes | Equipe | 🔶 Parcial |
| 7 | ~~Push do commit inicial~~ | Roger | ✅ Resolvido |
| 8 | ~~**LangChain ausente do código**~~ → decisão pela **opção B** da ADR-005: LangChain no pipeline de RAG (embeddings já implementados), Python puro no grafo do agente. Falta comunicar à Diva e fechar o vector store quando o Supabase existir | Roger ↔ Diva | ✅ Resolvido (06/08/26) |
| 9 | ~~`doc_chunks` sem `content_hash`~~ → resolvido em `001_schema_inicial.sql`: entraram `content_hash` **e** `embedding_content_hash` | Frente RAG | ✅ Resolvido (06/08/26) |
| 10 | ~~`orgao`/`data` no `Chunk` mas só em `licitacoes` no DDL~~ → decisão: mantidos em `licitacoes`, acessados por JOIN, sem duplicar escrita | Frente RAG | ✅ Resolvido (06/08/26) |
| 13 | **Senha do banco Supabase** para montar a `DATABASE_URL` — sem ela nada roda contra o banco real | Diva → Roger | 🔴 Bloqueante |
| 11 | Piso de similaridade da busca (`SIMILARIDADE_MINIMA_PADRAO=0.15`) calibrado contra provedor fake — recalibrar com embeddings reais | Frente RAG | ⏳ Semana de vetorização |
| 12 | Golden set de avaliação do RAG não existe (a skill pede "desde o início") — depende de casos reais da Solufarma | Frente RAG ↔ Cliente | ⏳ Aberto |
