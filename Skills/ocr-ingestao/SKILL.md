---
name: ocr-ingestao
description: Guia do pipeline de OCR e ingestão de documentos do projeto Solufarma - triagem de PDFs nativos vs escaneados, extração de texto, controle de qualidade e carga no Supabase. Use ao implementar ou depurar rotinas de OCR, ingestão de editais/atas/resultados ou tratamento do acervo histórico.
---

# OCR e Ingestão do Acervo — Guia de Implementação

Padrões para transformar o acervo bruto (PDFs, escaneados) em dados estruturados no Supabase. Design completo em `docs/ARQUITETURA.md`.

## Triagem (sempre o primeiro passo)

1. Para cada PDF, detectar se tem camada de texto nativa (`pypdf`/`pdfplumber` extraem texto?);
2. **PDF nativo** → extração direta (sem OCR, sem custo);
3. **PDF escaneado / imagem** → rota de OCR;
4. Registrar a rota usada nos metadados do documento (`metodo_extracao`).

## Regras de qualidade

- Nunca descartar o arquivo original: guardar no Supabase Storage e referenciar por URL — é a fonte da rastreabilidade;
- Medir confiança do OCR por página; páginas abaixo do limiar entram numa fila de revisão (não seguem silenciosamente para o RAG);
- Preservar números com cuidado: valores, datas, quantidades e códigos de item são o coração de uma licitação — erro de OCR aqui é erro grave;
- Idempotência: reprocessar um documento não pode duplicar registros (usar hash do arquivo como chave natural).

## Extração de metadados via LLM

Após obter o texto, extrair campos estruturados com LLM (saída em JSON validado por Pydantic):
- `tipo_documento` (edital / ata / resultado), `orgao`, `numero_edital`, `data`, `objeto` (resumo), `itens` (lista de equipamentos/produtos com quantidades), `resultado` (quando aplicável: ganhou/perdeu, valores);
- Usar modelo barato para essa extração em massa; validar campos críticos com regex/heurísticas (datas, valores monetários);
- Sumarização: 1 resumo curto (2–3 frases) + 1 resumo estruturado por documento.

## Carga no banco

- Transação por documento: original no Storage → registro em `documentos` → texto por página → metadados → status `pronto_para_embedding`;
- Pipeline com estados explícitos (`recebido → extraido → classificado → indexado → erro`) para retomar de onde parou;
- Logar tudo: documentos processados, falhas, custo de API por lote.

## Armadilhas conhecidas do domínio

- Editais brasileiros costumam ter anexos escaneados no meio de PDFs nativos (tratar página a página, não por arquivo);
- Atas podem ser fotos de documentos assinados — pior caso de OCR;
- Nomes de órgãos variam (abreviações, maiúsculas) — normalizar num dicionário de órgãos desde o início.
