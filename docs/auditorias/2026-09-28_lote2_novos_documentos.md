# Auditoria de precisão — lote 2 (3 documentos novos) — 2026-09-28

## 1. O que este arquivo é

Mesmo método da auditoria de 17/08/2026 (`docs/auditorias/2026-08-17_conversas_rag.md`, veredito em `PRECISÃO.md`): um "Agente 1" simulando uma analista de licitações, sem acesso ao acervo nem ao código, fez perguntas reais contra `tools/perguntar.py` (chamadas pagas). Desta vez são 7 turnos em 2 sessões, testando especificamente os 3 atestados novos que entraram no acervo (Ariston, Instituto Butantan, FIOCRUZ/Bio-Manguinhos), além do SENAI CETIQT que já existia.

Cada afirmação factual do transcript foi conferida contra:
- o texto extraído em `data/extraidos/*.json` (`paginas[i].markdown`) e os PDFs brutos em `data/brutos/*.pdf`, ambos lidos integralmente nesta auditoria;
- o conteúdo real indexado em `doc_chunks` (consulta direta ao Supabase, sem custo — `documento_id`s `3bdff192-…` Ariston, `960cb6cf-…` Butantan, `f7cb98d8-…` FIOCRUZ);
- o código (`src/solufarma_rag/agent/agent.py`, `prompts.py`, `citations.py`, `tools/perguntar.py`) para os dois pontos mecânicos pedidos (lacuna de citação e memória de conversa).

Os três PDFs são curtos (2–3 páginas) e têm OCR/extração nativa de baixa qualidade (ligaduras quebradas, "corn" por "com", acentos malformados) — isso é característica real dos documentos de origem e foi tolerado como tal, separado de erro factual de verdade. Confirmado: os chunks em `doc_chunks` têm exatamente essa mesma distorção, ou seja, não é o RAG inventando, é o texto que ele realmente enxerga.

Nenhuma chamada paga nova foi feita para esta auditoria. Nenhum número deste arquivo é estimado, salvo onde está escrito "estimativa".

---

## 2. Veredito turno a turno

