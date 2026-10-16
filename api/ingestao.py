"""Upload real (F9): guarda o PDF e roda o pipeline de indexação em segundo plano.

Só ORQUESTRA o que já existe — nenhuma lógica de extração/RAG é reescrita aqui:

    1. triagem       tools/triar_documentos.triar (regex no texto nativo, sem custo):
                     título pelo CONTEÚDO, nunca pelo nome do arquivo (lote de 28/09).
                     Se a estimativa de páginas de OCR passar do teto por envio
                     (UPLOAD_MAX_PAGINAS_OCR, padrão 60), o envio PARA aqui, sem
                     gastar, "aguardando aprovação" (POST /uploads/{id}/aprovar).
    2. extração      pharma_ops.extracao.processar  (PÁGINA ESCANEADA = OCR VIA VLM, PAGO)
    3. chunks        pharma_ops.chunking.chunkar_documento(doc, titulo=<da triagem>)
    4. cadastro      Storage (tools/upload_documento.enviar) +
                     pharma_rag.ingestion.indexacao.indexar_documento — o MESMO
                     roteiro do tools/indexar.py (método de extração por página,
                     reindexação sem órfãos, título igual ao dos chunks)
    5. embeddings    gerar_embeddings_pendentes restrito a ESTE documento (RepoRestrito,
                     o mesmo do generate_embeddings.py --documento-id) — PAGO
    6. classificação pharma_ops.classificacao via LLM (PAGO, ~US$ 0,003). Falha SUAVE:
                     se o LLM falhar, o documento já está indexado e buscável; a
                     etapa fica "pendente" com a instrução de rodar
                     tools/classificar_documentos.py depois.

Os passos são funções de módulo (`ETAPAS`), trocáveis nos testes: nenhum teste
chama rede, OCR ou embedding. Só roda com MODO_DEMO=0; no demo a rota nem chega aqui.

Uma ingestão por vez (executor de 1 thread): o OCR e o embedding são pagos e o
psycopg não deve ser compartilhado entre ingestões simultâneas. O estado dos
envios vive em memória — reiniciar a API perde o histórico da tela, não o
documento (que já está no Storage/banco ou no data/brutos/).
"""

from __future__ import annotations

import hashlib
import os
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
    "classificacao": "Classificação por IA",
}

# Teto de páginas de OCR (VLM, pago) por envio. Acima disso o envio espera
# aprovação explícita antes de gastar. Env: UPLOAD_MAX_PAGINAS_OCR.
MAX_PAGINAS_OCR_PADRAO = 60


def teto_paginas_ocr() -> int:
    try:
        return int(os.getenv("UPLOAD_MAX_PAGINAS_OCR", MAX_PAGINAS_OCR_PADRAO))
    except ValueError:
        return MAX_PAGINAS_OCR_PADRAO


class EtapaAdiada(Exception):
    """A etapa não rodou, mas o envio segue: ela fica 'pendente' com este detalhe."""


class AguardandoAprovacao(Exception):
    """O envio para aqui, sem gastar, até alguém aprovar o custo."""

    def __init__(self, detalhe_etapa: str, mensagem: str):
        super().__init__(mensagem)
        self.detalhe_etapa = detalhe_etapa
        self.mensagem = mensagem


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
    # na_fila | processando | concluido | erro. "Aguardando aprovação" é
    # estado='erro' + aguardando_aprovacao=True: o frontend v2 só conhece os
    # quatro estados e quebraria com um quinto.
    estado: str = "na_fila"
    etapas: list[Etapa] = field(default_factory=list)
    titulo: str | None = None
    documento_id: str | None = None
    erro: str | None = None
    aguardando_aprovacao: bool = False
    ocr_aprovado: bool = False
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
    paginas_ocr = registro.get("paginas_ocr", 0) or 0
    custo = registro.get("custo_ocr_estimado_usd", 0) or 0
    partes = [f"título: {envio.titulo}"]
    if not sugerido:
        partes.append("título não identificado no texto; confira no Acervo")
    if paginas_ocr:
        partes.append(f"{paginas_ocr} página(s) precisam de OCR (~US$ {custo:.2f})")
    detalhe = " · ".join(partes)

    teto = teto_paginas_ocr()
    if paginas_ocr > teto and not envio.ocr_aprovado:
        raise AguardandoAprovacao(
            detalhe,
            f"aguardando aprovação — {paginas_ocr} páginas de OCR, ~US$ {custo:.2f} "
            f"(teto por envio: {teto} páginas; nada foi gasto)",
        )
    return detalhe


