# Diário de Bordo — Solufarma Módulo 2

> Registro cronológico do trabalho. Cada sessão de trabalho relevante ganha uma entrada no topo (mais recente primeiro).
> Formato: data, quem trabalhou, o que foi feito, o que aprendemos, próximos passos.
> **Frontend:** a partir de 29/09 o trabalho de interface é registrado em `docs/DIARIO_DE_BORDO_FRONTEND.md` (o Streamlit foi trocado por um frontend Next.js próprio).

---

## 2026-09-29 (tarde) — Hipótese dos nomes confirmada; 7 documentos nativos indexados sem OCR (Roger + Claude)

**Decisões do Roger:** indexar só o que tem texto nativo (sem gastar com OCR agora), testar a hipótese dos nomes, adicionar o passo 0 no workflow, fazer push.

**Hipótese dos nomes trocados: confirmada.** Com os 32 PDFs em ordem alfabética, o conteúdo de cada arquivo é o documento que tem o nome do arquivo **anterior**. Bateu por nº de CAT em 18 casos e por órgão/objeto em mais 6, com **0 contradições**. Consequências:
- o documento "SS WHITE CAT 11686-2010 (injetáveis)" **não está em nenhum arquivo** do lote, e o conteúdo "Ariston" do primeiro arquivo (ordem alfabética) aponta para um arquivo que falta antes dele. Pedir à empresa o arquivo que falta;
- dá para renomear o lote inteiro de forma determinística. Por segurança os arquivos em `data/` **não foram mexidos**: os indexados foram **copiados** para `data/brutos/` com o nome certo + sufixo `[conteudo real]`.

**Indexados (7 documentos, 102 chunks, custo US$ 0 de OCR; embeddings Voyage ~59K tokens, dentro da cota gratuita):**

| Documento (título pelo conteúdo) | Órgão | Executante | Chunks |
|---|---|---|---:|
| Vestiários de produção do prédio 10 do CTM - Farmanguinhos | FIOCRUZ | **Solufarma** | 47 |
| Câmara Fria para Imunobiológicos (CAT SJC-01975) | Instituto Butantan | TEP | 3 |
| Trocadores de Calor PW/WFI (CAT SJC-02085) | Instituto Butantan | TEP | 2 |
| Controle e Instrumentação ISO 7 / Câmara Fria (CAT SJC-03608) | Instituto Butantan | TEP | 11 |
| Prédio IMAS II - Instalações Elétricas (CAT 2620130007911) | CNPEM | TEP | 28 |
| Manutenção Predial da Planta Industrial (CAT 2620130009521) | Instituto Terapêutico Delta | TEP | 6 |
| Manutenção de Ar Condicionado e Água Purificada (CAT 2620140004961) | FURP | TEP | 5 |

- Extração com o VLM **bloqueado por código** (`chamar_vlm` substituído por uma função que levanta erro): 96 páginas, todas nativas, 0 via VLM;
- **Ficou de fora** o 8º nativo (arquivo "BUTANTAN 0000000238897", conteúdo = "BUNKER SJC-01555"): OCR antigo ilegível, sem contratante identificável;
- **Banco agora:** 11 documentos, 272 chunks, 0 pendentes de embedding. É o primeiro atestado com a **Solufarma como executante** no acervo (o dos vestiários).

**Golden set (só busca):** recall **11/11**; controles negativos **3/4**. O que "falha" ("este atestado cobre manutenção predial… sala limpa ISO 7?") foi escrito quando o acervo era só o SENAI. Hoje o acervo tem manutenção predial e ISO 7 de verdade, então o controle perdeu a validade. Não é regressão: rever o golden set junto com a recalibração do piso (item 12).

**Workflow:** `workflows/indexacao.md` ganhou o "Passo 0: triagem pelo conteúdo" (autorizado pelo Roger).

**Observação:** `tools/indexar.py` grava `ocr_aplicado=True, metodo_extracao="vlm"` fixo, o que está errado para esses 7 documentos (foram nativos). Menor, mas vale corrigir quando mexer no CLI.

**Próximos passos:**
1. Pedir à Solufarma o arquivo que falta (SS WHITE 11686-2010) e confirmar a leitura dos nomes;
2. OCR dos parciais quando houver orçamento: 8 documentos precisam de só 1 página de OCR cada (~US$ 0,02 cada), o resto está concentrado em HIPOLABOR/HC USP/Butantan 2620120006270;
3. Rever os controles negativos do golden set e recalibrar o piso;
4. Os 3 documentos de 28/09 foram chunkados com o chunker antigo; reindexá-los com a heurística nova é barato (só embeddings), exceto o SENAI (patch manual do I6).

---

## 2026-09-29 — Folha de rosto generalizada em código; título pelo conteúdo; triagem dos 32 PDFs (Roger + Claude)

**Como foi feito:** duas sessões paralelas em worktrees (branches `worktree-agent-a441020e4488a086a` e `worktree-agent-a61e0e7f71a529ec4`), mescladas em `main` pelo orquestrador. Nenhuma chamada paga, nada escrito no Supabase, nada reindexado. **173 testes passando** (eram 114).

**O que entrou:**
- **Item 28 — heurística I6/P6 em código** (`src/solufarma/chunking.py::_rotulo_secao_prosa`): linha de prosa vira seção se for o rótulo inteiro, em caixa alta, ≤ 60 caracteres e casar com uma **lista fechada** (DADOS DO…, ATIVIDADE TÉCNICA REALIZADA, ENDEREÇO DA OBRA/SERVIÇO, DESCRIÇÃO, OBSERVAÇÕES, OBJETO, ESCOPO DOS SERVIÇOS…). Lista fechada e não "qualquer caixa alta" porque, nas CATs, quase toda linha solta em caixa alta é nome, cargo ou cidade. CONTRATANTE/CONTRATADA/RESPONSÁVEL TÉCNICO ficaram de fora de propósito (são legenda de assinatura). Na CAT do SENAI dispara exatamente nos 7 rótulos do patch manual do I6 e em nenhuma outra das 2.591 linhas; nos 3 documentos novos, chunks sem seção ganharam seção e faixas de página mais precisas;
- **Título do documento não vem mais do nome do arquivo:** `chunkar_documento(doc, titulo=None)`; `tools/chunk_document.py --titulo`; `tools/indexar.py` usa o título gravado nos chunks e **recusa** (saída 2) um `--titulo` divergente, mostrando o comando para refazer os chunks (grátis). Fecha o bug de 28/09;
- **Triagem pelo conteúdo** — `tools/triar_documentos.py` (lógica em `src/solufarma/triagem.py`), só regex, sem LLM: tipo, nº CAT, contratante/CNPJ, **executante**, responsável técnico, objeto, nativo vs. precisa OCR, nome do arquivo bate ou não, duplicatas. Saída em `.tmp/triagem_documentos.{json,md}`.

