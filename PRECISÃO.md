# PRECISÃO — plano de correção do RAG do acervo

## 1. O que este arquivo é

As evidências são as 4 sessões / 20 turnos registrados em `docs/auditorias/2026-08-17_conversas_rag.md`, produzidos por um agente que interpretou uma analista de licitações e não teve acesso nem ao acervo nem ao código. Cada afirmação factual dessas respostas foi conferida linha a linha contra `.tmp/acervo_indexado.md` (os 161 trechos indexados, texto integral) e contra o código do pipeline; toda suspeita de falha de busca foi reproduzida com `uv run python tools/perguntar.py "..." --so-busca` (custo zero) e com consultas diretas ao Supabase. Avaliação feita em 2026-08-17, com o acervo no estado inicial: um único documento, a CAT nº 100200 do Instituto BioPharma, 60 páginas.

Nenhum número deste arquivo é estimado, salvo onde está escrito "estimativa".

---

## 2. Veredito turno a turno

| Turno | Pergunta (resumida) | Classe | Gravidade | O que aconteceu |
|---|---|---|---|---|
| 1.1 | Temos atestado de implantação de laboratório? | OK | — | Todos os fatos conferem: contrato, valores, prazos, LEED, gases, água (13,03 m³/h), no-break 200 kVA, RS-485/Modbus, anti-explosão. Citações corretas. |
| 1.2 | E a área disso, quantos m²? | retrieval | **alta** | Somou só 4 pavimentos (4.078,56 m²). O 3º pavimento existe (p.5) e ficou fora do top_k=5. Ainda inventou a existência de um "1º pavimento" que não existe no prédio. |
| 1.3 | Bate os 3.000 m² que o edital pede? | recuperação | **alta** | Recusou ("não encontrei nada"). A mesma pergunta em `--so-busca` devolve as 5 tabelas de área. E o acervo traz o número certificado: **5.655,00 m²** de execução de obra/reforma, na p.2. Recusa falsa. |
| 1.4 | Área total somando todos os pavimentos | ancoragem + retrieval | **alta** | A soma 5.187,56 m² está aritmeticamente certa a partir das tabelas. Mas afirmou que "não há valor consolidado explícito de área total construída" — há: 5.655,00 m² na CAT. Número plausível e errado para o uso. |
| 1.5 | Resume em 3 linhas pra proposta | OK | — | Melhor resposta do teste. Curta, colável, todos os dados conferem. Único defeito: fontes numeradas [1] e [3], sem [2] — parece bug. |
| 2.1 | Quantitativos de piso, forro, etc. | retrieval + ancoragem | **alta** | Forro (13 itens) e parede (10 itens) conferem integralmente. Mas o piso saiu incompleto: faltaram P01 (206,92 m²), P02 (1.278,26 m²) e P03 (2.210,18 m²) — **3.695,36 m², os maiores itens de piso da planilha** — e a resposta ainda declarou "não encontrei quantitativos adicionais de piso/forro além dos listados". |
| 2.2 | Piso vinílico: marca e onde foi aplicado | concisão / forma | baixa | Fatos corretos (salas DNA e HTS no 4º pav., enchimento de 15 cm no térreo, P01–P03, linha Eclipse Premium). Omitiu as quantidades que estavam no mesmo trecho citado. Fontes [2] e [3] aparecem com rótulo idêntico e a numeração pula o [4]. |
| 2.3 | Prazo total com aditivos | OK | — | 180 + 30 + 60 = 270 dias. Correto. A "contradição" com o turno 1.1 (que disse "+90 dias") é aparente: 30+60 = 90. Problema de apresentação, não de fato. |
| 2.4 | Quantos pontos de consumo de gases e capacidade da central | recuperação | **alta** | Recusou o número de pontos. Ele está no acervo, p.45: 144 reguladores de 2º estágio em parede + 167 em totem = **311 postos de utilização**, mais 28 reguladores de 1º estágio. O trecho não foi recuperado. Recusa falsa com cara de honestidade. |
| 2.5 | 160 bar faz sentido para ar comprimido? | OK (prolixo) | baixa | Todos os números conferem, inclusive os 210 bar (que estão nos dois trechos citados) e os 30–150 psi. Ressalva bem feita. Mas são 5 blocos para uma dúvida pontual. |
| 3.1 | Quem assinou como responsável técnico | OK | — | Quatro nomes, CREA/CAU e vistos, todos exatos. RRT individual, correto. |
| 3.2 | Número do CAT e da ART | OK, com nuance | média | CAT 100200/2020, RRT 1002001 SIMPLES de 13/03/2019, CAU/SP 06/07/2020 — tudo confere. A explicação "RRT é do CAU, ART é do CREA" é conhecimento geral sem citação: útil, mas fora da regra 1 do system prompt. |
| 3.3 | Contratante, CNPJ e vigência | recuperação | **alta** | Recusou. Em `--so-busca` a mesma pergunta devolve exatamente os trechos certos. Falha antes da busca, não na busca. |
| 3.4 | Contratante e vigência (sem CNPJ) | OK | — | Correto e completo. Mostra que a informação sempre esteve lá. |
| 3.5 | Ficha para o envelope de habilitação | ancoragem parcial | média | Ficha excelente e integralmente ancorada. Mas omitiu duas coisas materiais que estavam no contexto ou no acervo: os **5.655,00 m²** certificados (no mesmo trecho p.1-2 que ela citou) e o **valor global ajustado de R$ 8.750.000,00** (informou só o original de R$ 6.500.000,00). Três fontes exibidas como "p.1-2" idênticas. |
| 4.1 | Temos atestado de obra hospitalar / gases medicinais? | OK (recusa correta) | — | Conferido: "hospital" e "medicinal" não aparecem em nenhum dos 161 trechos. Recusa certa, com a aproximação de gases especiais bem sinalizada. |
| 4.2 | E aquela obra de 2021 pro governo do estado? | OK (recusa correta) | — | Conferido: só existe um documento no acervo. Recusa certa. |
| 4.3 | Sala limpa ISO 7 + manutenção predial 5 anos | recuperação | **alta** | A parte de manutenção predial e de ISO 14644/ISO 7 é recusa correta (não existe no acervo). Mas afirmou que o atestado "não traz essa nomenclatura" de sala limpa — traz: "A.6.1. Portas padrão sala limpa" (p.11) e "LUMINÁRIA RETANGULAR SALA LIMPA ... 121 PÇ" (planilha). A analista concluiu que precisa de outro documento com base numa afirmação falsa. |
| 4.4 | Quantos documentos temos no total? | conversa / arquitetura | média | Resposta honesta, mas o sistema não tem caminho para responder uma pergunta de inventário — e essa é uma pergunta que a analista vai fazer sempre. |
| 4.5 | "E sobre aquilo lá, deu certo" | conversa | baixa | Pediu esclarecimento, comportamento certo. Mas o retrieval trouxe 5 trechos de ruído (planilhas de canteiro, portas, ar condicionado) e metade da resposta foi gasta descrevendo esse ruído. |

