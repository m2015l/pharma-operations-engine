# Plano do Projeto — Solufarma Módulo 2

> Fonte: proposta/timeline da ITA Júnior (`acesso/Timeline_Solufarma_ITAJunior (1).pdf`, datada de 21/07/26).
> Este documento é a versão viva do plano: atualize os checkboxes e datas conforme o trabalho avança.

## Objetivo

Desenvolver um **assistente de IA para validação de licitações** da Solufarma Engenharia, com arquitetura de dados robusta para ingestão, processamento e uso inteligente do acervo histórico de editais, atas e resultados. Respostas devem ser consistentes, contextualizadas, **rastreáveis** (com citação das fontes) e alinhadas ao histórico real de participações.

## Onde o projeto está (11/08/26)

> **Construção adiantada, validação parada.** O encanamento completo existe e é testado:
> OCR, chunking, banco, vetores, busca híbrida, agente com citação, e as ferramentas de
> ponta a ponta. **99 testes automáticos passando** + 9 verificações contra o Supabase real.
>
> O que falta se divide em três:
> 1. **Construir** — a aplicação Streamlit (nenhuma linha) e a classificação/sumarização;
> 2. **Validar** — nada nunca rodou com IA de verdade nem com documento real; falta chave de API;
> 3. **Receber do cliente** — o acervo, os critérios de decisão e as perguntas-teste.
>
> Os itens marcados com *itálico* abaixo significam "código pronto, nunca rodou de verdade".

## Prazo e investimento

- **Prazo**: 12 semanas de desenvolvimento + 2 semanas de suporte;
- **Investimento**: R$ 17.000,00;
- **Custos de API (Claude/OpenAI) e nuvem**: responsabilidade da Solufarma.

## Escopo funcional

### 1. Criação e tratamento do banco de dados
- [x] Configuração do banco em Supabase / PostgreSQL
- [ ] Ingestão do acervo histórico: editais, atas e resultados — *ferramentas prontas (`upload_documento`, `cadastro`, `indexar`); **nenhum documento carregado***
- [ ] OCR em PDFs e documentos escaneados — *pipeline completo; **nunca rodou em documento real** (falta chave + acervo)*
- [ ] Classificação e sumarização dos documentos via IA — ❌ **não iniciado**
- [x] Limpeza, padronização e estruturação dos dados — remoção de boilerplate, costura entre páginas, chunking por regime

### 2. Base de conhecimento (RAG)
- [x] Base vetorial para embeddings dos documentos — `vector(1024)` + índice HNSW no Supabase
- [ ] Processamento e indexação de editais, atas e resultados — *pipeline incremental pronto e validado contra o banco real; **acervo vazio***
- [x] Busca por similaridade semântica (por conceito, não só palavra-chave) — híbrida (vetorial + léxica + RRF), validada contra o banco real
- [x] Integração da base vetorial ao fluxo da IA
- [x] Rastreabilidade com citação das fontes originais — com verificação de citação alucinada (`contrato_citacao_ok`)

### 3. Agente de IA
- [ ] Integração com APIs Claude (Anthropic) e/ou OpenAI — *cliente escrito; **nunca chamou a API** (falta chave)*
- [ ] Orquestração com LangChain
- [x] Lógica de interpretação de solicitações sobre licitações
- [x] Busca automatizada de projetos/equipamentos semelhantes no histórico
- [x] Análise de novos editais contra o acervo validado — fluxo `analise_edital`
- [ ] Padronização das saídas conforme critérios de decisão da Solufarma — 🔴 **os critérios nunca foram fornecidos** (pendência 5)

### 4. Engenharia de prompts
- [ ] Desenvolvimento e calibragem de prompts — *escritos; **calibragem depende de casos reais***
- [x] Estruturas de entrada/saída por tipo de consulta — `consulta_historico` e `analise_edital`
- [x] Controle de contexto e aderência ao domínio de licitações — o agente recusa responder fora do acervo
- [ ] Ajustes iterativos com casos reais

### 5. Interface e handoff
- [ ] Aplicação web em Streamlit (foco desktop) — ❌ **nenhuma linha escrita. É o maior item em aberto**
- [ ] Chat em linguagem natural com o agente
- [ ] Upload de novos editais para análise imediata
- [ ] Links para os documentos originais de cada resposta — *o dado já está guardado (Storage + `storage_path`); falta a tela*
- [ ] Testes, otimizações e treinamento da equipe Solufarma

