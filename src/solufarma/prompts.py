"""
prompts.py — Os prompts de transcrição, isolados.

Ficam num módulo próprio porque são a peça mais sensível do pipeline: o
INVARIANTE 4 do CLAUDE.md ("a saída do OCR é Markdown estruturado") é imposto
aqui e em nenhum outro lugar. Se o modelo devolver texto corrido, a hierarquia
`A.1.1 vinílicos` e as colunas da planilha se perdem para sempre — nenhum
chunker recupera isso depois.

Mudou o prompt, mudou a assinatura do cache: `extracao.chamar_vlm` inclui o
hash destes textos na chave, então editar aqui invalida o cache de propósito.
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "Você é um transcritor de documentos técnicos e licitatórios brasileiros. "
    "Sua única função é converter a imagem de uma página em Markdown fiel. "
    "Você NÃO resume, NÃO interpreta, NÃO corrige e NÃO completa informação ausente."
)

USER_PROMPT = """Transcreva a página abaixo em Markdown.

REGRAS DE TRANSCRIÇÃO
1. Fidelidade literal. Erros de grafia do original permanecem. Nunca invente conteúdo para "fechar" uma tabela ou frase.
2. IGNORE completamente (não transcreva): logotipos, marcas d'água, carimbos de registro rotacionados nas laterais, rubricas manuscritas, número de página impresso, linhas de assinatura em branco.
3. Estrutura de seção vira heading, preservando o rótulo literal:
   "A. Arquitetura" -> "## A. Arquitetura"
   "A.1 acabamentos de pisos" -> "### A.1 acabamentos de pisos"
   "A.1.1 vinílicos" -> "#### A.1.1 vinílicos"
   O nível do heading segue a profundidade da numeração.
4. Tabelas viram tabela Markdown com pipes. Uma coluna por coluna visual.
   - Se a linha ocupa duas linhas visuais (texto quebrado), junte numa célula só.
   - Célula vazia fica vazia. NÃO escreva "N/A", não repita a de cima.
   - Preserve o formato numérico brasileiro exatamente: 1.490,00 continua 1.490,00.
5. Se esta página CONTINUA uma tabela iniciada antes, use o CABEÇALHO HERDADO fornecido abaixo como linha de cabeçalho, e comece o markdown com a marca `<!-- TABELA_CONTINUA -->`.
6. Se um parágrafo começa no meio de uma frase (continuação da página anterior), inicie o markdown com `<!-- PARAGRAFO_CONTINUA -->`.
7. Página em branco ou totalmente ilegível: devolva markdown vazio e confianca baixa.

{contexto_herdado}

FORMATO DA RESPOSTA
Responda APENAS com um objeto JSON válido, sem cercas de código, com as chaves:
{{
  "markdown": "a transcrição",
  "secao_corrente": "rótulo da última seção aberta nesta página, ex 'A.1.1', ou null",
  "cabecalho_tabela_final": ["Descrição","Unidade","Quantidade"] ou null,
  "tabela_aberta_no_fim": true/false,
  "confianca": 0.0 a 1.0,
  "observacoes": "problemas de legibilidade, se houver"
}}"""


def montar_contexto(anterior) -> str:
    """
    Monta o bloco de contexto herdado da página anterior.

    INVARIANTE 3 do CLAUDE.md: página não é fronteira semântica. As planilhas
    de quantitativos atravessam páginas sem repetir o cabeçalho das colunas —
    uma página isolada chega ao modelo como três colunas anônimas.

    `anterior` é uma `modelos.Pagina` ou None (primeira página do bloco).
    """
    if anterior is None:
        return "CONTEXTO: esta é a primeira página do documento."

    partes = []
    if anterior.secao_corrente:
        partes.append(f"- Seção aberta na página anterior: {anterior.secao_corrente}")
    if anterior.tabela_aberta_no_fim and anterior.cabecalho_tabela_final:
        colunas = " | ".join(anterior.cabecalho_tabela_final)
        partes.append(f"- CABEÇALHO HERDADO (tabela continua nesta página): {colunas}")

    if not partes:
        return "CONTEXTO: nenhum elemento aberto da página anterior."
    return "CONTEXTO HERDADO DA PÁGINA ANTERIOR\n" + "\n".join(partes)