**Contagem:** 7 turnos com problema de gravidade alta, 3 de média, 2 de baixa, 8 sem problema.

---

## 3. Padrões encontrados, por causa raiz

### P1. Filtros estruturados inventados pela interpretação zeram a busca
**Turnos: 1.3, 3.3 (e provavelmente 4.2, onde o resultado por acaso é o certo).**

Este é o achado de causa raiz mais importante do documento, e ele é reproduzível de forma determinística.

O `PROMPT_INTERPRETAR` (`prompts.py`) pede ao LLM um campo `tipo_documento` com o enum `"edital" | "ata" | "resultado" | null`. O único documento indexado tem `tipo = 'atestado'` — que não está no enum. Ou seja: **qualquer valor de `tipo_documento` que o modelo produza garante zero resultados.** Confirmado na prática:

```
tools/perguntar.py "contratante cnpj vigencia do contrato" --tipo edital --so-busca
  -> Nenhum trecho atingiu o piso de relevância.
tools/perguntar.py "contratante cnpj vigencia do contrato" --so-busca
  -> 5 trechos, todos corretos
```

O turno 1.3 diz "o edital que eu tenho aqui"; o 3.3 diz "envelope de habilitação". São exatamente as perguntas que induzem o interpretador a preencher o filtro. O mesmo vale para `orgao`: o valor gravado é `Instituto BioPharma`, e `--orgao "Instituto/BioPharma"` também devolve zero.

Agrava: no `agent.py`, o nó de refinamento troca a `consulta` mas **mantém `interpretacao.filtros` intactos** (`self.searcher.buscar(nova_consulta, interpretacao.filtros, self.top_k)`). Se o filtro é o que zerou, refinar não tem como salvar — é uma segunda chamada paga que nasce condenada.

### P2. `top_k = 5` corta a última peça de respostas que precisam de N trechos homogêneos
**Turnos: 1.2, 2.1, 4.3.**

No 1.2 as cinco tabelas de área competem entre si e uma delas (3º pavimento) fica em 6º lugar, atrás de um trecho de ALVENARIA. Reproduzido:

```
"e a area disso, quantos m2 tinha a obra?" --so-busca          -> 3º pavimento FORA
"e a area disso, quantos m2 tinha a obra?" --so-busca --top-k 8 -> 3º pavimento na posição 6
```

No 2.1 a seção `REVESTIMENTOS > PISO` está partida em duas janelas de tabela (chunks 99 e 100, mesma seção, mesmas páginas). Só a segunda foi recuperada, e é a que **não** tem P01/P02/P03. No 2.2, com uma pergunta mais focada, as duas vieram — prova de que o problema é orçamento de trechos, não indexação.

### P3. Pergunta com dois assuntos recebe uma consulta só e um orçamento só
**Turno 4.3 (uma ocorrência — é anedota até aparecer de novo, mas com causa clara).**

