"""Upload real (F9): guarda o PDF e roda o pipeline de indexação em segundo plano.

Só ORQUESTRA o que já existe — nenhuma lógica de extração/RAG é reescrita aqui:

    1. triagem     tools/triar_documentos.triar (regex no texto nativo, sem custo):
                   título pelo CONTEÚDO, nunca pelo nome do arquivo (lote de 28/09)
    2. extração    solufarma.extracao.processar  (PÁGINA ESCANEADA = OCR VIA VLM, PAGO)
    3. chunks      solufarma.chunking.chunkar_documento(doc, titulo=<da triagem>)
    4. cadastro    Storage (tools/upload_documento.enviar) + cadastrar_documento +
                   traduzir_chunks + upsert_chunks + gravar_itens_planilha
                   — o mesmo roteiro do tools/indexar.py
    5. embeddings  gerar_embeddings_pendentes (PAGO; marca o documento 'indexado')

Os passos são funções de módulo (`ETAPAS`), trocáveis nos testes: nenhum teste
chama rede, OCR ou embedding. Só roda com MODO_DEMO=0; no demo a rota nem chega aqui.

Uma ingestão por vez (executor de 1 thread): o OCR e o embedding são pagos e o
psycopg não deve ser compartilhado entre ingestões simultâneas. O estado dos
envios vive em memória — reiniciar a API perde o histórico da tela, não o
documento (que já está no Storage/banco ou no data/brutos/).
"""

from __future__ import annotations

import hashlib
import re
import sys
import threading
import traceback
import unicodedata
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA_UPLOADS = RAIZ / "data" / "brutos"
PASTA_EXTRAIDOS = RAIZ / "data" / "extraidos"

ROTULOS = {
    "triagem": "Triagem pelo conteúdo",
    "extracao": "Extração do texto",
    "chunks": "Divisão em trechos",
    "cadastro": "Cadastro no acervo",
    "embeddings": "Indexação para busca",
}


@dataclass
class Etapa:
    chave: str
    rotulo: str
    estado: str = "pendente"  # pendente | andamento | ok | erro
    detalhe: str | None = None


@dataclass
class Envio:
    id: str
    arquivo: str
    caminho: Path
    orgao: str
    tipo: str
    criado_em: datetime
    estado: str = "na_fila"  # na_fila | processando | concluido | erro
    etapas: list[Etapa] = field(default_factory=list)
    titulo: str | None = None
    documento_id: str | None = None
    erro: str | None = None
    # Passado de uma etapa para a seguinte (não vai para a tela).
    contexto: dict = field(default_factory=dict, repr=False)

    def etapa(self, chave: str) -> Etapa:
        return next(e for e in self.etapas if e.chave == chave)


_ENVIOS: dict[str, Envio] = {}
_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingestao")


# --------------------------------------------------------------------------
# Etapas reais (imports tardios: o modo demo e os testes não carregam nada disto)
# --------------------------------------------------------------------------


def _caminhos_import() -> None:
    for pasta in (RAIZ / "src", RAIZ / "tools"):
        if str(pasta) not in sys.path:
            sys.path.insert(0, str(pasta))


def etapa_triagem(envio: Envio) -> str:
    _caminhos_import()
    import triar_documentos

    registro = triar_documentos.triar(envio.caminho)
    if registro.get("erro"):
        raise RuntimeError(registro["erro"])
    md = registro.get("metadados") or {}
    sugerido = (md.get("titulo_sugerido") or {}).get("valor")
    # Sem título no conteúdo (escaneado sem texto nativo): órgão informado + nome
    # do arquivo, marcado para conferência — nunca só o nome do arquivo.
    envio.titulo = sugerido or f"{envio.orgao} — {Path(envio.arquivo).stem.replace('_', ' ')}"
    envio.contexto["triagem"] = registro
    paginas_ocr = registro.get("paginas_ocr", 0)
    partes = [f"título: {envio.titulo}"]
    if not sugerido:
        partes.append("título não identificado no texto; confira no Acervo")
    if paginas_ocr:
        custo = registro.get("custo_ocr_estimado_usd", 0)
        partes.append(f"{paginas_ocr} página(s) precisam de OCR (~US$ {custo:.2f})")
    return " · ".join(partes)


def etapa_extracao(envio: Envio) -> str:
    _caminhos_import()
    from solufarma import extracao

    doc = extracao.processar(envio.caminho, PASTA_EXTRAIDOS, verboso=False)
    envio.contexto["extracao"] = asdict(doc)
    return f"{doc.n_paginas} páginas ({doc.n_nativas} com texto nativo, {doc.n_vlm} via OCR)"


def etapa_chunks(envio: Envio) -> str:
    _caminhos_import()
    from solufarma.chunking import chunkar_documento

    chunks, itens = chunkar_documento(envio.contexto["extracao"], titulo=envio.titulo)
    envio.contexto["chunks"] = [asdict(c) for c in chunks]
    envio.contexto["itens"] = itens
    return f"{len(chunks)} trechos" + (f", {len(itens)} linhas de planilha" if itens else "")


