"""API fina sobre o agente de licitações da Solufarma.

    MODO_DEMO=1  →  fixtures gravadas (api/fixtures/demo.json): sem LLM, sem banco, custo zero
    MODO_DEMO=0  →  agente real (src/solufarma_rag) + Supabase: CADA PERGUNTA É CHAMADA PAGA

Rodar (da raiz do projeto):
    MODO_DEMO=1 uv run --with-requirements api/requirements.txt uvicorn main:app --app-dir api --port 8000

Os endpoints são `def` (não `async def`) de propósito: o agente e o psycopg são
síncronos, e o FastAPI roda `def` num threadpool — `async def` aqui bloquearia
o event loop durante a chamada ao LLM.

Credenciais: lidas do `.env` da raiz pelo `solufarma_rag.config`, só no modo
real. Nenhuma chave sai deste processo; o navegador recebe no máximo uma URL
assinada de 10 minutos.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import exportar_docx
import ingestao
import mock  # noqa: UP026 — é o api/mock.py local (modo demo), não o pacote "mock"
from schemas import (
    DocumentoOut,
    EnvioOut,
    ExportarDocxIn,
    FonteOut,
    PerguntaIn,
    RespostaOut,
    SaudeOut,
    UploadOut,
)

from solufarma_rag.db.models import TIPOS_DOCUMENTO

MODO_DEMO = os.getenv("MODO_DEMO", "1").strip().lower() not in ("0", "false", "nao", "não", "")
# Latência artificial do modo demo, para a tela de "consultando o acervo" ser vista.
LATENCIA_DEMO_S = float(os.getenv("MODO_DEMO_LATENCIA", "1.4"))
# Prefixo público pelo qual o navegador chega à API (o Next faz proxy de /api/* → :8000).
PREFIXO_PUBLICO = os.getenv("API_PREFIXO_PUBLICO", "/api")
LIMITE_UPLOAD = 50 * 1024 * 1024  # espelha file_size_limit de migrations/002_storage.sql
# Uma conversa de 100 turnos com todas as citações fica bem abaixo disto.
LIMITE_EXPORTAR = 5 * 1024 * 1024
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

if not MODO_DEMO:
    import real as backend
else:
    backend = mock

app = FastAPI(
    title="Solufarma — API do assistente de licitações",
    version="0.1.0",
    description="Camada HTTP sobre `AgenteLicitacoes`. Modo atual: "
    + ("DEMO (fixtures)" if MODO_DEMO else "REAL (chamadas pagas)"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGENS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limitar_exportacao(request: Request, call_next):
    """413 antes de ler o corpo: /exportar/docx não precisa de mais de ~5 MB."""
    if request.url.path == "/exportar/docx":
        try:
            tamanho = int(request.headers.get("content-length") or 0)
        except ValueError:
            tamanho = 0
        if tamanho > LIMITE_EXPORTAR:
            return JSONResponse({"detail": "Conversa grande demais para exportar (limite de 5 MB)."}, 413)
    return await call_next(request)


@app.get("/saude", response_model=SaudeOut)
def saude() -> SaudeOut:
    return SaudeOut(modo="demo" if MODO_DEMO else "real", documentos=len(backend.documentos()))


@app.get("/sugestoes", response_model=list[str])
def sugestoes() -> list[str]:
    """Perguntas de exemplo para a tela vazia do chat (as que têm resposta gravada)."""
    return mock.sugestoes()


@app.post("/perguntar", response_model=RespostaOut)
def perguntar(corpo: PerguntaIn) -> RespostaOut:
    """Pergunta ao acervo. `historico` resolve referências como "e o valor disso?" (I8)."""
    # Só os últimos turnos: o histórico entra inteiro no prompt de reescrita.
    historico = corpo.historico[-6:]
    if MODO_DEMO:
        time.sleep(LATENCIA_DEMO_S)
        return mock.responder(corpo.pergunta, historico)
    try:
        return backend.responder(corpo.pergunta, historico)
    except Exception as exc:  # a tela precisa de uma mensagem, não de um 500 cru
        raise HTTPException(502, f"O agente não conseguiu responder: {exc}") from exc


@app.get("/documentos", response_model=list[DocumentoOut])
def documentos() -> list[DocumentoOut]:
    return backend.documentos()


@app.get("/documentos/{doc_id}/fonte", response_model=FonteOut)
def fonte(doc_id: str) -> FonteOut:
    """URL do PDF original, para o botão "ver a fonte".

    Real: URL assinada do bucket privado `documentos` (`documentos.storage_path`),
    válida por 10 minutos. Demo: o PDF local em `data/`, casado por hash
    (o nome do arquivo em data/ não é confiável — ver DIARIO_DE_BORDO 28/09).
    """
    doc = backend.documento(doc_id)
    if doc is None:
        raise HTTPException(404, "Documento não encontrado no acervo")

    if MODO_DEMO:
        if doc.get("arquivo_local") and (RAIZ / "data" / doc["arquivo_local"]).is_file():
            return FonteOut(
                documento_id=doc_id, titulo=doc["titulo"], disponivel=True,
                url=f"{PREFIXO_PUBLICO}/demo/pdf/{doc_id}",
            )
        return FonteOut(
            documento_id=doc_id, titulo=doc["titulo"], url=None, disponivel=False,
            motivo="No modo demonstração só os PDFs presentes na pasta data/ podem ser abertos. "
            "Em produção, o arquivo vem do Supabase Storage por uma URL assinada.",
        )

    try:
        url = backend.url_assinada(doc["storage_path"])
    except Exception as exc:  # erro do Storage vira 502 com mensagem
        raise HTTPException(502, f"Não foi possível gerar o link do PDF: {exc}") from exc
    return FonteOut(
        documento_id=doc_id, titulo=doc["titulo"], url=url, disponivel=True,
        expira_em_segundos=600,
    )


@app.get("/demo/pdf/{doc_id}", include_in_schema=False)
def pdf_demo(doc_id: str) -> FileResponse:
    if not MODO_DEMO:
        raise HTTPException(404)
    doc = mock.documento(doc_id)
    if not doc or not doc.get("arquivo_local"):
        raise HTTPException(404)
    caminho = RAIZ / "data" / doc["arquivo_local"]
    if not caminho.is_file():
        raise HTTPException(404)
    return FileResponse(
        caminho, media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@app.post(
    "/exportar/docx",
    response_class=Response,
    responses={200: {"content": {MIME_DOCX: {}}, "description": "Documento Word"}},
)
def exportar_docx_rota(corpo: ExportarDocxIn) -> Response:
    """Conversa (ou uma resposta) em .docx. Só formata o que chegou: zero chamada ao LLM."""
    conteudo = exportar_docx.gerar(corpo)
    nome = exportar_docx.nome_arquivo(corpo)
    return Response(
        conteudo,
        media_type=MIME_DOCX,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@app.post("/upload", response_model=UploadOut, status_code=202)
async def upload(
    arquivo: Annotated[UploadFile, File(description="PDF do documento")],
    orgao: Annotated[str, Form(min_length=2, max_length=200)],
    tipo: Annotated[str, Form()] = "atestado",
) -> UploadOut:
    """Recebe um PDF para o acervo (atestados de capacidade técnica e CATs).

    Demo: só valida — nada é guardado nem processado (a tela diz isso).
    Real: guarda em data/brutos/ e enfileira o pipeline de `ingestao.py`
    (triagem → extração → chunks → cadastro → embeddings → classificação).
    A extração de página escaneada (OCR por VLM), os embeddings e a
    classificação SÃO CHAMADAS PAGAS; acima de UPLOAD_MAX_PAGINAS_OCR o envio
    para antes do OCR e espera POST /uploads/{id}/aprovar.
    Acompanhe em GET /uploads/{envio_id}.
    """
    if tipo not in TIPOS_DOCUMENTO:
        raise HTTPException(422, f"tipo deve ser um de {', '.join(TIPOS_DOCUMENTO)}")
    conteudo = await arquivo.read(LIMITE_UPLOAD + 1)
    if len(conteudo) > LIMITE_UPLOAD:
        raise HTTPException(413, "O arquivo passa de 50 MB, o limite do bucket")
    if not conteudo.startswith(b"%PDF"):
        raise HTTPException(415, "O arquivo não é um PDF")
    nome = arquivo.filename or "documento.pdf"

    if MODO_DEMO:
        return UploadOut(
            status="simulado",
            arquivo=nome,
            tamanho_bytes=len(conteudo),
            orgao=orgao,
            tipo=tipo,
            mensagem=(
                "Modo demonstração: o arquivo foi validado, mas nada foi guardado nem "
                "processado. Com a API em modo real, o envio dispara a indexação."
            ),
        )

    caminho = ingestao.guardar(conteudo, nome)
    envio = ingestao.criar_envio(caminho, nome, orgao.strip(), tipo)
    ingestao.enfileirar(envio)
    return UploadOut(
        status="na_fila",
        arquivo=nome,
        tamanho_bytes=len(conteudo),
        orgao=orgao,
        tipo=tipo,
        envio_id=envio.id,
        mensagem="Arquivo guardado. A indexação roda em segundo plano; acompanhe as etapas abaixo.",
    )


def _envio_out(envio: ingestao.Envio) -> EnvioOut:
    return EnvioOut(
        id=envio.id,
        arquivo=envio.arquivo,
        orgao=envio.orgao,
        tipo=envio.tipo,
        criado_em=envio.criado_em,
        estado=envio.estado,
        etapas=[
            {"chave": e.chave, "rotulo": e.rotulo, "estado": e.estado, "detalhe": e.detalhe}
            for e in envio.etapas
        ],
        titulo=envio.titulo,
        documento_id=envio.documento_id,
        erro=envio.erro,
        aguardando_aprovacao=envio.aguardando_aprovacao,
    )


@app.get("/uploads", response_model=list[EnvioOut])
def uploads() -> list[EnvioOut]:
    """Envios desde que a API subiu (mais recente primeiro). Vazio no modo demo."""
    return [_envio_out(e) for e in ingestao.recentes()]


@app.get("/uploads/{envio_id}", response_model=EnvioOut)
def upload_status(envio_id: str) -> EnvioOut:
    envio = ingestao.obter(envio_id)
    if envio is None:
        raise HTTPException(404, "Envio não encontrado (a API pode ter sido reiniciada)")
    return _envio_out(envio)


@app.post("/uploads/{envio_id}/aprovar", response_model=EnvioOut, status_code=202)
def aprovar_upload(envio_id: str) -> EnvioOut:
    """Libera um envio parado pelo teto de OCR (UPLOAD_MAX_PAGINAS_OCR) — ISTO GASTA.

    O envio volta para a fila e roda do início, agora sem o teto.
    """
    envio = ingestao.obter(envio_id)
    if envio is None:
        raise HTTPException(404, "Envio não encontrado (a API pode ter sido reiniciada)")
    if not ingestao.aprovar(envio):
        raise HTTPException(409, "Este envio não está aguardando aprovação")
    return _envio_out(envio)