**Resultado da triagem (32 PDFs: 29 soltos em `data/` + 3 de `data/brutos/`):**
- Texto: 11 nativos, 18 mistos, 3 totalmente escaneados (FURP 2620140004961, LAQFA 522936, SANTA CASA). Em 28 o "texto" é OCR antigo embutido, com bastante ruído;
- Nome do arquivo vs. conteúdo: **19 trocados**, 4 batem (fraco — só o órgão), 7 inconclusivos, 2 sem texto. Os 3 já conferidos em 28/09 foram confirmados pela ferramenta;
- **A troca parece sistemática:** o conteúdo de um arquivo costuma ser o documento com o nome de *outro* arquivo do lote (ex. arquivo SS WHITE = CAT 576640 do SENAI; arquivo SENAI = CAT da Santa Casa). Hipótese não testada: dá para corrigir por mapeamento;
- Executante: TEP 21, **Solufarma 5**, consórcio com TEP 2, outra 1, não encontrado 3;
- **Revisar descarte de 28/09:** o arquivo "BUTANTAN SJC-02542" contém a CAT SJC-02085 (trocadores de calor) e o arquivo "SJC-02085" contém outra CAT (câmara fria) — aparentemente não era duplicata. O arquivo "SS WHITE" é muito provavelmente o SENAI já indexado (mesma chave de autenticação);
- **OCR estimado:** 768 páginas, ~US$ 12 a 18 (estimativa, não medição). Concentrado em HIPOLABOR (294 p.), HC USP (137), Butantan 2620120006270 (76), FURP (63), SS WHITE (58), DELTA 216058 (48). O `.env` ainda está com o preço promocional que acabou em 31/08.

**Limitações conhecidas:**
- A lista de rótulos foi calibrada com 4 CATs; editais e atas nunca passaram por ela. Rótulos em caixa mista não disparam; "OBJETO"/"OBSERVAÇÕES" soltos no meio de edital podem abrir subseção indevida;
- CATs antigas do CREA-SP: nº da CAT e às vezes o contratante saem ilegíveis (órgão inferido, marcado com "(?)");
- **Não reindexar a CAT do SENAI** com o código novo sem cuidado: ela já tem o patch manual do I6.
- `ruff check .` acusa 10 erros em `api/` (vindos do commit do frontend, não de hoje). **Não usar `--fix` às cegas:** ele trocaria `import mock` (módulo local `api/mock.py`) por `unittest.mock`.

**Próximos passos:**
1. Decidir se indexa o lote e quanto gastar com OCR (quais documentos entram primeiro — os 11 nativos custam só embeddings);
2. Testar a hipótese do mapeamento de nomes trocados e renomear pelo conteúdo;
3. Rever o descarte do SJC-02542;
4. Adicionar "passo 0 — triagem" em `workflows/indexacao.md` e `workflows/ingestao_documento.md` (aguardando ok do Roger para editar workflow);
5. Recalibrar o piso e reauditar depois de indexar (itens 12 e 25).

---

## 2026-09-28 — RESUMO DO DIA e ponto de partida para a próxima sessão (Roger + Claude)

> Entrada-índice: resume o dia inteiro em uma página. Os detalhes de cada etapa estão nas entradas de 28/09 logo abaixo (da mais recente para a mais antiga).

**Resultado do dia em uma linha:** o RAG saiu de nota 3/5 (auditoria de 17/08) para **4,5/5** (auditoria do lote 2), com as 10 correções do `PRECISÃO.md` aplicadas, embeddings migrados para Voyage, e 3 documentos novos indexados — mas o lote de 31 documentos do Drive se mostrou **não confiável nos nomes de arquivo**.

**O que foi feito, em ordem:**
1. **Infra destravada** — Supabase estava pausado por inatividade (reativado); dois bugs de `.env` corrigidos (`EMBEDDING_MODEL` com slug do OpenRouter e `EMBEDDING_BASE_URL` apontando pro OpenRouter);
2. **I1–I4** (filtros que zeravam a busca, refinamento sem filtro, linguagem "não está nos trechos recuperados", `top_k` 5→8) — aplicadas em sessão paralela e **verificadas ao vivo com chamada paga**: as duas recusas falsas mais graves de agosto (turnos 1.3 e 3.3) agora respondem certo;
3. **Golden set criado** (`data/golden_set.json`, 15 casos, versionado como exceção no `.gitignore`);
4. **I5, I7–I10** (multi-assunto, seção herdada em planilha, memória de conversa, consulta a `itens_planilha`, formato da resposta) — em outra sessão paralela; **I9 estava implementada mas não ligada ao CLI** — corrigido;
5. **I6** aplicado como patch pontual de dados na folha de rosto da CAT do SENAI (`tools/i6_reindexar_folha_rosto_cat576640.py`, já executado — não rodar de novo): a área certificada de 5.655 m² passou da posição 7 para a posição 1 na busca;
6. **Voyage em produção** (`voyage-4-large-1024`) após o cartão ser cadastrado; piso recalibrado para `SIMILARIDADE_MINIMA=0.4472`; golden set: **11/11 recall + 4/4 controles negativos**;
7. **Merge e push** de tudo em `main` (commit `4d36a38` publicado no GitHub); 114 testes passando, ruff limpo;
8. **PDF de documentação para a empresa**: `data/relatorios/Melhoria_RAG_Solufarma_2026-09-28.pdf` (fica fora do git, `data/` é ignorado);
9. **3 documentos novos indexados** (de 31 enviados): Ariston (vapor puro), Instituto Butantan (biotério), FIOCRUZ/Bio-Manguinhos (cabine de criogenia). **4 de 4 arquivos conferidos tinham o nome trocado em relação ao conteúdo** — metadados corrigidos no banco pelo conteúdo real;
10. **Auditoria do lote 2** (agente interrogador cego + agente orquestrador): **4,5/5** — 6 sem problema, 1 leve, 0 médias/graves. Relatório em `docs/auditorias/2026-09-28_lote2_novos_documentos.md`. Memória de conversa (I8) confirmada ao vivo pela primeira vez;
11. **Decisão TEP vs. Solufarma**: os 3 atestados novos são da TEP, não da Solufarma — tratado por ora como uso só de consulta (premissa, não confirmação).

