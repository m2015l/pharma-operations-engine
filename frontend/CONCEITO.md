# Interface do assistente de licitações — conceito

## Para quem

Analistas de licitação da Solufarma, uso interno, no computador do escritório (desktop, tela ≥ 1280 px). A tarefa é sempre a mesma: **provar com documento** que a empresa já fez algo, como um atestado para o envelope de habilitação, um quantitativo para a proposta ou o CREA de um responsável técnico. A interface existe para encurtar o caminho entre a pergunta e a página do PDF que a sustenta.

## Telas

| Tela | Para quê |
|---|---|
| **Consulta** (`/`) | Conversa com o agente. Cada resposta traz marcadores `[n]` clicáveis; o painel **Fontes**, à direita, mostra de onde cada um saiu (órgão, documento, página, seção, trecho) e tem **Ver a fonte**, que abre o PDF direto na página citada. No rodapé de cada resposta: "N citadas de M trechos recuperados". |
| **Acervo** (`/acervo`) | Lista do que está indexado (título, órgão, tipo, páginas, trechos, data, situação). Deixa claro que só isso entra nas respostas. |
| **Enviar documento** (`/enviar`) | Arrastar o PDF, informar órgão e tipo. Avisa que a extração e a indexação rodam em segundo plano. |

## Fluxo principal

1. A analista pergunta ("a gente já fez obra de implantação de laboratório?").
2. A resposta chega com marcadores; clicar em `[5]` destaca a ficha da fonte 5.
3. **Ver a fonte** abre o PDF na página 3 de 60, dentro da própria tela.
4. Pergunta de acompanhamento ("e o valor disso?"): a tela manda os últimos 6 turnos como `historico`, e o agente reescreve o pronome antes de buscar (I8).
5. A conversa sobrevive à troca de tela (o estado fica no layout raiz); **Nova consulta** zera o histórico, para que um assunto novo não herde o pronome do anterior.

Estados que a tela precisa deixar óbvios, porque são o requisito central do projeto:
- **Nada encontrado no acervo**: rótulo próprio. Não é erro, é a recusa correta.
- **Contrato de citação violado** (`contrato_citacao_ok = false`): faixa âmbar "Resposta sem fonte rastreável. Não use sem conferir." Marcador inexistente aparece riscado.
- **Modo demonstração**: aviso fixo na barra lateral, e cada resposta indica de qual turno auditado ela veio.

## Direção visual

Ferramenta de trabalho, não landing page. A referência é o próprio acervo técnico: papel de repartição frio e tinta azul-marinho, com **uma** cor de destaque, o violeta do carimbo de cartório/CREA.

- **Regra do violeta:** só é violeta o que leva a um documento (marcadores `[n]`, fichas de fonte, "Ver a fonte", régua de citação). Se está violeta, dá para chegar ao PDF a partir dali.
- **Tipografia:** Archivo na interface; **Source Serif 4 no texto das respostas**, porque a resposta é lida como documento e não como mensagem de chat; IBM Plex Mono para páginas, seções e contagens.
- **Assinatura:** a régua de rastreabilidade no rodapé de cada resposta, com M traços (um por trecho recuperado) em que os N citados ficam em violeta. Ela mostra de relance quanto do que a busca trouxe foi de fato usado, e explica os "buracos" na numeração (`[1][2][4]` sem `[3]`) sem parecer bug (I10).
- Tema claro apenas; o foco é desktop (largura mínima de 1024 px).

## Arquitetura

```
navegador ──► Next.js (frontend/, :3000) ──/api/* (rewrite)──► FastAPI (api/, :8000) ──► src/solufarma_rag
                                                                    │                      (AgenteLicitacoes,
                                                                    │                       HybridSearcher,
                                                                    │                       SupabaseChunkRepository)
                                                                    └─► Supabase Storage (URL assinada, 10 min)
```

- **Nenhuma chave no navegador.** O Next só repassa `/api/*` para a API; a API lê o `.env` da raiz. O navegador recebe no máximo uma URL assinada que expira em 10 minutos.
- **A API não reescreve o RAG.** Ela monta as mesmas peças do `tools/perguntar.py` e serializa `RespostaAgente`, acrescentando só o título do documento em cada citação.
- **PDF com pdf.js**, e não com o visualizador do navegador: abre exatamente na página citada e funciona igual com a URL assinada e com o arquivo local do modo demo.

### Endpoints

| Método | Rota | Observação |
|---|---|---|
| GET | `/saude` | modo (`demo`/`real`) e nº de documentos |
| POST | `/perguntar` | `{pergunta, historico:[{pergunta, resposta}]}` → texto, citações, `trechos_recuperados`, `contrato_citacao_ok`… **Paga no modo real.** |
| GET | `/documentos` | acervo indexado |
| GET | `/documentos/{id}/fonte` | URL assinada do bucket privado `documentos` |
| POST | `/upload` | **stub**: valida PDF/tamanho/tipo e devolve 202, mas não guarda nem indexa |
| GET | `/sugestoes` | exemplos para a tela vazia |

### Modo demonstração (`MODO_DEMO=1`, o padrão)

Responde com `api/fixtures/demo.json`, sem LLM, sem banco e sem custo. As citações usam o **conteúdo real** dos chunks indexados. Os textos da auditoria de 17/08 são literais; os do lote 2 (28/09) foram reconstruídos, porque o transcript literal não foi preservado, e contêm só fatos que a auditoria conferiu. Pergunta sem cenário gravado recebe "esta versão só tem as respostas gravadas", nunca uma resposta inventada. No demo, só o PDF do SENAI existe localmente (em `data/`, localizado por hash).

## Como rodar

```bash
# 1. API (da raiz do projeto). MODO_DEMO=0 usa o agente real: cada pergunta é paga.
MODO_DEMO=1 UV_LINK_MODE=copy uv run --with-requirements api/requirements.txt \
  python -m uvicorn main:app --app-dir api --port 8000

# 2. Frontend
cd frontend && npm install && npm run dev      # http://localhost:3000

# Vídeo de demonstração (com os dois rodando, em modo demo)
UV_LINK_MODE=copy uv run --with playwright python frontend/demo/gravar_demo.py
```

`python -m uvicorn`, e não o executável `uvicorn`: nesta máquina o Controle de Aplicativo do Windows bloqueia o `uvicorn.exe` gerado pelo uv.

## Em aberto

- **Envio de documentos é stub.** A ingestão real (`workflows/indexacao.md`) é multi-etapa, tem OCR pago e exige conferência do conteúdo, já que o lote de 28/09 mostrou nomes de arquivo trocados. Falta uma fila de processamento e uma coluna de situação que a tela possa acompanhar.
- **Sem login.** Hoje é uso local. Antes de expor na rede: Supabase Auth, ou pelo menos um proxy com autenticação.
- **Histórico só em memória.** Recarregar a página perde a conversa.
