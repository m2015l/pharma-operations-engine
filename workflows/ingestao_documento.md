# Workflow: Ingestão de Documento (edital / ata / resultado)

## Objetivo

Transformar um documento bruto (PDF nativo ou escaneado) em registros estruturados no Supabase, prontos para a geração de embeddings. Este é o caminho único de entrada de documentos no sistema — tanto para o upload via Streamlit (modo interativo) quanto para eventual carga em lote via CLI (ver ADR-003).

## Entradas necessárias

- Arquivo do documento (PDF; aceitar também imagens JPG/PNG de páginas);
- Tipo declarado pelo usuário, se houver (edital / ata / resultado) — o pipeline valida/classifica de qualquer forma;
- Credenciais no `.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY` (ou `OPENAI_API_KEY`).

## Ferramentas

| Etapa | Tool | Status |
|-------|------|--------|
| Upload do original para o Storage + registro inicial | `tools/ingest_document.py` | 🔲 a implementar |
| Triagem nativo × escaneado + extração de texto | `tools/extract_text.py` | 🔲 a implementar |
| Classificação + metadados + sumarização via LLM | `tools/classify_and_extract.py` | 🔲 a implementar |
| Chunking estrutural | `tools/chunk_document.py` | 🔲 a implementar |

> Atualize a coluna Status conforme os scripts forem criados. Regras detalhadas de qualidade: skill `ocr-ingestao` (Skills/ocr-ingestao/SKILL.md).

## Sequência

1. **Registrar e armazenar o original**: calcular hash SHA-256 do arquivo; se já existe documento com esse hash, abortar com aviso (idempotência). Subir o original ao Supabase Storage e criar registro em `documentos` com status `recebido`.
2. **Triagem**: tentar extração de texto nativa (PyMuPDF). Densidade de texto boa → seguir. Página sem texto → rota OCR (API Claude com visão) **página a página** (editais têm anexos escaneados no meio de PDFs nativos).
3. **Persistir texto por página** com `metodo_extracao` e confiança; status → `extraido`. Páginas abaixo do limiar de confiança entram na fila de revisão.
4. **Classificar e extrair metadados** via LLM (saída JSON validada por Pydantic): tipo, órgão (normalizado pelo dicionário de órgãos), número do edital, data, objeto, itens/equipamentos, resultado. Gerar os dois resumos (curto + estruturado). Status → `classificado`.
5. **Chunking** estrutural (seções/cláusulas, 500–1000 tokens, overlap 10–15%) com metadados obrigatórios por chunk (documento, seção, página). Status → `pronto_para_embedding`.
6. Encadear o workflow `geracao_embeddings.md` (automático no fluxo interativo do Streamlit; manual/lote via CLI).

## Saídas esperadas

- Original no Storage + registro completo em `documentos` (status `pronto_para_embedding`);
- Texto por página, metadados estruturados e chunks no banco;
- Log da execução (rota usada, páginas OCR, custo de API, falhas).

## Casos de borda e regras

- **Falha em qualquer etapa**: status → `erro` com mensagem; o pipeline deve poder **retomar do estado salvo**, nunca recomeçar do zero silenciosamente;
- **Documento duplicado** (mesmo hash): não reprocessar; informar o usuário qual documento já existe;
- **PDF protegido por senha ou corrompido**: rejeitar com mensagem clara no Streamlit;
- **Modo interativo (Streamlit)**: usuário espera — mostrar progresso por etapa; documentos muito grandes (>100 págs) devem avisar que o processamento continuará em segundo plano;
- **Custos**: logar tokens por chamada; usar modelo barato (Haiku) para classificação/extração em massa.

## Aprendizados

_(registrar aqui rate limits, quirks de API e comportamentos inesperados descobertos durante a implementação)_