**Estado em que as coisas ficaram (importante para amanhã):**
- **3 commits locais NÃO publicados** (`adaa38b`, `deaa652`, `154a6e2` + este registro) — Roger pediu para deixar local por enquanto. Publicar com `git push origin main` quando decidir;
- `.env`: `EMBEDDING_PROVIDER=voyage`, `SIMILARIDADE_MINIMA=0.4472`, `OPENAI_API_KEY` preenchida (fallback), `EMBEDDING_BASE_URL` vazio;
- Banco: 4 documentos, 170 chunks, todos com embedding Voyage;
- `data/brutos/`: os 3 PDFs já indexados (ainda com o nome de arquivo errado no disco — só o banco foi corrigido); `data/`: 29 PDFs soltos (27 nunca processados + o SENAI já indexado + `BUTANTAN CAT SJC-02542`, que é duplicata do SJC-02085 e foi descartado);
- Duas worktrees de sessões paralelas continuam em `.claude/worktrees/` (branches `worktree-i5-i10` e `worktree-agent-adfdac112a4b14635`) — já mescladas, podem ser removidas;
- Frontend: conceito e protótipo com vídeo demo sendo feitos em sessão paralela, em `frontend_demo/` (não commitado).

**O que falta fazer (por prioridade):**
1. **Frontend** — ~~Streamlit~~ trocado por frontend próprio (Next.js + FastAPI) em 29/09; ver `docs/DIARIO_DE_BORDO_FRONTEND.md` (item 18 do plano, maior frente em aberto);
2. **Conferir o conteúdo dos 27 documentos restantes antes de indexar** — não confiar no nome do arquivo (item 27). Vale automatizar: extrair órgão/CAT/título do próprio conteúdo em vez do nome — resolve também o item 17;
3. **Corrigir o `tools/indexar.py`**: `--titulo` só grava em `documentos.titulo`, mas o cabeçalho de cada chunk vem do nome do arquivo no chunking — hoje foi corrigido à mão no banco;
4. **Recalibrar o piso** a cada lote relevante de documentos (item 12);
5. **Reauditoria completa dos 20 turnos** de agosto para ter a nota comparável (item 25);
6. **Generalizar o padrão "folha de rosto sem heading" (I6/P6) em código** (item 28);
7. **TEP vs. Solufarma** — confirmar com a empresa se esses atestados podem ser usados como comprovação de capacidade técnica (item 26);
8. Débito técnico: port ADR-007 (item 14), testes dos CLIs novos (item 20);
9. Fora do RAG, mas do contrato: **classificação e sumarização via IA** (item 19, não iniciado) e **critérios de decisão da Solufarma** (item 5, aguardando cliente desde agosto).

---

## 2026-09-28 — 3 documentos novos indexados; nota 4,5/5 na auditoria; achado grave nos nomes de arquivo do Drive (Roger + Claude)

**O que foi feito:**
- Indexados 3 dos 31 documentos novos enviados pelo Roger (amostra pequena, de propósito, pra não gastar tokens à toa): `ATESTADO CRISTÁLIA BIOTECNOLOGIA - OBRA II.pdf`, `CNPEM CAT 2620130007911...pdf`, `FIOTEC CIPBR CAT 52669-2020...pdf` (nomes de arquivo, ver achado abaixo). Extração 100% nativa, custo zero (documentos curtos, 2-3 páginas, texto nativo no PDF, sem OCR);
- **Achado grave: os 4 arquivos conferidos até agora (esses 3 + o Butantan SJC-02542 que o Roger já suspeitava) têm o nome do arquivo trocado em relação ao conteúdo real** — confirmado direto no PDF bruto, não é boato nem bug do pipeline. Conteúdo real: Ariston Indústrias Químicas (não Cristália), Instituto Butantan (não CNPEM), CAT 758012010/cabine de criogenia FIOCRUZ-Bio-Manguinhos (não CIPBR planta industrial, apesar do nome do arquivo). Os 4 vieram assinados pela mesma empresa executante (TEP — Tecnologia em Projetos de Engenharia) e o mesmo responsável técnico (Márcio Flávio Coppio), sugerindo erro sistemático na exportação do lote do Drive, não caso isolado. **Os outros 27 documentos da pasta `data/` não foram tocados — não dá pra confiar no nome do arquivo sem conferir o conteúdo primeiro**;
- Corrigido no banco: título/órgão dos 3 documentos indexados, usando o conteúdo real (não o nome do arquivo). Um segundo bug encontrado no processo: `--titulo` do `tools/indexar.py` só corrige a coluna `documentos.titulo`, não o cabeçalho contextual gravado dentro de cada chunk (o que aparece nas citações) — corrigido manualmente nos 9 chunks afetados, reembeddados;
- **Auditoria de 2 agentes rodada nos 3 documentos novos** (mesmo método de 17/08, com um terceiro papel — "orquestrador" — medindo a nota): Agente 1 (analista cega, sem acesso a documentos/código) fez 7 perguntas reais em 2 sessões via `tools/perguntar.py`; Agente 3 (orquestrador, com acesso ao conteúdo real) conferiu cada resposta. **Nota: 4,5/5** (6 sem problema, 1 falha leve, 0 médias/graves) — bem acima do 3/5 de agosto. Relatório completo em `docs/auditorias/2026-09-28_lote2_novos_documentos.md`;
- **Achado de negócio, não técnico**: ao pedir um parágrafo pronto pra proposta citando "nossa experiência", o sistema atribuiu a obra à Solufarma na primeira frase (sem citação — herdado do system prompt, não do acervo) e só depois se corrigiu numa ressalva dizendo que a executante real é a TEP. Não é alucinação (nenhum número inventado), mas é risco real: **não há vínculo comprovado no acervo entre a TEP (executante desses 3 atestados) e a Solufarma**. Confirmado pelo orquestrador: a palavra "Solufarma" não aparece em nenhum dos 9 chunks novos. **Pendência de confirmação com a Solufarma**: esses 3 atestados podem ser citados como experiência da empresa, ou são de outra pessoa jurídica/profissional? Nada foi mudado no cadastro até essa resposta chegar;
- Confirmado com chamada paga real, pela primeira vez: a memória de conversa (I8) funcionou nos dois pronomes soltos testados ("esse atestado", "essa obra"), sem vazar entre sessões diferentes;
- Confirmado: a lacuna de numeração nas fontes (ex. [1][2][4] sem [3]) é comportamento intencional, não bug — só entra na lista quem foi citado de fato no texto, mesmo que mais trechos tenham sido recuperados;
- O padrão "folha de rosto sem heading" (que motivou o I6) se repetiu nos 3 documentos novos — agora são 4 documentos com o mesmo padrão, não mais 1. Vale reconsiderar generalizar a heurística em `src/solufarma/chunking.py` em vez de seguir corrigindo caso a caso.

