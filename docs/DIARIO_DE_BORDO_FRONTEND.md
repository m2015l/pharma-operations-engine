# Diário de Bordo Frontend — Solufarma Módulo 2

> Registro cronológico do trabalho de frontend (interface para os funcionários da Solufarma consultarem o acervo). Cada sessão relevante ganha uma entrada no topo (mais recente primeiro).
> Formato: data, quem trabalhou, o que foi feito, o que aprendemos, próximos passos.
> O trabalho do RAG (backend, ingestão, auditorias) continua em `docs/DIARIO_DE_BORDO.md`.

---

## 2026-09-29 — Frontend v2 executado (F0–F7 + F9 upload real) (Roger + Claude)

**Contexto:** execução do `frontend/PLANO_V2.md` com as respostas do Roger (seção 8): módulo **Licitações**, logo oficial `frontend/acesso/Logo.png`, .docx da conversa inteira com trecho citado (até ~400 caracteres), sem autor, e login (F8) fora. Durante a sessão veio uma decisão nova do Roger com o gerente: **o acervo é só de resultado final, atestados de capacidade técnica e CATs**; editais e atas não entram. Os textos da interface foram ajustados para isso.

**Resultado em uma linha:** o assistente tem o visual do sistema Contratos, exporta a conversa (ou uma resposta) para Word e o envio de PDF, no modo real, dispara a indexação em segundo plano com progresso na tela.

### O que foi entregue (um commit por fatia na `main`, sem push)

| Fatia | Resumo |
|---|---|
| F0 · Tokens e fonte | Paleta do §2.4 (petróleo `#124443`, teal `#44a18c`, teal-texto `#277160`, fundo Flatly `#ecf0f1`), Lato 300/400/700; saem Archivo, Source Serif e Plex Mono. O lint passou a ignorar o `public/pdf.worker.min.mjs` (código de terceiro que gerava 6 erros) |
| F1 · Moldura | Header branco com o logo oficial, divisor, "Licitações", selo "Demonstração" (tooltip) ou "Sem conexão com a API", navegação em botões outline com o ativo preenchido e borda de 2 px; rodapé discreto. `barra-lateral.tsx` apagada |
| F2 · Consulta | Mestre-detalhe: título grande, card da conversa com o compositor dentro, card de fontes, rolagem própria em cada um. Exemplos em lista estilo Obras, marcadores e fichas em teal, "Nada encontrado" como badge escuro |
| F3 · Acervo | Legenda de situação, busca por título/órgão (sem acento) e filtro por tipo no cliente, badges pílula, "Abrir PDF" em teal |
| F4 · Enviar | Breadcrumb, card de formulário, botão em largura total, texto honesto. Sem seletor de tipo: todo envio é `atestado` |
| Ruff | Os 10 avisos de `ruff check api/` zerados. `import mock` ficou com `# noqa: UP026` (é o `api/mock.py` local) |
| F5 · API .docx | `api/exportar_docx.py` + `POST /exportar/docx`: A4, Lato 11 pt, cabeçalho com logo e "Licitações", rodapé com o aviso e "p. X/Y", markdown mínimo, `[n]` em teal, marcador inválido riscado, tabela das fontes com trecho. Sem autor nos metadados. 413 acima de 5 MB. Abre no Word sem reparo |
| F6 · Botões | "Exportar .docx" no header da Consulta e ".docx" em cada resposta; download por blob com o nome da API; toast |
| F7 · Ativos | `icon.png` recortado do símbolo "S" do logo; título "Licitações · Solufarma" |
| F9 · Upload real | `api/ingestao.py` orquestra o pipeline existente (triagem → extração → chunks com o título da triagem → cadastro/upsert → embeddings), um envio por vez, numa thread. `GET /uploads` e `GET /uploads/{id}` relatam as etapas; a tela Enviar consulta a cada 2 s. No modo demo o envio é simulado e a tela diz isso |