## Cronograma detalhado

### Semanas 1–4 — Infraestrutura e Dados
- [x] Ambiente Python montado e validado (`pyproject.toml` + `uv`, 33 testes passando) — 07/08/26
- [x] Configuração do banco Supabase — schema aplicado no banco real, RLS ligado, repositório validado por smoke test — 09/08/26
- [ ] Levantamento e organização do acervo histórico da Solufarma
- [ ] Rotinas de OCR para PDFs e documentos escaneados
  - [x] Detecção de formato por magic number, roteamento nativo/VLM, carry-over entre páginas, cache por hash, lote tolerante a falha, relatório de custo — 07/08/26
  - [ ] **Validação contra o documento real** *(bloqueado: o PDF do SENAI não está no repositório e falta a chave do OpenRouter)*
- [x] Chunking por regime de conteúdo (prosa / tabela / metadados) — 07/08/26
- [ ] Classificação, sumarização e tratamento dos documentos via IA — ❌ **não iniciado**
- [x] Estruturação inicial da base e preparação para embeddings — schema, Storage, cadastro do documento e ponte chunking→banco — 11/08/26

**Resultado esperado**: documentos estáticos viram base estruturada, pesquisável e pronta para alimentar a IA.

> **Portão de qualidade (M2 — calibração):** os limiares de roteamento e chunking
> foram derivados de **um** documento e são hipótese. Antes de indexar qualquer
> coisa, rodar o relatório de calibração sobre 20 documentos variados. Indexar
> com limiar errado significa indexar lixo com confiança. Ver `BRIEFING.md`.

### Semanas 5–9 — Agente de IA e Vetorização
- [x] Criação da base vetorial e geração dos embeddings — pipeline incremental por hash, dois provedores (Voyage/OpenAI) com interruptor — 11/08/26
- [ ] Indexação de editais, atas e resultados históricos — *`tools/indexar.py` pronto; **depende do acervo e da chave***
- [x] Pipeline de RAG com LangChain — embeddings + retriever, na forma do **ADR-008** — 06/08/26
- [ ] Integração com APIs Claude / OpenAI — *código pronto; **nunca chamou a API***
- [x] Lógica do agente e fluxos de entrada/saída — interpretar → buscar → refinar → responder → citar
- [x] Busca semântica e respostas com fontes citadas — busca validada contra o banco real
- [ ] Engenharia de prompts: desenvolvimento, calibragem, iteração — *escritos; **calibragem e iteração dependem de casos reais***

**Resultado esperado**: o "cérebro" da Solufarma — inteligência consultável em linguagem natural.