**Pendências:**
- **TEP vs. Solufarma — decisão do Roger (28/09): tratar por ora como uso apenas de consulta interna**, não como base para comprovação formal de capacidade técnica em proposta. Premissa assumida, não confirmação definitiva — se o time decidir usar esses atestados (ou os que vierem depois com o mesmo padrão) numa submissão real, a decisão muda e o cadastro/system prompt precisam de um campo explícito de vínculo empresarial antes disso acontecer. Nenhum dado foi alterado com base nessa premissa;
- Verificar os nomes de arquivo dos outros 27 documentos da pasta `data/` antes de indexar qualquer um — não é seguro assumir que o nome bate com o conteúdo;
- Generalizar I6/P6 (folha de rosto sem heading) em código, agora com evidência de 4 documentos;
- Captura de log da reescrita do I8 (hoje só foi possível inferir pelo resultado final, não pela pergunta reescrita literal) — melhoria pra próxima auditoria.

---

## 2026-09-28 — Voyage destravada; acervo migrado; piso recalibrado (Roger + Claude)

**O que foi feito:**
- Terceira tentativa de reembeddar com Voyage, alguns minutos depois do cartão cadastrado — **funcionou**. 162 chunks reembeddados (`voyage-4-large-1024`, ~37K tokens);
- Recalibrado o piso de similaridade contra o `data/golden_set.json` com `tools/avaliar.py --calibrar`: `SIMILARIDADE_MINIMA=0.4472` (folga de 0,012 entre sinal e ruído — estreita, esperado com 1 documento só; recalibrar de novo quando o acervo crescer);
- Golden set completo rodado com Voyage + piso novo: **recall 11/11 (100%) e 4/4 controles negativos corretos** — melhor que o resultado medido com OpenAI (que tinha 1/4 nos controles por ruído do ramo léxico, contornado pela camada de resposta/I3, não pela recuperação);
- Reconfirmado ao vivo (chamada paga real) o turno 1.3: resposta continua correta, lidera com "Sim", cita a área certificada (5.655 m²) primeiro. Efeito colateral menor observado: a ordenação diferente da Voyage não trouxe o 3º pavimento desta vez, e a resposta voltou a mencionar um "1º pavimento" que não existe no prédio (mesmo padrão do turno original da auditoria) — não é regressão de código, é a mesma sensibilidade a que documento entra no top-k, já conhecida;
- `EMBEDDING_PROVIDER=voyage` e `SIMILARIDADE_MINIMA=0.4472` no `.env` (principal e nesta worktree, sincronizados).

**Item 11 do plano fecha de verdade agora** — Voyage em produção, testada, calibrada, não é mais "decisão sem A/B".

---

## 2026-09-28 — I6 aplicado (folha de rosto da CAT); I9 ligado ao CLI; documentação em PDF (Roger + Claude)

**O que foi feito:**
- **I9 estava implementada mas não conectada** — `tools/perguntar.py` construía o `AgenteLicitacoes` sem passar `repo_itens`. Corrigido (uma linha). Verificado contra o Supabase real: pergunta sobre pontos de gases especiais agora cita os números exatos da planilha (144+167+28 conjuntos, p.45) em vez de recusar;
- **I6 aplicado como correção pontual de dados**, não como heurística de código: os 3 chunks que cobrem a folha de rosto da CAT (p.1-2) foram reescritos manualmente — a seção "ATIVIDADE TÉCNICA REALIZADA" (onde está a área certificada de 5.655,00 m²) virou chunk próprio, com heading sintético no cabeçalho contextual; os outros dois chunks da folha de rosto ganharam headings equivalentes ("DADOS DO CONTRATO", "ENDEREÇO DA OBRA/SERVIÇO"). Não houve reprocessamento de OCR — o texto extraído já estava correto, só a divisão em chunks escondia a seção. Script em `tools/i6_reindexar_folha_rosto_cat576640.py` (já executado, não deve rodar de novo — ver aviso no arquivo);
- Renumeração de `chunk_index` feita com deslocamento em duas fases (offset temporário de 100000) para não violar a constraint `unique(documento_id, chunk_index)` durante a operação — 159 linhas deslocadas, 0 colisões, conferido por asserção antes do commit da transação;
- Reembeddados só os 3 chunks afetados (882 tokens, OpenAI, ~US$ 0,0001) — o resto do acervo não foi tocado;
- **Verificação ao vivo, chamada paga real**: o turno 1.3 (3.000 m² de área) voltou a ser testado — agora a resposta lidera com "Sim", cita o número certificado (5.655,00 m²) da nova seção *e* a soma por pavimento (5.187,56 m²), tratando a diferença como ressalva plausível (áreas adicionais não capturadas) em vez de escolher um número às cegas. É a melhor resposta desse turno em toda a sessão;
- Confirmado por busca crua (`--so-busca`, sem custo): a pergunta "atividade técnica realizada área total construída da obra" agora recupera o novo chunk na **posição 1** — antes da correção só aparecia na posição 7, mesmo com `top_k=8`;
- **Gerado `data/relatorios/Melhoria_RAG_Solufarma_2026-09-28.pdf`** — documentação da sessão para a empresa (resumo executivo, diagnóstico da auditoria de 17/08, as 9+1 correções aplicadas, evidência antes/depois, situação atual).

**Decisão registrada:** I6 foi tratado como patch de dados específico deste documento (não uma heurística genérica em `src/solufarma/chunking.py`), seguindo a própria recomendação do PRECISÃO.md de não generalizar sem um segundo documento para validar contra. Quando o acervo ganhar mais atestados/editais, vale avaliar se o padrão de "folha de rosto com blocos em caixa alta sem heading" se repete — só aí compensa investir na heurística de código.