| Turno | Pergunta (resumida) | Gravidade | O que aconteceu |
|---|---|---|---|
| 1.1 | Quais atestados temos para plantas farmacêuticas/biotecnológicas? | **sem problema** | Todos os 4 atestados descritos batem com o texto real: FIOCRUZ/Bio-Manguinhos (cabine de criogenia, Sala Classe ISO 8, R$269.125,02, 21/12/2009–30/01/2010, TEP, Márcio Flávio Coppio — confere linha a linha com o chunk); Ariston (vapor puro apirogênico 820 kg/h, R$198.550,00, 04/06/2007–22/11/2007, TEP, mesmo responsável — confere); Instituto Butantan (biotério animais infectados, R$497.840,00, mar–ago/2002, TEP, mesmo responsável — confere); SENAI CETIQT citado sem detalhar escopo, correto por ser fora do escopo da pergunta. |
| 1.2 | Atestado de vapor puro ou água purificada? | **sem problema** | Vapor puro (Ariston, 820 kg/h apirogênico, PLC/IHM 21 CFR Part 11/GAMP, R$198.550,00) confere com o texto exato do chunk. "Não encontrei nada sobre água purificada" é recusa correta — nenhum dos 3 documentos novos menciona o termo; as fontes [2][3] citadas são do SENAI CETIQT (seção Água fria, já validada na auditoria anterior), não invenção. |
| 1.3 | Valor total do contrato desse atestado? (pronome = Ariston, resolvido pelo histórico da sessão 1) | **sem problema** | "R$198.550,00" confere exatamente. O pronome solto foi resolvido para o documento certo (Ariston), não para Butantan nem FIOCRUZ — primeiro teste real de I8, aprovado. Nota à parte: os dois chunks do Ariston (idx 1 e 2) têm `secao=''` e a mesma faixa de página "p.1-2" no banco, então as duas linhas de fonte no terminal saem visualmente parecidas ("ARISTON · · p.1-2" duas vezes) — é o mesmo padrão P6/P8 da auditoria de agosto (folha de rosto da CAT sem heading), não um bug novo, e o discriminador do I10 (primeiras palavras do trecho) já está ativo para diferenciá-las, só não é óbvio à primeira vista. |
| 2.1 | Atestado de obra rodoviária/DER/DNIT? (controle negativo, sem histórico) | **sem problema** | Recusa correta — nenhum dos 4 documentos do acervo trata de rodovia, DER ou DNIT. O único trecho citado ("movimento de terra, aterro e reaterro" do SENAI CETIQT) é real e foi corretamente descrito como sem relação com o pedido. |
| 2.2 | Detalhar escopo do biotério (Instituto Butantan) | **sem problema** | Todos os 6 itens do escopo conferem exatamente com o texto do atestado: 1.1 888 m² divisórias sanitárias alumínio/poliuretano melamina; 1.2 1.120 m² forro autoportante poliuretano/chapa galvanizada; 1.3 42 portas com visor duplo nitrogênio anti-embaçante; 1.4 08 sistemas de intertravamento elétrico; 1.5 965 m de canto sanitário alumínio anodizado; 1.6 06 pass-throughs poliuretano/inox AISI 304. Nenhum número trocado, nenhuma unidade errada. "Não achei HVAC/pressurização" é recusa correta — o documento não menciona isso. |
| 2.3 | Quem foi o responsável técnico? (pronome "essa obra" = Butantan, resolvido pelo histórico da sessão 2) | **sem problema** | "Eng. Márcio Flávio Coppio, Eng. Industrial Mecânico, CREA-SP 068.247.257-6" confere exatamente com o atestado. Pronome resolvido para o documento certo dentro da sessão 2. A lacuna [1][2][4] sem [3] é comportamento correto e documentado — ver §4. |
| 2.4 | Parágrafo pronto pra proposta, atribuindo a experiência à Solufarma | **falha leve** | Ver análise dedicada em §3. Números do escopo corretos e citados; mas a primeira metade do parágrafo atribui a experiência a "Solufarma" sem essa palavra aparecer em nenhum trecho do acervo, e só na "ressalva" (ao final) o sistema identifica corretamente que o executante registrado é TEP. A ordem — afirmação de autoria primeiro, ressalva depois — é um risco real se alguém copiar o parágrafo sem ler até o fim. |

**Contagem:** 6 turnos sem problema, 1 de gravidade leve, 0 de média, 0 de grave.

---

## 3. Achado central — "TEP – Tecnologia em Projetos de Engenharia" vs. "Solufarma" (turno 2.4)

**O que o texto real diz, nos 3 documentos novos, sem exceção:** a empresa executante registrada é **TEP – Tecnologia em Projetos de Engenharia Ltda.**, CNPJ 02.905.709/0001-61, CREA-SP 0561411, sediada em São José dos Campos/SP. O responsável técnico é o mesmo em todos: **Márcio Flávio Coppio**, Eng. Industrial Mecânico, CREA-SP 0682472576. A palavra "Solufarma" **não aparece em nenhum dos 9 chunks indexados** desses 3 documentos (conferido linha a linha contra `doc_chunks`, e contra os PDFs brutos).

**O que o sistema fez:** na primeira metade da resposta, escreveu o parágrafo em nome de "nossa experiência" (= Solufarma, por força do próprio `SYSTEM_AGENTE`, que abre com "Você é o assistente de licitações da Solufarma"), citando corretamente os números do escopo do Butantan com [1][2][3]. Só depois, numa "ressalva importante" separada, identificou que a fonte registra a executante como TEP e não achou vínculo explícito entre as duas razões sociais nos trechos recuperados, recomendando confirmar antes de usar.

**Veredito técnico:** isto não é uma alucinação no sentido estrito do termo — o sistema não inventou nenhum número, nenhuma citação [n] aponta para um trecho que não existe, e a frase que teria a maior chance de enganar (a atribuição a "Solufarma") não veio marcada com nenhuma citação, ou seja, o próprio sistema não a tratou como um fato extraído do acervo. E a autocorreção dentro do mesmo turno é o comportamento certo diante da ambiguidade: identificou a tensão, nomeou a empresa que o documento realmente registra, e recusou-se a afirmar o vínculo sem prova.