A pergunta juntava climatização de sala limpa ISO 7 e manutenção predial de 5 anos. Uma única consulta virou um vetor médio dos dois assuntos, o top_k inteiro foi para climatização, e os dois trechos que dizem literalmente "sala limpa" não entraram. Comprovado: `--so-busca "sala limpa"` devolve os dois; a pergunta original com `--top-k 8` não devolve nenhum.

### P4. Não existe memória de conversa
**Turnos: 1.2, 2.4, 4.5.**

`AgenteLicitacoes.responder(pergunta)` é sem estado. Cada turno reinterpreta a pergunta do zero. "E a área disso" (1.2), "o sistema de gases que vc mencionou antes" (2.4) e "aquilo lá" (4.5) chegam ao interpretador sem antecedente. No 4.5 o sintoma foi visível (retrieval de ruído puro); no 1.2 e 2.4 ele foi invisível — a resposta parece boa e está incompleta. O sintoma pior é o silencioso.

### P5. Ausência nos trechos é declarada como ausência no acervo
**Turnos: 1.4, 2.1, 2.4, 4.3.**

Quatro respostas afirmam, sobre o acervo, algo que só era verdade sobre os 5 trechos que chegaram: "não há valor consolidado de área total" (há: 5.655,00 m²); "não encontrei quantitativos adicionais de piso" (há: 3.695,36 m²); "não encontrei o número de pontos de consumo" (há: 311); "o atestado não traz a nomenclatura sala limpa" (traz, duas vezes). O `PROMPT_RESPONDER` diz literalmente "se os trechos não contêm a resposta, diga que não encontrou no acervo" — o prompt ensina exatamente essa confusão. **Esta é a falha mais perigosa do sistema hoje**, porque uma recusa errada parece um acerto de honestidade e ninguém vai auditá-la.

### P6. A camada de metadados da CAT (p.1-2) é quase invisível para a busca
**Turnos: 1.2, 1.3, 1.4 (e a omissão do 3.5).**

Os chunks 1, 2 e 3 são a certidão do CAU: chave-valor puro, sem nenhum heading de markdown emitido pelo OCR. Consequência em cadeia: `caminho_secao` vazio → `secao` vazia no banco → o cabeçalho contextual vira só `[Instituto BioPharma CAT 100200 ... | p. 1]`, sem nenhum termo temático → o embedding é dominado pelo boilerplate jurídico da resolução do CAU. É por isso que **os dados mais fortes para licitação do documento inteiro** — 5.655,00 m² de execução de obra, 5.655,00 m² de reforma de edificação, 23.537 kg de estrutura metálica, 625,00 m² de recuperação paisagística, contrato C1 001A-2024, CNPJ do contratante — só aparecem em consultas muito dirigidas, e nunca nas perguntas naturais sobre área.

### P7. Chunks de planilha herdam a seção errada
**Turnos: 2.4, 2.5.**

O chunk que contém os quantitativos de GASES e de HIDRÁULICA está rotulado `Instituto BioPharma > EQUIPAMENTOS E QUADROS ELÉTRICOS - (MDO) > FORNECIMENTO E MONTAGEM DE QUADRO DE DISTRIBUIÇÃO DE CIRCUITOS ELÉTRICOS (QDC)`. Motivo: as divisões `| GASES | | |` e `| HIDRÁULICA | | |` são **linhas de tabela**, e `parsear_blocos` (`src/pharma_ops/chunking.py`) só empilha headings markdown (`RE_HEADING`). O rótulo errado entra no cabeçalho contextual, ou seja, **entra no embedding**, empurrando o chunk para longe de perguntas sobre gases — e no turno 2.5 a analista viu uma fonte sobre quadro elétrico sustentando uma frase sobre compressor.

### P8. A exibição das fontes parece quebrada mesmo quando não está
**Turnos: 1.2, 1.5, 2.2, 3.5, 4.1.**

Dois defeitos somados. (a) A lista mostra só os marcadores citados, então a numeração sai com buracos ([1],[3],[5]); a analista registrou isso como "faltou a fonte [4]". (b) A linha exibida é `orgao · secao · p.X-Y`, e chunks diferentes com a mesma seção e página ficam idênticos — no 3.5 foram três fontes escritas exatamente como "Instituto BioPharma · · p.1-2". Nada disso é alucinação, mas destrói a confiança na rastreabilidade, que é o argumento central do produto.

### P9. `itens_planilha` existe, tem 807 linhas e nunca é consultada
**Turnos: 2.1, 2.4.**

A tabela está criada, populada e indexada. `AgenteLicitacoes` só recebe um `searcher`. As duas piores respostas de quantitativo do teste são exatamente as que um `select` resolveria. O próprio código já reconhece o problema (`src/pharma_ops/chunking.py`, `extrair_linhas_tabela`: "uma planilha de quantitativos precisa de SQL, não de busca vetorial").