**Testes:** `tests/test_exportar_docx.py` (7) e `tests/test_api_upload.py` (8), todos sem rede e sem custo; as etapas do upload são mockadas. Comando: `UV_LINK_MODE=copy uv run --extra dev --with-requirements api/requirements.txt pytest -q tests/test_api_* tests/test_exportar_*`.

**Screenshots e .docx de exemplo:** `.tmp/frontend_v2/` (10 telas, `consulta-solufarma-*.docx` e `resposta-solufarma-*.docx`). A tela 10 mostra o progresso do modo real com as rotas `/api/*` simuladas no Playwright. O modo real **não** foi executado.

### O que aprendemos

- **A Lato do Google Fonts tem `tabular-nums`**: "111" e "000" medem igual. A Plex Mono pôde sair de vez.
- **Com Lato só em 400/700, `font-semibold` vira 700 sintetizado.** Trocamos por `font-bold` nas telas.
- **O python-docx grava "python-docx" como autor.** O gerador zera `author` e `last_modified_by`.
- **`import main` num teste pode pegar outro módulo `main` do ambiente.** Os testes carregam `api/main.py` por caminho (`importlib`).
- **`scrollIntoView` rola também os ancestrais com `overflow: hidden`.** Na Consulta, a rolagem agora é só do card da conversa.

### Limitações e pontos para validar

- **O upload real roda o OCR (VLM) e os embeddings, e os dois são pagos.** A etapa de triagem mostra a estimativa de custo, mas não pede confirmação antes de seguir. Validar se deve haver confirmação ou um teto de páginas.
- **A etapa de embeddings chama `gerar_embeddings_pendentes`, que processa todos os chunks pendentes do banco**, não só os do documento enviado. Se houver chunks pendentes de outro documento, eles também são embeddados (e cobrados) nesse envio. Para isolar, falta em `src/` um filtro por `documento_id`, e esse ponto de extensão não foi mexido.
- **O estado dos envios vive em memória:** se a API reiniciar, a lista some da tela, mas o documento continua no Storage e no banco. Se o título não for achado no conteúdo, a triagem usa "órgão — nome do arquivo" e avisa para conferir.
- O PDF enviado vai para `data/brutos/` com o nome sanitizado; se já existir um arquivo diferente com o mesmo nome, ganha um sufixo com o hash.
- O favicon foi ampliado de 91 px e fica um pouco suave. Um SVG do símbolo resolveria.
- O `frontend/acesso/` (capturas do Contratos) continua fora do git, porque tem dados internos do cliente.

### Próximos passos

1. **Roger:** validar as decisões acima, principalmente a confirmação de custo antes do OCR no upload real.
2. **Primeiro teste do upload real:** um único atestado nativo, com `MODO_DEMO=0`.
3. **Regravar o vídeo demo** (`frontend/demo/gravar_demo.py` já está com o cursor teal e os seletores conferidos) e atualizar a "Direção visual" do `frontend/CONCEITO.md`.

---

## 2026-09-29 — Plano da v2: padrão visual da Solufarma + exportação .docx (Roger + Claude)

**Contexto:** o cliente pediu duas coisas:
1. **Exportar as respostas para Word.** Roger sugeriu exportar a conversa inteira.
2. **Seguir o visual do sistema interno "Contratos"** da Solufarma, com as 4 capturas em `frontend/acesso/` e a paleta oficial `#124443` (verde-petróleo), `#44a18c` (teal) e `#ffffff`.

Nesta sessão só **estruturamos**, sem mudar código: o resultado é a especificação `frontend/PLANO_V2.md`.

**Resultado em uma linha:** o `frontend/PLANO_V2.md` está pronto para um dev executar em 8 fatias pequenas (F0–F8), com tokens, esboços de tela, contrato da exportação e perguntas abertas.

### O que decidimos (proposta)

