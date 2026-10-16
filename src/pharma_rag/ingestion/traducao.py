"""Tradutor de chunk — etapa 8 de workflows/indexacao.md.

Converte a saída do chunker (`pharma_ops.chunking`, serializada em
`data/chunks/<stem>_chunks.json`) para o `Chunk` do banco
(`pharma_rag.db.models`).

Os dois modelos têm o mesmo nome e nenhum campo em comum além das páginas. O
mapeamento campo a campo está no §3 do workflow; este módulo é a implementação.

Recebe `dict`, não a dataclass de origem, porque é isso que existe no fluxo
real: `chunk_document.py` grava JSON e a indexação lê JSON. Importar
`pharma_ops.modelos` aqui acoplaria os dois pacotes sem ganho — o contrato
efetivo entre eles é o arquivo.
"""

from __future__ import annotations

import re
from datetime import date

from ..db.models import Chunk

# `9068e5659da77411#c0007` -> 7. O índice vem do id, não da posição na lista,
# para o chunk continuar rastreável ao arquivo de origem mesmo se algum for
# descartado no caminho.
_ID_CHUNK = re.compile(r"#c(\d+)\s*$")


def _indice(chunk_bruto: dict, posicao: int) -> int:
    achado = _ID_CHUNK.search(str(chunk_bruto.get("id", "")))
    return int(achado.group(1)) if achado else posicao


def traduzir_chunk(
    chunk_bruto: dict,
    posicao: int,
    *,
    documento_id: str,
    tipo_documento: str,
    orgao: str,
    data: date | None,
) -> Chunk:
    # `texto`, não `texto_puro`: é a versão COM cabeçalho contextual, e é ela que
    # vai para o embedding. O content_hash precisa cobrir exatamente o texto
    # embeddado, senão o incremental compara maçã com laranja.
    conteudo = chunk_bruto.get("texto") or ""
    if not conteudo.strip():
        raise ValueError(f"chunk {chunk_bruto.get('id')!r} veio sem texto")

    caminho = chunk_bruto.get("caminho_secao") or []
    n_chars = int(chunk_bruto.get("n_chars") or len(conteudo))

    return Chunk(
        documento_id=documento_id,
        chunk_index=_indice(chunk_bruto, posicao),
        tipo_documento=tipo_documento,
        orgao=orgao,
        data=data,
        # Origem é lista (hierarquia de seções), destino é string.
        secao=" > ".join(str(p) for p in caminho),
        # O DDL do destino exige página >= 1; a dataclass de origem tem default 0.
        # Um chunk sem página conhecida vira página 1 em vez de estourar validação
        # no meio de um lote de 161.
        pagina_inicio=max(1, int(chunk_bruto.get("pagina_inicio") or 1)),
        pagina_fim=max(1, int(chunk_bruto.get("pagina_fim") or 1)),
        conteudo=conteudo,
        # ~4 chars por token em português (mesma constante do chunker).
        token_count=max(1, n_chars // 4),
        # NÃO existe na origem — precisa ser calculado. É a base do incremental.
        content_hash=Chunk.calcular_hash(conteudo),
    )


def traduzir_chunks(
    chunks_brutos: list[dict],
    *,
    documento_id: str,
    tipo_documento: str,
    orgao: str,
    data: date | None = None,
) -> list[Chunk]:
    """Traduz o lote inteiro.

    `tipo_documento`, `orgao` e `data` não vêm do chunking — são metadados do
    *documento*, não do *pedaço*, e chegam do cadastro (etapa 7).

    O campo `tipo` da origem (prosa | tabela | metadados) não tem destino no DDL
    atual e é descartado aqui. Vale avaliar guardá-lo: o agente pode querer
    priorizar prosa em pergunta conceitual e tabela em pergunta de quantitativo.
    """
    return [
        traduzir_chunk(
            bruto,
            posicao,
            documento_id=documento_id,
            tipo_documento=tipo_documento,
            orgao=orgao,
            data=data,
        )
        for posicao, bruto in enumerate(chunks_brutos)
    ]
