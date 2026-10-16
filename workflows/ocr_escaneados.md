# Workflow — Extração de texto do acervo (OCR de escaneados)

**Objetivo:** transformar documentos brutos (PDF, ZIP de imagens, imagem solta)
em markdown estruturado por página, com relatório de custo e fila de revisão.

**Marco:** M1 do `BRIEFING.md`. Roda antes do chunking e da calibração.

---

## Pré-requisitos

| Item | Como verificar |
|---|---|
| `.env` com `OPENROUTER_API_KEY` | `uv run python -c "from pharma_ops import config; config.exigir('extracao')"` |
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
uv run python tools/extract_text.py "data/brutos/INSTITUTO_BIOPHARMA_CAT_100200.pdf"
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
   Na CAT 100200 do Instituto BioPharma: **2 nativas, 58 via VLM**. Se aparecerem 60 nativas, o
   boilerplate não foi detectado e o carimbo passou por texto real.

2. **Carimbo ausente** — procure a chave de impressão no markdown final:
   ```bash
   grep -c "0000000A000AA0A0AAA0" data/extraidos/*.json   # esperado: 0
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
| Todas as páginas viraram "nativas" | boilerplate não detectado | baixar `PHARMA_OPS_LIMIAR_BOILERPLATE` ou subir `PHARMA_OPS_MIN_DENSIDADE` |
| Tabela sem cabeçalho na 2ª página | carry-over quebrado | conferir se as páginas VLM contíguas ficaram no mesmo bloco |
| `resposta não era JSON válido` nas observações | modelo saiu do formato | página fica com confiança 0.4 e entra na revisão; se for recorrente, revisar `prompts.py` |
| `Resposta cortada ou fora do formato em N tentativa(s)` nas observações | a resposta bateu no teto de 8.000 tokens (o modelo degenera e enche o resto de espaços) ou não era JSON | desde 09/10 o `chamar_vlm` repete sozinho (até 2 vezes) e **não grava a resposta ruim no cache**. Se a mensagem aparecer, as 3 tentativas falharam: a página fica com confiança 0.4 e **o documento não deve ser indexado** antes de rodar o `extract_text.py` de novo, que tenta só essa página. Extração feita **antes de 09/10** pode ter resposta cortada no cache (`tokens_saida` = 8000): apagar a entrada em `.cache_ocr/` e rodar de novo |
| Refazer uma página fez as seguintes serem pagas de novo | o contexto herdado da página anterior entra na chave do cache; mudou a página N, a N+1 perde o cache, e assim por diante | é o comportamento correto, só caro. Para trocar uma página isolada sem reler as demais, chamar `extracao.chamar_vlm` com a mesma imagem e o mesmo `prompts.montar_contexto` e substituir só essa página no JSON de `data/extraidos/` |
| `HTTP 403 Key limit exceeded` | teto mensal da **chave** (não da conta) | openrouter.ai/settings/keys → editar a chave → Credit limit. Conferir também o saldo em Credits: limite acima do saldo não adianta |

**Custo real medido (07/10, 382 páginas, `anthropic/claude-sonnet-5`):** US$ 0,022 a
0,034 por página via VLM, contra US$ 0,016 da estimativa do `triar_documentos.py`.
Planilhas densas ficam no topo da faixa. O painel do OpenRouter demora alguns minutos
para contabilizar as últimas chamadas.

---

## Folha escaneada com OCR antigo embutido (desde 09/10)

Muitos PDFs do acervo são folhas escaneadas com uma camada de texto que o scanner
embutiu. Esse texto tem volume e densidade de texto digitado, passa na dupla
condição do roteamento e chega ao acervo com erro de grafia em nomes de profissionais
e razões sociais.

Agora a página que é **uma imagem cobrindo 85% ou mais da folha** vai para o VLM
mesmo tendo texto (`formatos.paginas_escaneadas`, `extracao.desviar_ocr_embutido`).
O CLI avisa: `OCR antigo embutido: N página(s) nativa(s) desviada(s) para o VLM`.

- Página realmente digital não é afetada (medido: as 142 páginas de planta industrial digital seguem nativas);
- **Isso encarece documentos novos desse tipo**: cada página desviada custa OCR
  (~US$ 0,03). O `triar_documentos.py` já conta essas páginas na estimativa;
- Para desligar: `PHARMA_OPS_OCR_EMBUTIDO_VLM=0`. Para mudar o corte de 85%:
  `PHARMA_OPS_COBERTURA_ESCANEADA`;
- **Os documentos indexados antes de 09/10 não foram reprocessados.** Os 9 com
  `metodo_extracao = 'nativo'` em folha escaneada (59 páginas) seguem com o texto da OCR antiga. Reextrair custa cerca de
  US$ 2 e muda os chunks: rodar o golden set depois.

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

Todos são sobrescrevíveis por variável de ambiente (`PHARMA_OPS_*`), então dá
para varrer valores no M2 sem editar código.

---

## Próximo passo

`workflows/` → chunking (`tools/chunk_document.py`), depois o **M2 (calibração)**,
que é portão: não indexar nada antes dos limiares serem confirmados sobre 20
documentos reais.
