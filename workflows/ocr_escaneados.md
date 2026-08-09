# Workflow — Extração de texto do acervo (OCR de escaneados)

**Objetivo:** transformar documentos brutos (PDF, ZIP de imagens, imagem solta)
em markdown estruturado por página, com relatório de custo e fila de revisão.

**Marco:** M1 do `BRIEFING.md`. Roda antes do chunking e da calibração.

---

## Pré-requisitos

| Item | Como verificar |
|---|---|
| `.env` com `OPENROUTER_API_KEY` | `uv run python -c "from solufarma import config; config.exigir('extracao')"` |
| Crédito no OpenRouter | openrouter.ai → Credits. Sem saldo a API devolve **402** |
| Slug do modelo confere | openrouter.ai/models → comparar com `OPENROUTER_MODELO` do `.env` |
| Documentos em `data/brutos/` | `ls data/brutos/` |

Se o slug mudar, ajuste **também** `OPENROUTER_PRECO_ENTRADA` / `_SAIDA` — senão
o relatório de custo mente em silêncio.

---

## Execução

```bash
# lote inteiro (padrão: data/brutos/ -> data/extraidos/)
uv run python tools/extract_text.py

# um documento específico
uv run python tools/extract_text.py "data/brutos/SENAI_CETIQT_CAT_576640.pdf"
```

Saída:

| Caminho | Conteúdo |
|---|---|
| `data/extraidos/<nome>.json` | markdown por página + metadados de roteamento |
| `data/relatorios/custo_extracao.md` | tabela de custo por documento |
| `data/relatorios/falhas.jsonl` | documentos que falharam (o lote não para) |
| `.cache_ocr/` | respostas por hash — reexecução não recobra |

---

## O que conferir depois de rodar

1. **Roteamento** — a contagem `N nativas, M via VLM` bate com o esperado?
   No CAT do SENAI: **2 nativas, 58 via VLM**. Se aparecerem 60 nativas, o
   boilerplate não foi detectado e o carimbo passou por texto real.

2. **Carimbo ausente** — procure a chave de impressão no markdown final:
   ```bash
   grep -c "3035566A189DW5W2DWBZ" data/extraidos/*.json   # esperado: 0
   ```

3. **Tabela costurada** — a tabela das págs. 44–45 precisa ter cabeçalho de
   colunas nas duas. Confira no JSON antes de chunkar.

4. **Páginas de baixa confiança** — o CLI lista as abaixo de `0.75`. Elas vão
   para revisão manual, **não** seguem silenciosamente para o RAG.

5. **Idempotência** — rode duas vezes seguidas. A segunda deve reportar
   `US$ 0.0000` e `chamadas_pagas: 0`. Se cobrar de novo, a assinatura do cache
   quebrou (checar `_assinatura_cache` em `extracao.py`).

---

## Falhas conhecidas e o que fazer

| Sintoma | Causa provável | Ação |
|---|---|---|
| `HTTP 401` | chave inválida ou não carregada | conferir `.env`, sem aspas em volta do valor |
| `HTTP 402` | sem crédito no OpenRouter | recarregar em Credits |
| `HTTP 404` no modelo | slug errado ou descontinuado | conferir em openrouter.ai/models e atualizar `.env` |
| Todas as páginas viraram "nativas" | boilerplate não detectado | baixar `SOLUFARMA_LIMIAR_BOILERPLATE` ou subir `SOLUFARMA_MIN_DENSIDADE` |
| Tabela sem cabeçalho na 2ª página | carry-over quebrado | conferir se as páginas VLM contíguas ficaram no mesmo bloco |
| `resposta não era JSON válido` nas observações | modelo saiu do formato | página fica com confiança 0.4 e entra na revisão; se for recorrente, revisar `prompts.py` |

---

## Limiares — são hipótese até o M2

Os valores em `config.py` vieram de **um** documento. Não os trate como
verdade antes do relatório de calibração:

| Constante | Padrão | O que ela decide |
|---|---|---|
| `MIN_CARACTERES_UTEIS` | 220 | volume mínimo para a página ser "digital" |
| `MIN_DENSIDADE` | 0.00035 | caracteres por pixel² — é o teste que pega marca d'água |
| `LIMIAR_BOILERPLATE` | 0.55 | % de páginas em que a linha precisa aparecer |
| `LIMIAR_CONFIANCA_REVISAO` | 0.75 | abaixo disso vai para revisão manual |

Todos são sobrescrevíveis por variável de ambiente (`SOLUFARMA_*`), então dá
para varrer valores no M2 sem editar código.

---

## Próximo passo

`workflows/` → chunking (`tools/chunk_document.py`), depois o **M2 (calibração)**,
que é portão: não indexar nada antes dos limiares serem confirmados sobre 20
documentos reais.