**Pendências:**
- Merge das branches paralelas (`worktree-agent-adfdac112a4b14635` com I1-I4, e esta com I5-I10) em `main` — bloqueado pela permissão de merge automático do ambiente, aguardando o usuário rodar manualmente ou ajustar a permissão;
- Reauditoria completa dos 20 turnos ainda não feita. Dos 7 turnos de gravidade alta: **3 reconfirmados ao vivo com chamada paga real** (1.3 — área/3000m², 3.3 — contratante/CNPJ/vigência, 2.4 — pontos de gases) e **1 confirmado só por retrieval bruto, sem custo** (1.2 — `--so-busca` agora recupera os 5 pavimentos). Os outros três (1.4, 2.1, 4.3) dependem do mesmo mecanismo já corrigido, mas não foram testados individualmente — ficam para a reauditoria completa.

---

## 2026-09-28 — Aplicadas I5, I7, I8, I9 e I10 do PRECISÃO.md; I6 fica de fora (Claude)

**O que foi feito** (branch `worktree-i5-i10`, a partir de `worktree-agent-adfdac112a4b14635`, que já tinha I1-I4):

- **I5** — `PROMPT_INTERPRETAR` (`prompts.py`) pede `"consultas": [...]` (1 a 3 itens) em vez de `"consulta"` singular, com a regra "uma consulta por assunto, nunca junte assuntos diferentes". `Interpretacao.consultas: list[str]` substitui o campo singular; `_extrair_consultas` (`agent.py`) lê a lista com fallback para o formato antigo (`"consulta"`) e para a pergunta crua, sempre cortando em `MAX_CONSULTAS = 3` no código — não confia só na instrução do prompt. `AgenteLicitacoes._buscar` busca cada consulta separadamente com o próprio `top_k` e une os resultados deduplicando por `chunk.chave`, preservando a ordem de RRF dentro de cada busca;
- **I7** — `_pseudo_heading_tabela` (`src/solufarma/chunking.py`) reconhece linha de tabela em que só a primeira célula tem conteúdo, em caixa alta e com até 40 caracteres (`MAX_CHARS_PSEUDO_SECAO`), e a trata como divisão de seção/subseção: empilha no `caminho_secao` com um nível sentinela (`NIVEL_PSEUDO_SECAO = 900`, acima de qualquer heading markdown real) em vez de deixar o bloco herdar o heading anterior. Duas pseudo-seções consecutivas são irmãs (a nova substitui a anterior na pilha), e um heading real de verdade sempre estoura as pseudo-seções acumuladas;
- **I8** — `AgenteLicitacoes.responder` (`agent.py`) aceita `historico: list[dict] | None`; quando presente, `_resolver_referencia` roda `PROMPT_RESOLVER_REFERENCIA` (novo em `prompts.py`, texto colado do PRECISÃO.md) antes de `_interpretar`, reescrevendo a pergunta como autossuficiente e sempre logando original + reescrita em `INFO`. `tools/perguntar.py` acumula pares `{"pergunta", "resposta"}` no modo interativo e passa adiante a cada turno;
- **I9** — novo método `buscar_itens_planilha(termo, documento_id=None, limite=20)` no protocolo `ChunkRepository` (`db/repository.py`), implementado em `InMemoryChunkRepository` (substring normalizada, com `adicionar_item_planilha` auxiliar de teste) e em `SupabaseChunkRepository` (SQL com `ilike` sobre `array_to_string(celulas, ' ')`, JOIN com `documentos`/`licitacoes` para trazer `orgao`/`tipo_documento` — **não executado contra o banco real**). `AgenteLicitacoes` ganhou `repo_itens: ChunkRepository | None = None` opcional; quando presente e a pergunta bate em `_pede_quantitativo` (marcadores "quant", "total de", "m2", "unidade"), `_buscar` complementa a busca híbrida com um SELECT estruturado, convertendo cada linha (`ItemPlanilha`, novo modelo em `db/models.py`) num `ChunkComScore` sintético — entra no contexto como trecho numerado normal, citável por [n] pelo mesmo mecanismo de sempre. Não agrega/soma, só lista linhas casadas, como o próprio PRECISÃO.md manda;
- **I10** — bloco `ESTILO` do `SYSTEM_AGENTE` (`prompts.py`) trocado pelo texto do PRECISÃO.md: primeira linha responde com o número + [n] quando pediram número, sem título em negrito para resposta de um parágrafo. `RespostaAgente` ganhou `trechos_recuperados: int` (total de trechos no contexto, antes do filtro de citação). Em `tools/perguntar.py`, `_mostrar_resposta` acrescenta um discriminador (início do `trecho`) nas fontes que compartilham órgão+seção+página, e uma linha final "Fontes: N citadas de M trechos recuperados". Aplicado depois de confirmar que I3 já estava no `prompts.py` da branch base, como o PRECISÃO.md manda;
- **I6 ficou de fora**, por instrução explícita da tarefa: exige reprocessar o documento real (reindexar a folha de rosto da CAT com seção sintética) e reembeddar contra o Supabase ao vivo — risco de colisão com outra sessão escrevendo no mesmo banco ao mesmo tempo. Fica pendente para uma sessão isolada.

**Verificação:**
- `uv run --extra dev ruff check .` limpo;
- `uv run --extra dev pytest -q`: **114 testes passando** (99 pré-existentes + 15 novos, nenhum pré-existente perdido). Um teste precisou de ajuste mecânico: o helper `_interpretacao()` de `tests/test_agent.py` passou a emitir `"consultas": [consulta]` em vez de `"consulta": consulta` — mudança de formato de dado, não de comportamento testado; todos os testes que usavam `_interpretacao(consulta=...)` continuam passando sem alteração de asserção;
- Cobertura nova: I5 (pergunta com 2 assuntos gera 2 consultas e deduplica; limite duro de 3), I7 (fixture sintética reproduzindo o padrão real `| GASES | | |` / `| **HIDRÁULICA** | | |`, comparado com `.tmp/acervo_indexado.md` só por leitura — nenhuma escrita no Supabase), I8 (reescrita roda antes de interpretar; sem histórico ou com histórico vazio não aciona a chamada extra; pergunta devolvida intacta pelo LLM segue o fluxo), I9 (pergunta com marcador de quantidade consulta `repo_itens`; sem marcador ou sem `repo_itens` não quebra nem chama à toa) — todos com `FakeLLM`/`SearcherStub`/`InMemoryChunkRepository`, offline;
- **Nada rodado contra o Supabase real** (nem leitura nem escrita) — nem para I7 (comparação foi textual, contra a cópia local `.tmp/acervo_indexado.md`, fora do repo/gitignorada) nem para I9 (a query do `SupabaseChunkRepository.buscar_itens_planilha` existe mas não foi exercitada contra o banco).