def etapa_cadastro(envio: Envio) -> str:
    _caminhos_import()
    import httpx
    import upload_documento

    from solufarma_rag.db.repository import SupabaseChunkRepository, criar_conexao
    from solufarma_rag.ingestion.cadastro import cadastrar_documento, gravar_itens_planilha
    from solufarma_rag.ingestion.traducao import traduzir_chunks

    chunks_brutos = envio.contexto["chunks"]
    paginas = envio.contexto["extracao"].get("paginas") or []
    usou_ocr = any(p.get("estrategia") in ("vlm", "vazia") for p in paginas)
    num_paginas = envio.contexto["extracao"].get("n_paginas") or max(
        (int(c.get("pagina_fim") or 0) for c in chunks_brutos), default=None
    )

    with httpx.Client() as client:
        url, chave = upload_documento._credenciais()
        storage_path, hash_sha256 = upload_documento.enviar(client, url, chave, envio.caminho)

    conn = criar_conexao()
    try:
        documento_id, ja_existia = cadastrar_documento(
            conn,
            storage_path=storage_path,
            hash_sha256=hash_sha256,
            titulo=envio.titulo or envio.arquivo,
            tipo=envio.tipo,
            orgao=envio.orgao,
            num_paginas=num_paginas,
            ocr_aplicado=usou_ocr,
            metodo_extracao="vlm" if usou_ocr else "nativo",
        )
        chunks = traduzir_chunks(
            chunks_brutos, documento_id=documento_id, tipo_documento=envio.tipo, orgao=envio.orgao
        )
        SupabaseChunkRepository(conn=conn).upsert_chunks(chunks)
        if envio.contexto.get("itens"):
            gravar_itens_planilha(
                conn,
                documento_hash=hash_sha256[:16],
                documento_id=documento_id,
                itens=envio.contexto["itens"],
            )
    finally:
        conn.close()
    envio.documento_id = documento_id
    return ("já estava cadastrado; " if ja_existia else "") + f"{len(chunks)} trechos gravados"


def etapa_embeddings(envio: Envio) -> str:
    _caminhos_import()
    from solufarma_rag.db.repository import SupabaseChunkRepository, criar_conexao
    from solufarma_rag.ingestion.embeddings import criar_provedor, gerar_embeddings_pendentes

    conn = criar_conexao()
    try:
        relatorio = gerar_embeddings_pendentes(
            SupabaseChunkRepository(conn=conn), criar_provedor(None)
        )
    finally:
        conn.close()
    return f"{relatorio.embeddados} trechos indexados ({relatorio.embedding_model})"


ETAPAS: dict[str, Callable[[Envio], str]] = {
    "triagem": etapa_triagem,
    "extracao": etapa_extracao,
    "chunks": etapa_chunks,
    "cadastro": etapa_cadastro,
    "embeddings": etapa_embeddings,
}


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------


def _nome_seguro(nome: str) -> str:
    base = unicodedata.normalize("NFKD", Path(nome).name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "documento"
    return base if base.lower().endswith(".pdf") else f"{base}.pdf"


def guardar(conteudo: bytes, nome: str, pasta: Path | None = None) -> Path:
    """Grava o PDF em data/brutos/. Mesmo nome e conteúdo diferente → sufixo com o hash."""
    pasta = pasta or PASTA_UPLOADS
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / _nome_seguro(nome)
    if destino.exists() and destino.read_bytes() != conteudo:
        sufixo = hashlib.sha256(conteudo).hexdigest()[:8]
        destino = destino.with_name(f"{destino.stem}_{sufixo}.pdf")
    destino.write_bytes(conteudo)
    return destino


def criar_envio(caminho: Path, arquivo: str, orgao: str, tipo: str) -> Envio:
    envio = Envio(
        id=uuid.uuid4().hex,
        arquivo=arquivo,
        caminho=caminho,
        orgao=orgao,
        tipo=tipo,
        criado_em=datetime.now(UTC),
        etapas=[Etapa(chave, rotulo) for chave, rotulo in ROTULOS.items()],
    )
    with _LOCK:
        _ENVIOS[envio.id] = envio
    return envio


def executar(envio: Envio) -> Envio:
    """Roda as etapas em ordem. A primeira que falha para o envio (as seguintes ficam pendentes)."""
    envio.estado = "processando"
    for etapa in envio.etapas:
        etapa.estado = "andamento"
        try:
            etapa.detalhe = ETAPAS[etapa.chave](envio)
            etapa.estado = "ok"
        except Exception as exc:  # noqa: BLE001 — o erro vai para a tela, não mata a thread
            etapa.estado = "erro"
            etapa.detalhe = str(exc) or exc.__class__.__name__
            envio.estado = "erro"
            envio.erro = f"{etapa.rotulo}: {etapa.detalhe}"
            traceback.print_exc()
            return envio
    envio.estado = "concluido"
    envio.contexto.clear()  # chunks e extração podem ser grandes; não guardar em memória
    return envio


def enfileirar(envio: Envio) -> None:
    _EXECUTOR.submit(executar, envio)


def obter(envio_id: str) -> Envio | None:
    with _LOCK:
        return _ENVIOS.get(envio_id)


def recentes(limite: int = 20) -> list[Envio]:
    with _LOCK:
        return sorted(_ENVIOS.values(), key=lambda e: e.criado_em, reverse=True)[:limite]