### P10. Concisão: o sistema já sabe fazer, quando pedem
**Bom: 1.5, 3.5. Ruim: 2.5, 4.3, 4.5.**

Quando a analista pede formato ("3 linhas", "tipo ficha"), a saída é excelente e colável. Quando não pede, a resposta vira ensaio com títulos em negrito e o número pedido some no meio. O `SYSTEM_AGENTE` não diz nada sobre onde a resposta começa.

---

## 4. Instruções de aumento de precisão

Ordenadas por confiabilidade ganha dividida por esforço. As quatro primeiras são de baixo esforço e resolvem 6 dos 7 turnos de gravidade alta.

---

### I1. Parar de gerar filtros estruturados na interpretação

**Onde:** `src/pharma_rag/agent/prompts.py`, bloco `PROMPT_INTERPRETAR`.

**O que fazer:** enquanto o acervo não tiver metadados confiáveis e um vocabulário fechado de tipos que inclua os tipos reais, o campo `filtros` só destrói recall. Substituir o bloco inteiro por:

```python
PROMPT_INTERPRETAR = """\
Analise a pergunta do usuário e responda APENAS com um JSON válido, sem
comentários, no formato:

{{
  "tipo_fluxo": "consulta_historico" | "analise_edital",
  "consulta": "<termos de busca no acervo, curtos e específicos>",
  "filtros": {{
    "orgao": null,
    "tipo_documento": null,
    "data_inicio": null,
    "data_fim": null
  }}
}}

Use "analise_edital" somente se o usuário enviou um edital para análise.

REGRAS PARA "consulta":
- Escreva os termos que apareceriam NO DOCUMENTO do acervo, não os termos da
  pergunta. "quero comprovar 3000 m² num edital" vira "área construída total
  da obra por pavimento", não "edital 3000 m²".
- Nunca inclua palavras sobre o processo licitatório do usuário (edital,
  envelope, habilitação, proposta, certame) na consulta: o acervo é feito de
  atestados e documentos de obra, não do edital que o usuário tem na mão.
- Não invente filtros. Os quatro campos de "filtros" são sempre null.

Pergunta do usuário:
{pergunta}
"""
```

**Evidência:** turnos 1.3 e 3.3 — duas recusas totais sobre informação que está no acervo e que a busca crua encontra em primeiro lugar.

**Como verificar:** refazer `"tem certeza desse numero? o edital que eu tenho aqui pede comprovacao de pelo menos 3000 m2 de area construida, da pra confirmar se bate?"` e `"quem foi o contratante oficialmente, o cnpj deles, e a vigencia do contrato pra eu colocar no envelope de habilitacao"`. As duas devem deixar de responder "não encontrei nada". A primeira deve passar a citar áreas por pavimento (com I6, deve citar 5.655,00 m²); a segunda deve dar contratante, CNPJ 33.444.555/0001-03 e vigência 07/02/2019–06/02/2020, igual ao turno 3.4.

**Risco:** perde-se a filtragem por órgão e por período, que vai ser necessária quando o acervo tiver dezenas de documentos. Isto é uma medida para o acervo inicial. Registre a reversão como pendência ligada ao momento em que o segundo documento entrar, e nessa hora reintroduza os filtros com um enum de `tipo_documento` gerado a partir de `select distinct tipo from documentos`, não escrito à mão.

---

### I2. Relaxar filtros no refinamento, não só a consulta

**Onde:** `src/pharma_rag/agent/agent.py`, método `responder`, dentro do `while not resultados`.

**O que fazer:** trocar a linha de rebusca para descartar os filtros na segunda tentativa:

```python
            interpretacao.consulta = nova_consulta
            # Segunda tentativa sem filtros: se foi um filtro que zerou a busca
            # (tipo/órgão que não casa com o acervo), refinar só a consulta não
            # tem como salvar — a segunda chamada nasce condenada.
            resultados = self.searcher.buscar(nova_consulta, FiltrosBusca(), self.top_k)
```

**Evidência:** turnos 1.3 e 3.3 gastaram uma chamada de refinamento que não tinha nenhuma chance de mudar o resultado.

**Como verificar:** com I1 revertida temporariamente (ou forçando um filtro no teste), a mesma pergunta que hoje devolve `MSG_SEM_RESULTADOS` deve devolver trechos na segunda tentativa. Barato: um teste unitário com fake searcher que só devolve resultado quando `filtros` está vazio.

**Risco:** baixo. Uma consulta que deveria mesmo ser filtrada pode devolver trecho de outro órgão na segunda tentativa. Como a resposta sempre cita a fonte com o órgão, o usuário vê. Vale mais que a recusa falsa.

---

### I3. Separar "não está nos trechos" de "não está no acervo"

**Onde:** `src/pharma_rag/agent/prompts.py`, blocos `SYSTEM_AGENTE` (regra 3) e `PROMPT_RESPONDER`.