**Decisões tomadas que não estavam 100% explícitas no PRECISÃO.md:**
- **I9, formato de `termo`**: o texto diz só "ilike sobre array_to_string(celulas, ' ')" sem definir o que o agente passa como `termo`. Decidi reusar cada item de `interpretacao.consultas` (já filtrado pelo LLM para "termos que apareceriam no documento") em vez da pergunta crua do usuário — mas isso significa que o casamento é só contra o texto da CÉLULA, não contra a seção; uma consulta como "gases" só acha uma linha se a palavra estiver na descrição do item, não só no rótulo de seção que a envolve (que, depois de I7, é onde "GASES" normalmente mora). Isto é uma limitação real do desenho descrito no PRECISÃO.md, não um bug desta implementação — registro aqui para quem for validar contra o documento de verdade;
- **I9, forma de citação**: converti cada `ItemPlanilha` num `Chunk`/`ChunkComScore` sintético (com `chunk_index` deslocado por `_OFFSET_CHUNK_INDEX_PLANILHA = 1_000_000` para não colidir com chunks reais) para reaproveitar `montar_contexto`/`extrair_citacoes` sem duplicar o mecanismo de citação — o PRECISÃO.md só disse "trechos numerados normais", não como;
- **I8, formato de `historico`**: defini `list[dict]` como pares `{"pergunta": ..., "resposta": ...}` (não `{"role", "content"}` estilo chat) porque é o formato natural do laço pergunta/resposta do `tools/perguntar.py`; a reescrita SUBSTITUI a pergunta para o resto do fluxo (interpretar + responder), não só para a busca — é o que a seção "como verificar" do PRECISÃO.md pede ("a consulta gerada deve conter...");
- **I7, limite de 40 caracteres**: aplicado como está escrito no PRECISÃO.md. Contra o texto real do documento isso também reconhece rótulos intermediários mais específicos (ex.: um nome de item de até 40 caracteres em caixa alta que antecede sua própria tabela de bitolas), não só os dois exemplos citados (`GASES`, `HIDRÁULICA`) — comportamento a favor do objetivo (rótulo mais específico que o heading herdado errado), mas não foi medido contra uma reindexação completa do documento, só contra os trechos testados isoladamente.

**Pendências:**
- I6 fica para uma sessão isolada (reprocessa o documento real + reembedda contra o Supabase ao vivo);
- I7 validado só por comparação textual offline (fixtures sintéticas espelhando linhas reais de `.tmp/acervo_indexado.md`) — falta rodar a reindexação completa do documento e comparar `caminho_secao` chunk a chunk, como o "como verificar" do PRECISÃO.md pede;
- I9 sem teste contra `itens_planilha` real — a query do `SupabaseChunkRepository` está escrita e comentada mas não foi executada; falta validar se `ilike` sobre as células, sozinho, realmente encontra os 144+167 reguladores do turno 2.4 (ver decisão acima sobre secao vs. célula);
- Nenhuma das cinco instruções foi medida com chamada paga de LLM — as seções "como verificar" do PRECISÃO.md continuam como hipóteses testáveis, não resultados, exceto pelo que os testes unitários offline cobrem;
- Refazer a bateria de 20 turnos (ou pelo menos os turnos citados nas evidências de I5/I7/I8/I9/I10) continua pendente, igual registrado na entrada de I1-I4.

---

## 2026-09-28 — I1-I4 verificadas contra o Supabase real, ao vivo (Roger + Claude)

**O que foi feito:**
- Supabase estava pausado por inatividade (mais de um mês sem uso) — reativado. Diagnóstico completo (`tools/setup_supabase.py --check`) voltou limpo;
- Descobertos e corrigidos dois bugs de configuração que travavam qualquer embedding: `EMBEDDING_MODEL` tinha o slug no formato do OpenRouter (`openai/text-embedding-3-large`, inválido pra chamada direta na API da OpenAI) e `EMBEDDING_BASE_URL` apontava pro OpenRouter, que não aceita a chamada de embeddings da forma configurada. Corrigidos os dois no `.env`;
- Reembeddados os 161 chunks com OpenAI (`text-embedding-3-large`, ~37K tokens, ~US$ 0,005) — o piso de similaridade (0,474) já estava calibrado pra esse modelo, não precisou recalibrar;
- Decisão do Roger: usar Voyage como padrão (já era o padrão no código) ficou **bloqueada** pelo tier gratuito sem cartão da Voyage (3 RPM / 10K TPM) — toda tentativa de reembeddar falhou, mesmo em lotes pequenos e pausados. Registrado como pendência separada, não bloqueante hoje;
- **Rodadas as verificações que a sessão anterior não conseguiu** — as prescritas no PRECISÃO.md para I1 e I4, mais duas checagens de I3, todas com chamada paga real (não `--so-busca`):
  - Turno 1.3 (3.000 m²): recusa falsa → **agora responde**, soma as áreas por pavimento (5.187,56 m²), cita as 5 fontes certas e sinaliza sozinho uma anomalia nos dados (valores repetidos) em vez de afirmar com falsa confiança;
  - Turno 3.3 (contratante/CNPJ/vigência): recusa falsa → **agora responde** exatamente os dados certos (SENAI CETIQT, CNPJ 03.851.105/0001-42, vigência 07/02/2019–06/02/2020), distinguindo vigência de prazo de execução;
  - Turno 4.1 (obra hospitalar) e um novo controle (obra de 2021 pro governo do estado): **continuam recusando corretamente**, agora na linguagem do I3 ("não encontrei isso nos trechos recuperados", não "não está no acervo");
- Rodado `tools/avaliar.py` contra o `data/golden_set.json` novo (15 casos, ver abaixo): **recall 11/11 (100%)** nos casos positivos com `top_k=8`.

**Achado importante — o golden set expôs uma lacuna real:**
- 3 dos 4 controles negativos "falharam" no nível de **recuperação bruta**: o ramo léxico (full-text) da busca híbrida não tem piso de relevância (só "casa por termo"), e palavras genéricas do domínio ("atestado", "obra", "gases") aparecem no documento mesmo quando o assunto específico da pergunta (hospital, ISO 14644, 2021) não aparece. Com `top_k=8` (I4), mais desse ruído lexical entra na janela visível — não entrava com `top_k=5`;
- **Mas ao rodar o agente de verdade** (não só a busca) nos dois controles que falharam na recuperação, a resposta final continuou correta nos dois — o I3 pegou o ruído e recusou do jeito certo. Ou seja: o golden set testa disciplina de *recuperação*, não qualidade de *resposta final*, e são coisas diferentes. Isso não é uma regressão de I4, é uma limitação de metodologia do golden set — vale nota para quem for evoluir `tools/avaliar.py`: um controle negativo "falhando" na recuperação merece checagem manual da resposta antes de virar alarme.