Mas a resposta **não é isenta de risco**, por dois motivos concretos, não hipotéticos:
1. **Ordem.** O `ESTILO` do `SYSTEM_AGENTE` manda a ressalva vir depois da resposta, nunca antes (regra do I10 da auditoria de agosto). Aqui isso significa que a frase mais arriscada do texto — a atribuição de autoria — vem primeiro, e o alerta que a desarma vem por último, num pedido explícito de "texto pronto pra colar". É exatamente o risco que o próprio `PRECISÃO.md` já havia previsto ao registrar o I10 ("a instrução de 'primeira linha responde' pode induzir o modelo a comprometer-se... antes de checar as ressalvas") — e agora apareceu na prática, com uma chamada paga real.
2. **Nenhum metadado no banco resolve essa ambiguidade.** `documentos` e `doc_chunks` não têm coluna de empresa executante/contratada — só `licitacoes.orgao`, que guarda o **contratante** (Ariston, Instituto Butantan, FIOCRUZ), corretamente corrigido antes desta auditoria. A distinção TEP vs. Solufarma só existe no texto livre do atestado, então o sistema só pode acertar isso se o LLM ler o trecho com atenção — o que ele fez aqui, mas é uma dependência frágil (um chunk truncado ou um top_k menor poderia ter cortado a frase que menciona "TEP" antes do LLM chegar nela).

**Sobre a hipótese de negócio (o profissional pode ter migrado o CAT para a Solufarma depois):** isso é plausível e comum no setor — CATs seguem o profissional, não a empresa, no sistema CREA/CAU — mas não está em lugar nenhum do acervo indexado hoje, nem no banco, nem nos PDFs. A resposta do sistema foi tecnicamente correta em não afirmar esse vínculo como fato; o ponto de risco é só a ordem de apresentação, não a substância.

**Recomendação prática (fora do escopo desta auditoria, registrando para o PRECISÃO.md):** para pedidos de "texto pronto pra colar" que envolvam atribuição de autoria/experiência, considerar uma regra de estilo separada que force a ressalva de titularidade para ANTES do parágrafo comercial, não depois — o inverso do padrão geral do I10, porque aqui o risco de cópia sem leitura é maior que em uma resposta de consulta comum.

---

## 4. A lacuna de citação [3] no turno 2.3 — confirmado: não é bug

`extrair_citacoes` (`src/solufarma_rag/agent/citations.py`) usa uma regex sobre o texto gerado pelo LLM (`_RE_MARCADOR = re.compile(r"\[(\d+)\]")`) e só materializa como `Citacao` os marcadores que **realmente aparecem no corpo da resposta**. Se o modelo recuperou 8 trechos mas só citou [1], [2] e [4] no texto, a lista de fontes mostra exatamente isso — [3] nunca existiu como citação, só como trecho recuperado e não usado. Isso é comportamento intencional, documentado desde a I10 do `PRECISÃO.md` de agosto ("Não mexa na lógica; acrescente uma linha... 'X citadas de Y recuperados'") e a linha final do turno 2.3 confirma: "3 citadas de 8 recuperados". O código já foi ajustado para isso (`tools/perguntar.py`, comentário explícito em `_mostrar_resposta`: "Os 'buracos' na numeração... são extrair_citacoes mostrando só o que foi citado — comportamento correto, não bug"). Nenhuma ação necessária.

---

## 5. Memória de conversa (I8) — primeiro teste real, aprovado

Dois pronomes soltos foram testados com chamada paga real pela primeira vez:
- Turno 1.3, "esse atestado" → resolvido corretamente para **Ariston** (o assunto do turno 1.2 imediatamente anterior na sessão 1), não para Butantan nem FIOCRUZ, que também estavam na conversa (turno 1.1).
- Turno 2.3, "essa obra" → resolvido corretamente para **Instituto Butantan** (assunto do turno 2.2 na sessão 2), numa sessão nova, sem contaminação da sessão 1.