**O que fazer:** em `SYSTEM_AGENTE`, substituir a regra 3 por:

```
3. Se a informação não estiver nos trechos fornecidos, diga que ela NÃO ESTÁ
   NOS TRECHOS RECUPERADOS — nunca que "não está no acervo" e nunca que "o
   documento não menciona". Você enxerga 5 a 8 trechos de documentos que têm
   dezenas de páginas; ausência no seu contexto não é prova de ausência no
   acervo. Formule assim: "não encontrei isso nos trechos recuperados; se for
   decisivo para a proposta, refaça a pergunta usando o termo exato do
   documento (ex.: 'postos de utilização', 'atividade técnica realizada')".
   NÃO complete com conhecimento geral.
```

E em `PROMPT_RESPONDER`, substituir a última linha por:

```
Responda seguindo as regras de citação: toda afirmação factual com [n].
Se os trechos não contêm a resposta, diga que não encontrou NOS TRECHOS
RECUPERADOS — não afirme que a informação não existe no acervo, e não afirme
que a lista que você deu é completa.
```

**Evidência:** turnos 1.4, 2.1, 2.4 e 4.3 — quatro afirmações de ausência que são falsas contra o acervo real, três delas de gravidade alta.

**Como verificar:** refazer `"quais quantitativos de servico aparecem nesse atestado? tipo m2 de piso, forro, essas coisas"`. A frase "não encontrei no acervo quantitativos adicionais de piso/forro" deve sumir e dar lugar a uma ressalva de escopo. E refazer a de sala limpa: a frase "o atestado não traz essa nomenclatura técnica" deve virar "não apareceu nos trechos recuperados".

**Risco:** as respostas ficam um pouco mais hedgeadas e menos assertivas, e o usuário pode ler isso como o sistema "não ter certeza de nada". Contrapeso: combinar com I10, que exige o número direto na primeira linha — a ressalva vai para o fim, não para o começo.

---

### I4. Subir `top_k` de 5 para 8

**Onde:** `src/pharma_rag/retrieval/hybrid_search.py`, `TOP_K_PADRAO = 5` → `TOP_K_PADRAO = 8`; e `tools/perguntar.py`, `p.add_argument("--top-k", type=int, default=5, ...)` → `default=8`.

**O que fazer:** trocar os dois valores. Não mexer em `CANDIDATOS_PADRAO` (o pool já é 40 por ramo, sobra folga).

**Evidência:** turno 1.2, medido: com `--top-k 8` o 3º pavimento entra na posição 6 e a soma passa a fechar. Turno 2.1: a segunda janela da tabela de piso é do mesmo tipo de disputa. Turno 4.3: mais orçamento aumenta a chance de o segundo assunto ser contemplado (mas não resolve — ver I5).

**Como verificar:** `tools/perguntar.py "e a area disso, quantos m2 tinha a obra?" --so-busca` deve passar a listar os 5 pavimentos. Depois, uma chamada paga da mesma pergunta deve devolver 5.187,56 m², não 4.078,56.

**Risco:** custo. São 3 trechos a mais no prompt por chamada; pelo tamanho médio dos chunks deste documento (algo em torno de 250 tokens, estimativa a partir dos totais em `.tmp/acervo_indexado.md`), são ~750 tokens de entrada a mais por pergunta. Também entra mais ruído: no teste com `--top-k 8` apareceram trechos de ALVENARIA e de movimento de terra em pergunta de área. Com I3 e I10 aplicadas, ruído citado é menos danoso que trecho faltando; sem elas, o modelo tem mais material para se distrair.

---

### I5. Quebrar pergunta com múltiplos assuntos em várias buscas

**Onde:** `src/pharma_rag/agent/prompts.py` (`PROMPT_INTERPRETAR`) e `src/pharma_rag/agent/agent.py` (`_interpretar` + `responder`).

**O que fazer:** trocar `"consulta": "<string>"` por `"consultas": ["<string>", ...]` (1 a 3 itens), com a instrução:

```
- Se a pergunta trata de mais de um assunto (ex.: "sala limpa ISO 7" E
  "manutenção predial 5 anos"), devolva UMA consulta por assunto. Nunca junte
  assuntos diferentes numa consulta só.
```

No agente, buscar cada consulta com `top_k` próprio e unir os resultados deduplicando por `chunk.chave`, preservando a ordem de RRF dentro de cada busca.

**Evidência:** turno 4.3. Uma ocorrência só nesta amostra — é anedota em frequência, mas a causa é mecânica e verificável: `--so-busca "sala limpa"` acha os dois trechos, a pergunta composta não acha nenhum nem com `--top-k 8`.

**Como verificar:** refazer a pergunta do 4.3. A resposta deve passar a citar "A.6.1. Portas padrão sala limpa" (p.11) e/ou a luminária de sala limpa (121 peças), mudando a conclusão prática da analista.