- **.docx no backend**, com `python-docx` numa rota `POST /exportar/docx`:
  - O navegador manda os turnos que já tem, com o `RespostaOut` inteiro, e a API só formata. Não há chamada ao LLM, então é custo zero também no modo real.
  - Os motivos: é testável com pytest sobre `demo.json`, não pesa no bundle, é consistente com o resto do projeto em Python e vira `GET /conversas/{id}/docx` quando o histórico for persistido.
  - Dá para exportar a conversa inteira (botão no header da Consulta) ou uma resposta isolada (botão em cada resposta). O nome do arquivo segue o padrão `consulta-solufarma-AAAA-MM-DD-HHMM.docx`.
- **A barra lateral vira header branco** no padrão Contratos:
  - logo, divisor e nome do módulo à esquerda; navegação em botões *outline* à direita, com o item ativo preenchido em `#124443`; borda inferior de 2 px `#124443`;
  - fundo da página `#ecf0f1`, título grande, cards brancos e o rodapé discreto;
  - a Consulta vira mestre-detalhe, como a tela Obras.
- **As decisões de design 1 e 2 foram revogadas** (violeta, fundo azul-acinzentado, Archivo, Source Serif e Plex Mono). Entra **Lato** em tudo.
  - A regra da cor de destaque sobrevive com o **teal**, que marca só o que leva a documento.
  - A régua (3), o pdf.js (4) e o formato desktop claro (5) ficam.
  - O texto da tela de upload (7) vai ser corrigido na fatia F4.

### Achados

- **O Contratos usa Bootstrap 5 com o tema Bootswatch Flatly**, com o *primary* trocado por `#124443`. Os tons auxiliares batem exatamente com os da Flatly (`#ecf0f1`, `#18bc9c`, `#2c3e50`, `#95a5a6`), e a Flatly usa Lato. Falta confirmar com quem mantém o Contratos.
- **Contraste:**
  - branco sobre `#124443` dá 10,86:1 e passa em AA e AAA;
  - branco sobre `#44a18c` dá **3,12:1** e **reprova no AA para texto pequeno**;
  - o `#18bc9c` dos badges do Contratos dá 2,41:1.
  - Solução: o teal oficial fica para bordas, traços e foco, e o texto teal usa `#277160` (5,81:1).
- **Não temos o logo em boa resolução.** O header vai usar um logo em texto até chegar o SVG.

### Próximos passos

1. **Roger:** responder às perguntas abertas da seção 8 do `PLANO_V2.md`. São elas: o nome do módulo (sugestão "Licitações"), o logo e a fonte, a base de usuários do login (a mesma do Contratos ou Supabase Auth), o trecho no .docx, o autor no .docx e o texto do aviso.
2. **Executar as fatias F0 a F6**, que não dependem das respostas. Depois vem a F7 (ativos) e a F8 (login, bloqueada pela pergunta 3).
3. Quando a v2 entrar, atualizar a "Direção visual" do `frontend/CONCEITO.md`, que fica obsoleta, e regravar o vídeo demo.

---

## 2026-09-29 — Primeira versão do frontend profissional + vídeo demo (Roger + Claude)

**Contexto:** o plano original (proposta e ADR-003) previa um protótipo em **Streamlit**. Roger decidiu trocar por um frontend de verdade: *"Não precisa ser um protótipo em streamlit, vamos fazer algo mais profissional desenvolvendo um frontend mesmo"*. O trabalho foi feito numa sessão paralela (agente em segundo plano), que escreveu só em `api/` e `frontend/` e não commitou nada.

**Resultado em uma linha:** conceito, API, frontend e vídeo demo de 75 s prontos. O modo demonstração funciona do começo ao fim, e o modo real foi testado com uma pergunta paga, que veio correta.

### O que foi entregue