**Golden set criado:** `data/golden_set.json` (15 casos: 11 positivos + 4 controles negativos), cada página verificada direto contra `.tmp/acervo_indexado.md` (texto completo indexado), não só contra o resumo do PRECISÃO.md. Passou a ser versionado (exceção pontual no `.gitignore`, já que `data/` é bloqueado por conter documento de cliente).

**Pendências atualizadas:**
- Item 11 do plano fechado: Voyage por decisão/conveniência, sem A/B formal (chave testada e funcional, mas bloqueada pelo rate limit sem cartão);
- I5-I10 do PRECISÃO.md seguem em outra sessão paralela (branch `worktree-i5-i10`), fora desta;
- I6 (reindexar a folha de rosto da CAT com headings sintéticos) ainda não feito — fica para quando I5-I10 estiver consolidado, porque precisa reprocessar e reembeddar contra o banco real;
- Ainda falta refazer a bateria completa de 20 turnos (não só os 4 verificados aqui) para atualizar a nota 3/5 de 17/08.

---

## 2026-09-28 — Aplicadas as 4 instruções de baixo esforço do PRECISÃO.md (I1-I4) (Claude)

**O que foi feito:**
- **I1** — `PROMPT_INTERPRETAR` (`src/solufarma_rag/agent/prompts.py`) parou de pedir filtros estruturados de verdade: os quatro campos de `filtros` agora saem sempre `null` no JSON pedido ao LLM, com regra explícita "Não invente filtros". Adicionadas também as regras de "consulta" que já estavam no texto do PRECISÃO.md (termos do documento, não do processo licitatório do usuário);
- **I2** — `AgenteLicitacoes.responder` (`src/solufarma_rag/agent/agent.py`), dentro do `while not resultados`: a segunda tentativa de busca agora chama `self.searcher.buscar(nova_consulta, FiltrosBusca(), self.top_k)` — filtros zerados, não os da interpretação original — para que um filtro que zerou a primeira busca não condene a segunda também;
- **I3** — regra 3 do `SYSTEM_AGENTE` e última linha do `PROMPT_RESPONDER` trocaram a linguagem de "não está no acervo" / "documento não menciona" por "não está nos trechos recuperados", com a ressalva de que o agente vê 5-8 trechos de um documento de dezenas de páginas — texto colado exatamente como está no PRECISÃO.md;
- **I4** — `TOP_K_PADRAO` (`src/solufarma_rag/retrieval/hybrid_search.py`) subiu de 5 para 8; `--top-k` default em `tools/perguntar.py` idem. `CANDIDATOS_PADRAO` não foi tocado, como instruído.

**Verificação:**
- `uv run ruff check src tools tests` limpo;
- `uv run pytest -q`: **99 testes passando**, nenhum precisou de ajuste — os testes de agente usam `FakeLLM`/`SearcherStub` com JSON de interpretação fixado no próprio teste (não dependem do texto do prompt), e os testes de `top_k` sempre passam o valor explicitamente, nunca dependendo do default;
- **Não foi possível rodar a verificação `tools/perguntar.py ... --so-busca` prescrita no PRECISÃO.md para I1 e I4** (as perguntas do contratante/CNPJ e da área por pavimento): a conexão com o Supabase do projeto falhou com `EAUTHQUERY ... connection to database not available` em duas tentativas — sintoma de projeto Supabase pausado ou indisponível no momento, não relacionado às mudanças de código. Fica pendente rodar essas duas verificações assim que o banco estiver acessível;
- I3 é só prompt — como o próprio PRECISÃO.md registra, só dá para confirmar com chamada paga de LLM contra os dois turnos citados (piso/forro e sala limpa), que não foi feita aqui.

**Decisões tomadas que não estavam 100% explícitas no PRECISÃO.md:**
- O default `top_k: int = 5` em `AgenteLicitacoes` (`agent.py`) **não foi alterado** — I4 só lista `hybrid_search.py` e `perguntar.py` como "Onde". Na prática isso não importa hoje: o único chamador de produção (`tools/perguntar.py`) sempre passa `top_k=args.top_k` explicitamente, que agora já nasce em 8;
- Copiei o `.env` da raiz do repo (fora da worktree) para dentro da worktree só para tentar a verificação `--so-busca` contra o banco real — arquivo gitignorado, não entrou em nenhum commit.

**Pendências (continuam abertas):**
- I5-I10 do PRECISÃO.md ficam para depois — fora do escopo desta tarefa;
- Rodar as verificações `--so-busca` de I1/I4 e a bateria de 20 turnos completa (mencionada no diário de 17/08) assim que o Supabase estiver acessível de novo;
- Nota do RAG (3/5 em 17/08) continua sem remedição — só uma nova rodada da auditoria de dois agentes confirma se I1-I4 moveram o placar.

---

## 2026-08-17 — RAG validado ponta a ponta e auditado por workflow de dois agentes (Roger + Claude)

**O que foi feito:**
- **RAG rodou de verdade pela primeira vez**, contra o banco real: 1 documento (CAT 576640 do SENAI CETIQT, 60 páginas), 161 chunks, todos embeddados. Resposta com 5 citações apontando para páginas reais; controle negativo ("autoclaves para o Hospital das Clínicas") recusado corretamente;
- Dois problemas de configuração corrigidos no caminho: `EMBEDDING_PROVIDER=voyage` com `VOYAGE_API_KEY` vazia contra 161 chunks embeddados com `openai/text-embedding-3-large-1024` (busca devolveria lixo sem erro), e `UnicodeEncodeError` no console cp1252 do Windows — resolvido forçando UTF-8 na saída dos 9 CLIs;
- Criado `tools/dump_acervo.py`: despeja o acervo indexado por inteiro (página, seção, texto). Sem ele, auditar o RAG é circular — a única janela para o conteúdo era a própria busca;
- **Workflow de dois agentes com contextos deliberadamente separados**, a pedido do Roger. Agente 1 (cego: sem acervo, sem código) interpretou uma analista de licitações em 4 sessões encadeadas / 20 turnos, com pronome solto, desconfiança, reformulação e pedido de formato — registro verbatim em `docs/auditorias/2026-08-17_conversas_rag.md`. Agente 2 (com o acervo integral + o código, sem o raciocínio do agente 1) conferiu turno a turno e escreveu `PRECISÃO.md`;
- `PRECISÃO.md` criado na raiz: veredito turno a turno, 10 padrões por causa raiz, 10 instruções acionáveis ordenadas por impacto/esforço, seção "o que NÃO mudar" e limites da avaliação.

