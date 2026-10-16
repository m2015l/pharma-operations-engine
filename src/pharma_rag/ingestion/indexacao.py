"""Indexação de UM documento — o roteiro comum ao CLI e à API.

    [upload no Storage] → cadastro → tradução dos chunks → substituição dos
    chunks (sem órfãos) → itens de planilha

Quem chama faz o upload (cada um tem seu jeito de achar `tools/upload_documento`)
e passa `storage_path` + `hash_sha256`. Daqui para frente o caminho é um só:
`tools/indexar.py` e `api/ingestao.py` chamam `indexar_documento`, então uma
melhoria aqui (método de extração por página, reindexação sem órfãos, título
sincronizado com o cabeçalho dos chunks) vale para os dois.

Os embeddings NÃO são gerados aqui — ver `embeddings.RepoRestrito`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .cadastro import cadastrar_documento, gravar_itens_planilha
from .traducao import traduzir_chunks

# Quando não há rota por página conhecida, mantém o comportamento anterior a
# 29/09 (o pipeline nasceu para o acervo escaneado) — quem chama deve avisar.
EXTRACAO_DESCONHECIDA = (True, "vlm")


def metodo_extracao(paginas: list[dict]) -> tuple[bool, str] | None:
    """Deriva `(ocr_aplicado, metodo_extracao)` das rotas das páginas extraídas.

    Cada página do JSON de extração traz `estrategia`: `nativo` (texto do PDF),
    `vlm` (OCR por modelo de visão) ou `vazia` (foi ao VLM e voltou sem texto —
    conta como VLM, porque a chamada aconteceu). O resultado:

        todas nativas  -> (False, "nativo")
        todas VLM      -> (True,  "vlm")
        mistura        -> (True,  "misto")

    `documentos.metodo_extracao` é `text` sem CHECK (001_schema_inicial.sql),
    então "misto" é aceito pelo banco. Devolve None se não houver página com
    rota conhecida (ex.: `pendente`) — quem chama decide o fallback.
    """
    rotas = {
        "vlm" if p.get("estrategia") == "vazia" else p.get("estrategia")
        for p in paginas
    } & {"nativo", "vlm"}
    if not rotas:
        return None
    if rotas == {"nativo"}:
        return False, "nativo"
    if rotas == {"vlm"}:
        return True, "vlm"
    return True, "misto"


class TituloDivergente(ValueError):
    """O título pedido não é o que está gravado no cabeçalho dos chunks."""


def resolver_titulo(titulo_pedido: str | None, chunks_brutos: list[dict]) -> str:
    """Decide o título do cadastro a partir dos chunks já gerados.

    O cabeçalho contextual (o que aparece na citação) é gravado no CHUNKING,
    não no cadastro. Se o título do cadastro divergir do que está nos chunks, o
    banco fica com `documentos.titulo` certo e as citações erradas — o bug de
    28/09. Por isso: sem título pedido, herda o dos chunks; com título
    divergente, recusa e manda re-chunkar (chunking é grátis e determinístico).
    """
    titulos = {(c.get("documento") or "").strip() for c in chunks_brutos} - {""}
    if len(titulos) > 1:
        raise TituloDivergente(f"chunks com títulos diferentes entre si: {sorted(titulos)}")
    titulo_chunks = titulos.pop() if titulos else None
    if titulo_pedido is None:
        if titulo_chunks is None:
            raise TituloDivergente("chunks sem campo 'documento'; passe --titulo e re-chunke")
        return titulo_chunks
    if titulo_chunks is not None and titulo_pedido.strip() != titulo_chunks:
        raise TituloDivergente(
            f"--titulo {titulo_pedido.strip()!r} diverge do título embutido nos chunks "
            f"{titulo_chunks!r}. Re-gere os chunks com o título certo:\n"
            "  uv run python tools/chunk_document.py <json de extração> "
            f'--titulo "{titulo_pedido.strip()}"'
        )
    return titulo_pedido.strip()


@dataclass
class ResultadoIndexacao:
    documento_id: str
    ja_existia: bool
    chunks_gravados: int
    orfaos_removidos: int
    itens_gravados: int


def indexar_documento(
    conn,
    *,
    storage_path: str,
    hash_sha256: str,
    chunks_brutos: list[dict],
    itens: list[dict] | None,
    titulo: str,
    orgao: str,
    tipo: str,
    ocr_aplicado: bool,
    metodo: str,
    numero_edital: str | None = None,
    data_abertura: date | None = None,
    num_paginas: int | None = None,
    repo=None,
    cadastrar: Callable = cadastrar_documento,
) -> ResultadoIndexacao:
    """Cadastra o documento e grava seus chunks e itens. Devolve o `documento_id`.

    Reindexação segura: `substituir_chunks_documento` faz upsert + remoção dos
    chunks que o chunking novo não gerou mais, numa transação restrita a este
    documento. `cadastrar_documento` atualiza título e método de extração quando
    o arquivo (mesmo hash) já estava cadastrado.

    `repo` e `cadastrar` são injetáveis para os testes; o padrão é o Supabase.
    """
    if repo is None:
        from ..db.repository import SupabaseChunkRepository

        repo = SupabaseChunkRepository(conn=conn)
    if num_paginas is None:
        # A maior página vista nos chunks é a melhor estimativa disponível.
        num_paginas = max((int(c.get("pagina_fim") or 0) for c in chunks_brutos), default=None)

    documento_id, ja_existia = cadastrar(
        conn,
        storage_path=storage_path,
        hash_sha256=hash_sha256,
        titulo=titulo,
        tipo=tipo,
        orgao=orgao,
        numero_edital=numero_edital,
        data_abertura=data_abertura,
        num_paginas=num_paginas,
        ocr_aplicado=ocr_aplicado,
        metodo_extracao=metodo,
    )
    chunks = traduzir_chunks(
        chunks_brutos,
        documento_id=documento_id,
        tipo_documento=tipo,
        orgao=orgao,
        data=data_abertura,
    )
    removidos = repo.substituir_chunks_documento(documento_id, chunks)
    gravados = 0
    if itens:
        gravados = gravar_itens_planilha(
            conn, documento_hash=hash_sha256[:16], documento_id=documento_id, itens=itens
        )
    return ResultadoIndexacao(
        documento_id=documento_id,
        ja_existia=ja_existia,
        chunks_gravados=len(chunks),
        orfaos_removidos=removidos,
        itens_gravados=gravados,
    )