### Semanas 10–12 — Interface, Validação e Handoff
- [ ] Aplicação web em Streamlit — ❌ **nenhuma linha. Maior frente de construção em aberto**
- [ ] Chat e upload de novos editais — ❌ existe por linha de comando (`tools/perguntar.py`), não por tela
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
| 7 | ~~Push do commit inicial~~ → repositório ativo, `main` sincronizada | Roger | ✅ Resolvido |
| 8 | ~~`SENAI_CETIQT_CAT_576640.pdf` em `data/brutos/`~~ → indexado e auditado desde 17/08; hoje o acervo tem 4 documentos (SENAI + 3 novos indexados em 28/09) | Roger | ✅ Resolvido |
| 9 | Confirmar o slug do modelo em openrouter.ai/models e ajustar `OPENROUTER_MODELO` + preços no `.env` se divergir | Roger | ⏳ Aguardando |
| 10 | 20+ documentos variados do Drive para o M2 → Roger enviou 31. **10 indexados** (3 em 28/09 + 7 com texto nativo em 29/09, sem OCR). Os outros precisam de OCR (~US$ 12–18 no total, adiado por decisão do Roger) ou estão ilegíveis. ~~Falta 1 arquivo (SS WHITE)~~: em 07/10 o PDF está em `data/brutos/` e o conteúdo confere. **Situação em 08/10: 32 de 33 indexados.** Falta só o HC USP: OCR pausado com ~109 de 294 páginas no cache; retomar com `tools/extract_text.py` (~US$ 4,50) | Roger / Solufarma | 🔶 Parcial — 32/33 (08/10/26) |
| 11 | ~~Modelo de embeddings~~ → **Voyage** (`voyage-4-large-1024`) em produção desde 28/09: rate limit liberou minutos após o cartão ser cadastrado, acervo reembeddado (162 chunks), piso recalibrado (`SIMILARIDADE_MINIMA=0.4472` via `tools/avaliar.py --calibrar`). Golden set: 11/11 recall + 4/4 controles negativos — melhor resultado que o medido com OpenAI | Roger | ✅ Resolvido (28/09/26) |
| 12 | Piso de similaridade — calibrado em 28/09 (**0.4472**) com 1 documento. Em 29/09 o acervo foi para 11 documentos: recall do golden set segue 11/11, mas 1 dos 4 controles negativos perdeu validade (o acervo agora tem manutenção predial e ISO 7 de verdade). **Rever os controles negativos e recalibrar** | Frente RAG | 🔶 Parcial — recalibrar (29/09/26) |
| 13 | ~~Golden set de avaliação~~ → criado em 28/09: `data/golden_set.json`, 15 casos (11 positivos + 4 controles negativos), páginas verificadas direto contra o texto indexado. Recall 100% (11/11) medido com `tools/avaliar.py` | Frente RAG | ✅ Resolvido (28/09/26) |
| 14 | **Port de `src/solufarma_rag/` para dentro de `src/solufarma/`** (ADR-007): achatar subpacotes, Pydantic→dataclass, `Settings`→constantes, nomes em português | Frente RAG | 🔴 Em andamento |
| 15 | ~~Reconciliar acesso ao Supabase~~ → decisão do Roger: acesso por `DATABASE_URL` (psycopg direto), porque a REST não faz operador de vetor nem full-text com filtro. `DATABASE_URL` entrou em `VARIAVEIS_POR_ESTAGIO["indexacao"]` | Roger | ✅ Resolvido (09/08/26) |
| 16 | ~~Ponte chunking → Supabase~~ → implementada pelo Thiago em 11/08: `ingestion/cadastro.py`, `ingestion/traducao.py`, `tools/indexar.py`, `tools/upload_documento.py` | Thiago | ✅ Resolvido (11/08/26) |
| 17 | Origem de `orgao`/`numero_edital`/`data`: usuário informa no upload ou LLM extrai da capa? **Não bloqueia mais** — `cadastrar_documento()` recebe os três por parâmetro, agnóstico à origem. Vira decisão de produto na tela de upload | Roger ↔ Cliente | 🔶 Não bloqueante |
| 18 | ~~Aplicação Streamlit~~ → trocada por **frontend Next.js + API FastAPI** (29/09). v1 funcionando em modo demo; redesign no padrão visual da Solufarma e exportação .docx especificados em `frontend/PLANO_V2.md`. Falta ADR da troca e avisar a Diva | Frente Interface | 🔶 Em andamento (29/09/26) |
| 19 | **Classificação e sumarização dos documentos via IA** (escopo 1) — não iniciado | Frente Dados | 🔴 Aberto |
| 20 | Ferramentas novas (`indexar`, `perguntar`, `avaliar`, `upload_documento`, `cadastro`, `traducao`) **não têm testes automáticos** | Frente RAG | ⏳ Aberto |
| 21 | ~~Aplicar as instruções do `PRECISÃO.md`~~ → as 10 aplicadas e **mescladas em `main` e publicadas no GitHub em 28/09** (commit `4d36a38`). Testes: 114/114 passando | Frente RAG | ✅ Resolvido (28/09/26) |
| 22 | ~~Recusas falsas~~ → I1/I2/I3 corrigem a causa (filtros zerando busca + linguagem de recusa). Verificado ao vivo: turnos 1.2, 1.3, 2.4, 3.3 reconfirmados corretos; 1.4/2.1/4.3 dependem do mesmo mecanismo mas não testados individualmente | Frente RAG | ✅ Resolvido (28/09/26) |
| 23 | ~~`itens_planilha` não é consultada~~ → I9 implementada e ligada ao CLI (`tools/perguntar.py`), verificada contra o Supabase real: pergunta de gases especiais agora cita 144+167+28 conjuntos da planilha, p.45 | Frente RAG | ✅ Resolvido (28/09/26) |
| 24 | ~~Sem memória de conversa~~ → I8 implementada e **confirmada com chamada paga real em 28/09** (auditoria do lote 2): dois pronomes soltos resolvidos corretamente, sem vazar entre sessões | Frente RAG / Interface | ✅ Resolvido (28/09/26) |
| 25 | **Refazer a bateria de 20 turnos após as mudanças** — 4 turnos graves já reconfirmados individualmente (item 22), mas a bateria completa de 20 turnos com o workflow de dois agentes não foi refeita. Transcrição base em `docs/auditorias/2026-08-17_conversas_rag.md` | Frente RAG | ⏳ Aberto |
| 26 | **Vínculo TEP vs. Solufarma nos 3 documentos novos** — os atestados são da TEP (Tecnologia em Projetos de Engenharia), não da Solufarma; "Solufarma" não aparece em nenhum dos 9 chunks. Decisão do Roger (28/09): tratar por ora como consulta interna, não como base de comprovação de capacidade técnica. Se isso mudar, precisa de campo explícito de vínculo no cadastro | Roger | 🔶 Premissa assumida, não fechada |
| 27 | ~~Confiabilidade dos nomes de arquivo~~ → **resolvido o diagnóstico**: em ordem alfabética, o conteúdo de cada arquivo é o documento com o nome do arquivo anterior (18 casos bateram pelo nº da CAT, 0 contradições). `tools/triar_documentos.py` confere nome × conteúdo sem custo; passo 0 no `workflows/indexacao.md` | Frente RAG | ✅ Resolvido (29/09/26) |
| 28 | ~~Generalizar a folha de rosto sem heading (P6/I6)~~ → `_rotulo_secao_prosa` em `src/solufarma/chunking.py` (lista fechada de rótulos de CAT/atestado). Calibrado só com CATs: **editais e atas nunca passaram por ela** | Frente RAG | ✅ Resolvido (29/09/26) |
| 29 | ~~Bug do `--titulo` no `indexar.py`~~ → título vai para o cabeçalho dos chunks via `chunk_document.py --titulo`; o `indexar.py` recusa título divergente. Resta: `indexar.py` grava `metodo_extracao="vlm"` fixo, mesmo para documento nativo | Frente RAG | ✅ Resolvido (29/09/26) |
| 30 | **Lacunas de carimbo não são marcadas para revisão** — no LAQFA/CEMFAR o OCR avisou que carimbos cobrem valores (págs. 17, 20, 21, 25, 34, 36, 38; ex.: item 04.01.521.ac), mas `chunking.classificar_lacuna()` gravou essas linhas como `vazio`, não `ilegivel`. Dos 5 documentos de 07/10, só o Butantan hemoderivados teve linhas sinalizadas (9). Efeito: `tools/relatorio_lacunas.py` não lista essas lacunas e uma soma de quantidades sai menor sem erro. Ajustar o classificador e rechunkar/reindexar os documentos afetados | Frente Dados | 🔴 Aberto (07/10/26) |
| 31 | **Documento preso em `chunked` por chunk de ruído** — `gerar_embeddings_pendentes` pula chunk só com título, mas ele segue contando como pendente; o documento nunca vira `indexado` e o Acervo mostra "Em processamento". Contornado à mão em 3 documentos (07/10). Corrigir em `ingestion/embeddings.py` ou no chunker | Frente RAG | 🔴 Aberto (07/10/26) |
| 32 | **OCR antiga embutida passa por texto nativo** — o roteamento aceita a camada de OCR antiga do PDF como texto bom (SS WHITE: "Copplo", "municiplo"). 8 dos 9 PDFs que faltavam em 07/10 têm essa camada. Avaliar forçar o VLM nessas páginas | Frente Dados | 🔴 Aberto (07/10/26) |
| 33 | **Resposta do VLM cortada no teto de 8.000 tokens** (pág. 35 do Cristália 2620210005534): página salva incompleta e em JSON cru. Verificar se o cache guarda a resposta ruim, subir o teto ou dividir a página, e refazer | Frente Dados | 🔴 Aberto (07/10/26) |
| 34 | Classificação por IA dos 5 documentos de 07/10 (executante/disciplina, ~US$ 0,03) e perguntas sobre eles no golden set; chunk 1 do Hangar Anápolis com ~3.800 tokens (págs. 1–3 numa tabela só) | Frente RAG | ⏳ Aberto (07/10/26) |