def etapa_extracao(envio: Envio) -> str:
    _caminhos_import()
    from pharma_ops import extracao

    doc = extracao.processar(envio.caminho, PASTA_EXTRAIDOS, verboso=False)
    envio.contexto["extracao"] = asdict(doc)
    return f"{doc.n_paginas} páginas ({doc.n_nativas} com texto nativo, {doc.n_vlm} via OCR)"


def etapa_chunks(envio: Envio) -> str:
    _caminhos_import()
    from pharma_ops.chunking import chunkar_documento

    chunks, itens = chunkar_documento(envio.contexto["extracao"], titulo=envio.titulo)
    envio.contexto["chunks"] = [asdict(c) for c in chunks]
    envio.contexto["itens"] = itens
    return f"{len(chunks)} trechos" + (f", {len(itens)} linhas de planilha" if itens else "")


def etapa_cadastro(envio: Envio) -> str:
    _caminhos_import()
    import httpx
    import upload_documento

    from pharma_rag.db.repository import criar_conexao
    from pharma_rag.ingestion.indexacao import (
        EXTRACAO_DESCONHECIDA,
        indexar_documento,
        metodo_extracao,
        resolver_titulo,
    )

    chunks_brutos = envio.contexto["chunks"]
    if not chunks_brutos:
        raise RuntimeError("nenhum trecho de texto foi gerado; nada a cadastrar")
    extracao = envio.contexto["extracao"]
    # Mesmo título do cabeçalho dos chunks (o bug de 28/09 era a divergência).
    titulo = resolver_titulo(envio.titulo, chunks_brutos)
    ocr_aplicado, metodo = metodo_extracao(extracao.get("paginas") or []) or EXTRACAO_DESCONHECIDA

    with httpx.Client() as client:
        url, chave = upload_documento._credenciais()
        storage_path, hash_sha256 = upload_documento.enviar(client, url, chave, envio.caminho)

    conn = criar_conexao()
    try:
        res = indexar_documento(
            conn,
            storage_path=storage_path,
            hash_sha256=hash_sha256,
            chunks_brutos=chunks_brutos,
            itens=envio.contexto.get("itens"),
            titulo=titulo,
            orgao=envio.orgao,
            tipo=envio.tipo,
            ocr_aplicado=ocr_aplicado,
            metodo=metodo,
            num_paginas=extracao.get("n_paginas"),
        )
    finally:
        conn.close()
    envio.documento_id = res.documento_id
    partes = [f"{res.chunks_gravados} trechos gravados (extração: {metodo})"]
    if res.ja_existia:
        partes.insert(0, "já estava cadastrado; título e método atualizados")
    if res.orfaos_removidos:
        partes.append(f"{res.orfaos_removidos} trechos antigos removidos")
    return "; ".join(partes)


def etapa_embeddings(envio: Envio) -> str:
    _caminhos_import()
    from pharma_rag.db.repository import SupabaseChunkRepository, criar_conexao
    from pharma_rag.ingestion.embeddings import (
        RepoRestrito,
        criar_provedor,
        gerar_embeddings_pendentes,
    )

    if not envio.documento_id:
        raise RuntimeError("sem documento_id: o cadastro não terminou")
    conn = criar_conexao()
    try:
        # Só os chunks DESTE documento — nunca os pendentes de outra sessão.
        repo = RepoRestrito(SupabaseChunkRepository(conn=conn), {envio.documento_id})
        relatorio = gerar_embeddings_pendentes(repo, criar_provedor(None))
    finally:
        conn.close()
    return f"{relatorio.embeddados} trechos indexados ({relatorio.embedding_model})"


