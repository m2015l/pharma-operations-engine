# Diário de Bordo Frontend — Solufarma Módulo 2

> Registro cronológico do trabalho de frontend (interface para os funcionários da Solufarma consultarem o acervo). Cada sessão relevante ganha uma entrada no topo (mais recente primeiro).
> Formato: data, quem trabalhou, o que foi feito, o que aprendemos, próximos passos.
> O trabalho do RAG (backend, ingestão, auditorias) continua em `docs/DIARIO_DE_BORDO.md`.

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