O mecanismo (`_resolver_referencia` em `agent.py`, chamado quando `historico` não é vazio, usando `PROMPT_RESOLVER_REFERENCIA`) só acumula histórico dentro do laço interativo de um único processo (`tools/perguntar.py`, variável `historico: list[dict]` no `while True`); cada execução separada do CLI começa com histórico vazio. A separação limpa entre sessão 1 e sessão 2 neste transcript (nenhum vazamento de contexto de uma pra outra) é consistente com isso.

**Ressalva de verificação:** esta conclusão é inferida pela correção do resultado final (o pronome apontou pro documento certo nas duas vezes), não por inspeção direta do log `logger.info("Reescrita de referência (I8): original=%r reescrita=%r", ...)` — não há arquivo de log desta execução real disponível no repositório para conferir a pergunta reescrita literal. Registrar como pendência: se for fácil capturar `stderr`/log em execuções futuras do `perguntar.py`, vale preservar para auditorias seguintes (o mesmo cuidado que a auditoria de agosto teve com `.tmp/acervo_indexado.md`).

---

## 6. Padrão que se repete do lote anterior

**P6 (camada de metadados da CAT quase invisível), agora nos 3 documentos novos.** Os 9 chunks das 3 CATs novas têm `secao=''` — nenhum heading de markdown foi emitido pelo OCR para a página 1 (folha de rosto do CREA/CAU). É o mesmo problema já diagnosticado em agosto para o SENAI CETIQT (instrução I6 do `PRECISÃO.md`), só que I6 nunca foi generalizada — foi aplicada (se foi) só ao documento original. Consequência observável nesta auditoria: quando dois chunks do mesmo atestado curto são citados juntos (turno 1.3), a linha de fonte no terminal fica pouco discriminável ("ARISTON · · p.1-2" duas vezes), mesmo com o discriminador do I10 ativo. Não causou nenhum erro factual nesta amostra, mas é o mesmo ponto cego estrutural, agora replicado em 100% dos documentos novos porque todos são CATs curtas do mesmo formato de folha de rosto.

---

## 7. Nota final

**4,5 / 5** para o lote de 3 documentos novos, na mesma metodologia da auditoria de agosto (que deu 3/5 para o SENAI CETIQT sozinho).

- 6 de 7 turnos sem problema (86%), incluindo os dois controles negativos (2.1 DER/DNIT; recusa de água purificada em 1.2), ambos corretos contra o acervo real.
- 1 de 7 turnos com falha leve (14%) — turno 2.4, risco de ordem de apresentação (afirmação antes da ressalva), não erro factual.
- Zero falhas médias ou graves. Zero números errados, zero atribuições de órgão erradas, zero citação apontando para trecho errado, zero recusa falsa (as 2 recusas do lote — água purificada, DER/DNIT — foram conferidas e são recusas verdadeiras).
- As duas causas-raiz mais graves da auditoria de agosto — P1 (filtros estruturados zerando a busca) e P5 (ausência nos trechos declarada como ausência no acervo) — não se manifestaram nesta amostra: nenhuma recusa falsa ocorreu, e os dois controles negativos foram corretos.
- I8 (memória de conversa) funcionou nas duas vezes em que foi exercida com chamada paga real, pela primeira vez.

**Por que não é 5/5:** a amostra é pequena (7 turnos contra 20 em agosto) e não testou várias das situações que mais derrubaram a nota anterior — nenhuma pergunta multi-assunto (I5), nenhum estresse de `top_k` em documento longo, nenhuma pergunta de quantitativo que exercitasse `itens_planilha` (I9) contra os documentos novos, nenhum fluxo `analise_edital`. E o achado do turno 2.4 (ordem afirmação-antes-de-ressalva num pedido de "texto pronto pra colar") é um risco de negócio real, não cosmético — é o tipo de resposta que, se copiada sem o parágrafo final, sai errada. Fica registrado como item de acompanhamento, não como nota mais baixa, porque a resposta, lida inteira, é tecnicamente correta e não afirma nada que o acervo não sustente.