def etapa_classificacao(envio: Envio) -> str:
    """Classifica o documento por LLM. Qualquer falha vira `EtapaAdiada` (suave)."""
    _caminhos_import()
    comando = f"tools/classificar_documentos.py --documento {envio.documento_id}"
    try:
        import classificar_documentos

        from pharma_ops import classificacao as cl
        from pharma_rag.agent.llm import OpenRouterLLM
        from pharma_rag.db.repository import criar_conexao

        modelo = os.getenv("CLASSIFICACAO_MODELO") or classificar_documentos.MODELO_PADRAO
        conn = criar_conexao()
        try:
            chunks = cl.carregar_chunks(conn, envio.documento_id)
            llm = OpenRouterLLM(model=modelo, json_mode=True, temperatura=0)
            res = cl.classificar_documento(llm, chunks, envio.titulo, modelo=modelo)
            cl.salvar(conn, envio.documento_id, res.classificacao, res.resumo)
        finally:
            conn.close()
    except Exception as exc:
        traceback.print_exc()
        motivo = (str(exc) or exc.__class__.__name__).splitlines()[0][:160]
        raise EtapaAdiada(f"pendente — classificar depois com {comando} ({motivo})") from exc

    c = res.classificacao
    grupo = (c.get("executante_grupo") or {}).get("valor") or "não identificado"
    disciplinas = ", ".join(d["valor"] for d in c.get("disciplinas") or []) or "nenhuma"
    custo = res.uso.get("custo_usd")
    return (
        f"executante: {grupo} · disciplinas: {disciplinas}"
        + (f" · US$ {custo:.4f}" if custo is not None else "")
    )


ETAPAS: dict[str, Callable[[Envio], str]] = {
    "triagem": etapa_triagem,
    "extracao": etapa_extracao,
    "chunks": etapa_chunks,
    "cadastro": etapa_cadastro,
    "embeddings": etapa_embeddings,
    "classificacao": etapa_classificacao,
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


def _etapas_novas() -> list[Etapa]:
    return [Etapa(chave, rotulo) for chave, rotulo in ROTULOS.items()]


def criar_envio(caminho: Path, arquivo: str, orgao: str, tipo: str) -> Envio:
    envio = Envio(
        id=uuid.uuid4().hex,
        arquivo=arquivo,
        caminho=caminho,
        orgao=orgao,
        tipo=tipo,
        criado_em=datetime.now(UTC),
        etapas=_etapas_novas(),
    )
    with _LOCK:
        _ENVIOS[envio.id] = envio
    return envio


def executar(envio: Envio) -> Envio:
    """Roda as etapas em ordem. A primeira que falha para o envio (as seguintes ficam pendentes).

    Duas exceções não são erro: `EtapaAdiada` deixa a etapa 'pendente' com o
    detalhe e segue; `AguardandoAprovacao` marca a etapa como feita e para o
    envio antes da próxima (a que gastaria), com o motivo na próxima etapa.
    """
    envio.estado = "processando"
    for i, etapa in enumerate(envio.etapas):
        etapa.estado = "andamento"
        try:
            etapa.detalhe = ETAPAS[etapa.chave](envio)
            etapa.estado = "ok"
        except EtapaAdiada as exc:
            etapa.estado = "pendente"
            etapa.detalhe = str(exc)
        except AguardandoAprovacao as exc:
            etapa.estado = "ok"
            etapa.detalhe = exc.detalhe_etapa
            if i + 1 < len(envio.etapas):
                envio.etapas[i + 1].detalhe = exc.mensagem
            envio.estado = "erro"
            envio.aguardando_aprovacao = True
            envio.erro = exc.mensagem
            return envio
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


def aprovar(envio: Envio) -> bool:
    """Libera um envio parado pelo teto de OCR e o recoloca na fila. False se não estava parado."""
    with _LOCK:
        if not envio.aguardando_aprovacao:
            return False
        envio.aguardando_aprovacao = False
        envio.ocr_aprovado = True
        envio.estado = "na_fila"
        envio.erro = None
        envio.etapas = _etapas_novas()
        envio.contexto.clear()
    enfileirar(envio)
    return True


def obter(envio_id: str) -> Envio | None:
    with _LOCK:
        return _ENVIOS.get(envio_id)


def recentes(limite: int = 20) -> list[Envio]:
    with _LOCK:
        return sorted(_ENVIOS.values(), key=lambda e: e.criado_em, reverse=True)[:limite]