**Risco:** mais trechos no contexto (N assuntos × top_k), portanto mais custo por pergunta. Limite duro de 3 consultas. E cuidado: perguntas encadeadas mal decompostas podem gerar consultas redundantes — a deduplicação por `chunk.chave` protege parcialmente.

---

### I6. Reindexar a folha de rosto da CAT como bloco de metadados com seção sintética

**Onde:** `src/pharma_ops/chunking.py` (`parsear_blocos` / `cabecalho_contextual`) ou, mais barato, na etapa de OCR que gera o markdown das páginas 1-2.

**O que fazer:** duas mudanças, nesta ordem de preferência.

1. Fazer o OCR (ou um pós-processamento) emitir headings de markdown para as divisões em caixa alta da certidão que hoje são texto solto: `DADOS DO PROFISSIONAL`, `DADOS DOS REGISTROS DE RESPONSABILIDADE TÉCNICA-RRT`, `DADOS DO CONTRATO`, `ATIVIDADE TÉCNICA REALIZADA`, `ENDEREÇO DA OBRA/SERVIÇO`, `INFORMAÇÕES IMPORTANTES`. Isso preenche `caminho_secao` e o cabeçalho contextual passa a carregar "ATIVIDADE TÉCNICA REALIZADA", que é o termo temático que falta.
2. Separar em chunk próprio o bloco `ATIVIDADE TÉCNICA REALIZADA` — hoje ele está espremido no chunk 2, entre o endereço do contratante e o boilerplate da Lei 8.666. É lá que estão os números certificados:

```
2.1.1 - Execução de obra , 5655.00 m²
2.1.2 - Execução de reforma de edificação , 5655.00 m²
2.2.4 - Execução de estrutura metálica , 23537.00 kg
2.6.2 - Execução de recuperação paisagística , 625.00 m²
```

Descartar do embedding (mantendo no texto de exibição) o parágrafo de "INFORMAÇÕES IMPORTANTES", que é lei genérica do CAU e não diz nada sobre esta obra.

**Evidência:** turnos 1.2, 1.3, 1.4 e a omissão do 3.5. Nenhuma pergunta natural sobre área recupera este trecho. Medido: `--so-busca "qual a area total construida da obra, somando todos os pavimentos" --top-k 8` não traz a p.1-2; só `"atividade tecnica realizada execucao de reforma de edificacao area"` traz, e na posição 7.

**Como verificar:** depois de reindexar, `--so-busca "area total construida da obra"` deve trazer o chunk da atividade técnica no top 3. Depois, na chamada paga, a pergunta dos 3.000 m² deve responder "sim, bate — a CAT certifica 5.655,00 m² de execução de obra e de reforma de edificação", que é o número que a comissão de licitação vai aceitar, em vez de uma soma de tabelas de pavimento.

**Risco:** exige reprocessar o documento e regerar embeddings (custo de API, pequeno para 161 chunks). Se a regra de headings for feita por heurística de caixa alta, ela vai disparar em falso em outros documentos — teste contra o próximo documento antes de generalizar. E qualquer mudança de `conteudo` muda o `content_hash`, então o incremental vai re-embeddar os chunks tocados; é o comportamento correto, mas conte com isso.

---

### I7. Corrigir a seção herdada em planilhas

**Onde:** `src/pharma_ops/chunking.py`, função `parsear_blocos`.

**O que fazer:** tratar como divisão de seção a linha de tabela em que só a primeira célula tem conteúdo e ela está em caixa alta — o padrão `| GASES | | |`, `| HIDRÁULICA | | |`, `| VÁLVULAS/EQUIPAMENTOS - ( MDO ) | | |`. Quando reconhecida, empilhar como subseção no `caminho_secao` em vez de deixar o bloco herdar o heading anterior.

**Evidência:** turnos 2.4 e 2.5. O chunk que responde "quantos pontos de gás" está rotulado como quadro de distribuição elétrica. O rótulo entra no cabeçalho contextual e, portanto, no vetor.

**Como verificar:** depois de reindexar, `--so-busca "quantos pontos de consumo de gases especiais foram instalados"` deve trazer o chunk da p.45 no top 3 (hoje ele só aparece com a formulação "postos de utilização", e nas posições 4-5). E a fonte exibida no turno 2.5 deve deixar de dizer "QUADRO DE DISTRIBUIÇÃO DE CIRCUITOS ELÉTRICOS" para uma frase sobre gases.

**Risco:** heurística de caixa alta em célula de tabela vai produzir falsos positivos (uma descrição de item toda em maiúsculas que ocupe a primeira célula sozinha). Limite o gatilho a linhas curtas — sugestão: até 40 caracteres na primeira célula — e valide contra o documento atual antes de reindexar, comparando o `caminho_secao` gerado com o de hoje, chunk a chunk.

---

### I8. Reescrever a pergunta com o histórico antes de interpretar

**Onde:** `src/pharma_rag/agent/agent.py` (assinatura de `responder`, novo nó) e `prompts.py` (novo prompt).