| Entrega | Onde | Resumo |
|---|---|---|
| Conceito | `frontend/CONCEITO.md` | Usuários, telas, fluxo, direção visual, arquitetura, como rodar e o que está em aberto |
| API | `api/` | FastAPI fina por cima do agente existente: `main.py`, `mock.py` (modo demonstração), `real.py` (agente real + Supabase), `schemas.py`, `requirements.txt`, `fixtures/demo.json` |
| Frontend | `frontend/` | Next.js 16 (App Router) + TypeScript + Tailwind v4 + shadcn/ui. Três telas: **Consulta** `/`, **Acervo** `/acervo`, **Enviar documento** `/enviar` |
| Vídeo demo | `frontend/demo/demo.mp4` (6,3 MB) e `demo.webm` (7,0 MB) | 75 s, gravado com Playwright pelo script `frontend/demo/gravar_demo.py` |

**Rotas da API:**
- `POST /perguntar`: pergunta com histórico da conversa.
- `GET /documentos`: lista o acervo.
- `GET /documentos/{id}/fonte`: gera uma URL assinada do Supabase Storage (expira em 10 min) para abrir o PDF original.
- `POST /upload`: por enquanto é só uma casca (ver "O que ainda não funciona").

**Segurança:** o navegador só conversa com o Next, que repassa `/api/*` para a API. Nenhuma chave vai para o código do navegador; a API lê o `.env` da raiz.

### O que o vídeo mostra

1. O chat vazio.
2. A pergunta "A gente já fez alguma obra de implantação de laboratório?", com a resposta e as fontes.
3. O clique nas citações [3] e [5] e depois em "Ver a fonte", que abre o PDF do SENAI na página 3 de 60 e passa uma página.
4. Perguntas de seguimento com pronome:
   - "E o valor disso?", que o sistema entende como sendo sobre o SENAI;
   - "vapor puro" e em seguida "E o valor total do contrato desse atestado?", que ele entende como sendo sobre a Ariston.
5. A tela de Acervo e o envio de um PDF sintético na tela de upload.

### Como rodar

A partir da raiz do projeto, em dois terminais:

```
MODO_DEMO=1 UV_LINK_MODE=copy uv run --with-requirements api/requirements.txt python -m uvicorn main:app --app-dir api --port 8000
cd frontend && npm install && npm run dev        # http://localhost:3000
```

- `MODO_DEMO=0` usa o agente real, e **cada pergunta vira uma chamada paga**.
- É preciso usar `python -m uvicorn`, porque o Windows App Control bloqueia o `uvicorn.exe` gerado pelo uv.
- `UV_LINK_MODE=copy` evita os erros de hardlink do OneDrive.

### Testes feitos

- O modo demonstração funciona do começo ao fim.
- No modo real foi feita **uma única pergunta paga**: "Temos algum atestado de vapor puro?". A resposta sobre a Ariston veio correta, com 2 fontes citadas de 3 trechos recuperados, e o contrato de citação funcionou.
- No modo real, a URL assinada do Storage funcionou (expira em 10 min, CORS `*`).

### Respostas do modo demonstração (fixtures)

- Montadas a partir de uma leitura gratuita do banco em 29/09. Todo trecho citado é conteúdo real de chunk.
- As respostas da auditoria de **17/08 são literais**.
- As respostas do lote de **28/09 foram reconstruídas**, porque aquela auditoria guardou só resumos e não as transcrições. Elas usam apenas fatos que a auditoria conferiu nos documentos.
- Cada resposta tem um campo `origem`, e a tela marca todas como "Resposta gravada · auditoria de dd/mm, turno x.y".
- Se a pergunta não tem resposta gravada, a tela diz "esta versão só tem as respostas gravadas". Nunca inventa uma resposta.

### O que ainda não funciona de verdade