**Aprendizados / observações:**
- **Placar: 7 turnos com problema grave, 3 médios, 2 leves, 8 limpos. Nota do RAG hoje: 3 de 5** — fundação sólida (4), experiência entregue ao cliente (2);
- **Zero alucinação em 20 turnos.** Nenhum marcador `[n]` inválido, nenhum dado de obra inventado. A parte difícil (não mentir) está funcionando;
- **A falha mais perigosa é a recusa falsa.** Três vezes o agente disse "não encontrei no acervo" sobre informação que está lá: a área certificada (5.655,00 m², p.2), os 311 postos de consumo de gases (p.45) e a nomenclatura "sala limpa" (p.11 + planilha). Recusa errada *parece* acerto de honestidade, então ninguém audita. Só se detecta com o acervo inteiro na mão — foi por isso que o dump precisou existir antes do agente avaliador;
- **Causa raiz reproduzível:** `PROMPT_INTERPRETAR` oferece o enum `edital|ata|resultado` e o único documento é `tipo='atestado'`. Qualquer filtro que o modelo emitir garante zero resultados. Pior: o nó de refinamento troca a consulta e **mantém os filtros**, então a segunda chamada paga nasce condenada;
- `top_k=5` corta a última peça em respostas que precisam de N trechos homogêneos: faltaram 3.695,36 m² dos maiores itens de piso, e a resposta ainda declarou a lista completa;
- A tabela `itens_planilha` tem 807 linhas populadas e indexadas, e **nunca é consultada** — as duas piores respostas de quantitativo são as que um `SELECT` resolveria;
- Chunks de planilha herdam seção errada (quantitativos de GASES rotulados como quadro de distribuição elétrica), porque as divisões são linhas de tabela e o chunker só empilha headings markdown. O rótulo errado entra no embedding;
- Separar os contextos dos dois agentes foi o que produziu o achado principal: o testador cego não podia saber que a recusa era falsa, e o avaliador não podia ser contaminado por opinião de teste;
- **A nota 3 é provisória e provavelmente otimista** — medida contra 1 documento de 1 tipo, que nem é o tipo principal do produto.

**Próximos passos:**
- Aplicar as 4 primeiras instruções do `PRECISÃO.md` (baixo esforço, cobrem 6 dos 7 turnos graves): I1 parar de gerar filtros na interpretação, I2 relaxar filtros no refinamento, I3 separar "não está nos trechos" de "não está no acervo", I4 subir `top_k` para 8;
- **I10 só depois de I3 e I4** — antes disso ela deixaria a resposta errada mais assertiva;
- Refazer a mesma bateria de 20 turnos depois das mudanças e comparar (é a única forma de saber se a nota subiu);
- Aplicação Streamlit (item 18) segue sendo a maior frente em aberto que não depende de ninguém.

---

## 2026-08-09 — Supabase configurado e validado; merge com o pipeline da Diva (Roger + Claude)

**Merge das duas frentes.** `origin/main` tinha o pipeline de OCR/chunking da Diva (`bcc00e3`),
paralelo ao nosso. 8 arquivos conflitavam. As decisões dela venceram todos; nossa ADR-005
(orquestração do agente) foi renumerada para **ADR-008**, porque a 005 dela (OCR via OpenRouter)
já estava na main. Uma auditoria adversarial por agente pegou 5 problemas de contrato que teste
nenhum acusaria — o pior: o `.env.example` deixou de configurar o nosso pacote, e a chave chegaria
vazia com erro só na primeira chamada real. Tudo corrigido antes do merge na main.

**Supabase, de configurado a provado.** O schema foi aplicado no banco real (PostgreSQL 17.6,
session pooler `sa-east-1`): 6 tabelas, extensões, índices HNSW/GIN e RLS ligado nas 6.

Dois problemas reais apareceram na aplicação:
1. **`unaccent()` não é IMMUTABLE**, e o Postgres recusa função STABLE em índice e em coluna
   gerada. A migração inteira abortava. Contornado com o wrapper `public.f_unaccent()`, que fixa
   o dicionário explicitamente. Toda busca textual precisa usar ele — usar `unaccent` direto faz
   a consulta normalizar diferente do índice e simplesmente não casar;
2. **Faltava a tabela `itens_planilha`**, exigida pelo ADR-006 da Diva. Criada com duas colunas de
   documento de propósito: `documento_hash` (o que o chunking produz hoje) e `documento_id` (a FK
   de verdade, nula até o cadastro existir) — para a ingestão não travar esperando cadastro.

**`tools/setup_supabase.py --smoke`**: o `SupabaseChunkRepository` nunca tinha rodado contra banco
real. Agora roda o caminho completo — upsert → embeddings → busca híbrida → filtro por órgão —
com dados sintéticos que ele mesmo apaga. **9 verificações, todas passando.** Foi a primeira prova
de que a camada de banco funciona, e não só de que o schema existe.

**Decisões do Roger (09/08):**
- Modelo de embeddings (Voyage × OpenAI) **fica em aberto** — mas precisa fechar antes da primeira
  carga real, porque trocar depois obriga a recriar a coluna `vector(N)` e reprocessar tudo;
- Acesso ao banco é por `DATABASE_URL` (psycopg direto). A API REST do Supabase não faz operador
  de vetor nem full-text com filtro. `DATABASE_URL` entrou em `VARIAVEIS_POR_ESTAGIO["indexacao"]`;
- O acervo é escaneado, então **o chunker da Diva é o único** — o nosso, feito para edital digital
  nativo, não tem fonte de entrada neste fluxo.

**O que falta, especificado e não implementado:** a ponte entre o chunking e o Supabase. Os dois
`Chunk` (dela e nosso) têm o mesmo nome e nenhum campo em comum além das páginas. A tradução
campo a campo, o passo de cadastro do documento e as armadilhas conhecidas estão em
[workflows/indexacao.md](../workflows/indexacao.md).

**Estado:** 99 testes offline + 9 verificações contra o banco real, ruff limpo, main sincronizada.

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