**O que fazer:** aceitar `historico: list[dict] | None` em `responder` e, quando houver, rodar antes do `_interpretar`:

```python
PROMPT_RESOLVER_REFERENCIA = """\
Reescreva a última pergunta do usuário como uma pergunta autossuficiente,
resolvendo pronomes e elipses com o que já foi dito na conversa. Não responda
à pergunta, não acrescente informação nova, não invente contexto. Se a
pergunta já for autossuficiente, devolva-a sem alterações. Se não houver
contexto suficiente para resolver a referência, devolva-a sem alterações.
Responda APENAS com a pergunta reescrita.

Conversa até aqui:
{historico}

Última pergunta:
{pergunta}
"""
```

O `tools/perguntar.py` em modo interativo já tem o laço; basta acumular os pares pergunta/resposta e passar adiante.

**Evidência:** turnos 1.2 ("e a área disso"), 2.4 ("o sistema de gases que vc mencionou antes"), 4.5 ("aquilo lá"). Nos três a busca partiu de uma pergunta sem referente.

**Como verificar:** em modo interativo, perguntar 1.1 e depois "e a área disso, quantos m2 tinha a obra?". A consulta gerada deve conter "Instituto BioPharma" e "área construída", e o retrieval deve trazer as tabelas de área mais o bloco da atividade técnica.

**Risco:** mais uma chamada de LLM por turno (custo e latência). E o modo de falha novo é ruim: uma reescrita que enfia contexto errado numa pergunta que mudou de assunto contamina o retrieval sem deixar rastro. Por isso o prompt manda devolver a pergunta intacta na dúvida — e vale registrar em log a pergunta original e a reescrita, sempre.

---

### I9. Ligar `itens_planilha` a um caminho de consulta

**Onde:** `src/pharma_rag/db/repository.py` (novo método) e `agent.py` (nova dependência opcional).

**O que fazer:** expor um `buscar_itens_planilha(termo, documento_id=None)` que faz `ilike` sobre `array_to_string(celulas, ' ')` e devolve as linhas com página e seção. Injetar no agente e chamar quando a pergunta contiver marcadores de quantidade ("quanto", "quantos", "quantitativo", "total de", "m²", "unidades"). O resultado entra no contexto como trechos numerados normais, para continuar rastreável por [n].

**Evidência:** turnos 2.1 e 2.4 — as duas piores respostas de quantitativo do teste. A tabela tem 807 linhas populadas e zero consultas. Turno 2.4: 144 + 167 reguladores de 2º estágio estão lá.

**Como verificar:** `"quantos pontos de consumo de gases foram instalados"` deve passar a citar os 144 em parede e 167 em totem, com a página 45.

**Risco:** maior dos dez. (a) O formato da planilha deste documento coloca a descrição numa linha e a quantidade na linha seguinte, por bitola (`| Ø1/2" | CJ | 144,00 |`), então um `SUM` ingênuo dá número errado — e número errado com cara de certo é exatamente o que este projeto existe para evitar. Comece por **listar as linhas casadas**, sem somar nada, e só depois avalie agregação. (b) Aumenta a superfície de código antes de existir um segundo documento para validar o formato. Se for para adiar alguma instrução desta lista, adie esta.

---

### I10. O número pedido na primeira linha; e consertar a exibição das fontes

**Onde:** `prompts.py` (bloco `ESTILO` do `SYSTEM_AGENTE`) e `tools/perguntar.py` (`_mostrar_resposta`).

**O que fazer.** No `SYSTEM_AGENTE`, substituir o bloco `ESTILO` por:

```
ESTILO:
- Responda em português brasileiro, direto e objetivo;
- A PRIMEIRA linha responde a pergunta. Se pediram um número, ele vem na
  primeira linha, com a citação [n]. Detalhamento, ressalvas e recomendações
  vêm depois, nunca antes;
- Sem títulos em negrito quando a resposta cabe em um parágrafo;
- Ao comparar um novo edital com o histórico, aponte riscos e precedentes com
  a respectiva citação [n].
```

Em `tools/perguntar.py`, na listagem de fontes, incluir um discriminador para chunks que compartilham seção e página. Hoje a linha é `[{c.marcador}] {c.orgao} · {c.secao} · p.{...}`; acrescentar as primeiras palavras de `c.trecho` (o campo já existe em `Citacao` e traz 200 caracteres do corpo) resolve o caso do turno 3.5, em que três fontes saíram escritas de forma idêntica.

Sobre os buracos na numeração ([1],[3],[5]): eles são consequência correta de `extrair_citacoes` mostrar só o que foi citado. Não mexa na lógica; acrescente uma linha na saída dizendo quantos trechos foram recuperados e quantos foram efetivamente citados (ex.: "Fontes: 3 citadas de 5 trechos recuperados"). Isso transforma um aparente bug em informação útil de calibração.