- **Upload:** `POST /upload` confere se é PDF, o tamanho (até 50 MB) e o tipo, e devolve 202. **Não guarda nem indexa nada**, e a mensagem de sucesso na tela diz isso. Indexar ainda é feito pelos scripts em `tools/`.
- **"Ver a fonte" no modo demonstração:** só abre o PDF do SENAI, porque é o único arquivo local que confere pelo hash. Os outros três mostram "PDF indisponível nesta versão". No modo real funciona para todos os documentos.
- **Login e histórico:** não tem login, e o histórico da conversa fica só na memória.

### Decisões de design (aguardando aprovação do Roger)

1. **Visual:** fundo cinza-azulado de papel de repartição, texto azul-marinho e uma única cor de destaque, o violeta de carimbo de CREA ou cartório. A regra é que o violeta só aparece no que leva a um documento: citações [n], cartões de fonte e o botão "Ver a fonte".
2. **Tipografia:** as respostas aparecem em fonte serifada (Source Serif 4), para lembrar a leitura de um documento. A interface usa Archivo e os dados usam IBM Plex Mono.
3. **Barra de rastreabilidade:** fica embaixo de cada resposta, com um traço por trecho recuperado e os citados em violeta, por exemplo "3 citadas de 8 trechos recuperados".
4. **Visualizador de PDF próprio (pdf.js)**, dentro do app em vez do visualizador do navegador, para abrir exatamente na página citada. Isso adiciona a dependência `pdfjs-dist`, e o `postinstall` copia o worker para `public/`.
5. **Formato:** só tema claro, pensado para desktop (tela mínima de 1024 px). A conversa continua ao trocar de tela, e o botão "Nova consulta" limpa o histórico para um assunto novo não herdar o pronome do anterior.
6. **Dados de cliente no git:** `api/fixtures/demo.json` tem trechos reais das CATs (nomes, CREA, CNPJ, valores), e o vídeo mostra a página 3 do PDF real do SENAI. **Recomendação:** deixar `demo.json` e os vídeos fora do git (coerente com "não coloque esses atestados no git") e guardar o vídeo no Drive da empresa.
7. **Texto da tela de upload:** o aviso diz que a extração e a indexação rodam em segundo plano, o que descreve o comportamento futuro e não o atual. A mensagem de sucesso deixa claro que ainda não processa nada.

### Achados

- **Nomes de arquivo trocados também em `data/`:** o PDF indexado como SENAI CETIQT (mesmo hash) é o arquivo chamado `SS WHITE CAT 11686-2010 ...pdf`. O arquivo chamado `SENAI CETIQT CAT 576640 ...pdf` tem outro hash. Isso confirma o registro de 28/09 no diário do RAG.
- **`storage_path` no banco também guarda os nomes originais errados**, por exemplo a Ariston aparece como `ATESTADO-CRISTALIA-...pdf`. O conteúdo está correto; só o nome está errado.

### Estado em que as coisas ficaram

- `api/` e `frontend/` existem **só localmente, sem commit**.
- `main` == `origin/main` em `69735d5`.

### Próximos passos

1. **Roger:** assistir ao vídeo e aprovar ou ajustar o visual (decisões 1 a 5 e 7).
2. **Roger:** decidir a decisão 6. Se aprovada, colocar `api/fixtures/demo.json` e `frontend/demo/*.mp4|*.webm` no `.gitignore` e commitar o resto.
3. **Avisar a Diva** que a troca do Streamlit por um frontend próprio muda a forma de um entregável do contrato, e **escrever o ADR** da mudança (substitui o ADR-003 nesse ponto).
4. **Ligar o upload de verdade:** fazer o `POST /upload` chamar o pipeline de `tools/` (extração, chunking, indexação, embeddings), com status de processamento na tela.
5. **Login e histórico persistente** (por exemplo Supabase Auth + tabela de conversas).
6. **"Ver a fonte" no modo demonstração** para os outros três documentos, ou aceitar essa limitação só na demo.
7. **Corrigir os nomes no `storage_path`** e nos arquivos de `data/`, para bater com o conteúdo real.