**Evidência:** concisão — turnos 2.5, 4.3, 4.5 (contra os acertos 1.5 e 3.5). Exibição — turnos 1.2, 1.5, 2.2, 3.5, 4.1.

**Como verificar:** refazer `"qual foi o prazo total de execucao dessa obra, com os aditivos?"` — a primeira linha deve trazer "270 dias" (hoje o 270 aparece só no fim da primeira frase, depois de duas cláusulas). E refazer a ficha do 3.5: as três fontes de p.1-2 devem ficar distinguíveis.

**Risco:** o de concisão é real — instrução de "primeira linha responde" pode induzir o modelo a comprometer-se com um número antes de checar as ressalvas, que é justamente o que produziu o 4.078,56 do turno 1.2. Só aplique I10 **depois** de I3 e I4 estarem no lugar; caso contrário você vai deixar a resposta errada mais assertiva.

---

## 5. O que NÃO mudar

- **O piso de similaridade em 0,474.** Ele está funcionando. `--so-busca "xyzzy plumbus frobnicate"` devolve zero, e as recusas dos turnos 4.1 e 4.2 (obra hospitalar, obra de 2021) foram conferidas contra o acervo e estão certas. Nenhuma das falhas deste relatório foi causada pelo piso. Baixá-lo para "achar mais" trocaria recusa falsa por resposta com contexto irrelevante, que é pior.
- **A verificação de contrato de citação (`contrato_citacao_ok`, marcadores inválidos, resposta sem citação) em `agent.py` e `perguntar.py`.** Em 20 turnos não houve um único marcador inválido. Vale registrar: o que a analista leu como "faltou a fonte [4]" era numeração com buraco, não alucinação de fonte. O guarda-corpo está fazendo o trabalho dele.
- **A regra de nunca completar com conhecimento geral.** Nenhuma das 20 respostas inventou um dado de obra. O único conhecimento geral que apareceu foi a explicação de RRT vs ART (turno 3.2), que foi correta e útil. Se você for flexibilizar isso, flexibilize de forma explícita e estreita: permitir explicação de conceito regulatório, **desde que marcada como fora do acervo**, e jamais para número, data, valor, área ou nome próprio.
- **A busca híbrida com fusão RRF.** Ela é o motivo de "sala limpa" e "climatização" acharem o trecho certo — a parte léxica está carregando termos que o vetor sozinho perderia. Não substitua por busca puramente vetorial.
- **O cabeçalho contextual determinístico dos chunks** (`cabecalho_contextual`). É barato e funciona: as respostas conseguiram atribuir cada trecho à obra e à seção certas. As instruções I6 e I7 melhoram o que vai dentro dele, não o mecanismo.
- **O tom quando o usuário pede formato.** Turnos 1.5 e 3.5 são o padrão a preservar: texto colável, sem preâmbulo, com as ressalvas no fim. I10 deve puxar as outras respostas para esse padrão, não afastar essas duas dele.

---

## 6. Limites desta avaliação

- **Um documento, um tipo.** O acervo inicial era uma CAT com atestado e planilhas anexas. Nada aqui foi testado contra edital, ata ou resultado de licitação — que são os tipos adicionais suportados pelo sistema. Padrões como P6 (folha de rosto invisível) e P7 (seção herdada em planilha) são reais neste documento e plausíveis em outros, mas não medidos.
- **Vinte turnos, uma persona, uma sessão de teste.** Frequências não são estatística. P3 (pergunta multi-assunto) tem exatamente uma ocorrência; chamei de anedota no texto e mantenho.
- **`--so-busca` não reproduz o que o agente busca.** A ferramenta busca com a **pergunta crua**; o agente busca com a **consulta reescrita pelo interpretador** e com os filtros. Todas as reproduções deste arquivo são, portanto, aproximações — e no caso dos turnos 1.3 e 3.3 são aproximações *favoráveis ao sistema*, o que só reforça a conclusão: se a pergunta crua acha e o agente não achou, o problema está entre a pergunta e a busca. Mas não observei diretamente nenhuma consulta gerada, porque isso exigiria chamada paga.
- **O piso 0,474 foi calibrado contra este único documento** e contra `openai/text-embedding-3-large` em 1024 dimensões. Ele não sobrevive à troca de modelo de embedding nem, provavelmente, à entrada de um acervo com dezenas de documentos. Recalibre com `tools/avaliar.py --calibrar` quando qualquer um dos dois mudar.
- **Nenhuma instrução deste arquivo foi aplicada e medida antes desta revisão.** As seções "como verificar" são hipóteses testáveis. Onde se pôde medir sem gastar chamada paga (top_k, filtros, presença de termos no acervo), mediu-se e registrou-se o número; onde a verificação exige chamada paga, está escrito como verificação a fazer.
- **Não avaliei latência, custo por pergunta nem o comportamento do fluxo `analise_edital`** — nenhum dos 20 turnos enviou um edital para análise, então o `PROMPT_ANALISE_EDITAL_SUFIXO` está completamente sem cobertura de teste.
