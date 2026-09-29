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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import mock  # noqa: UP026 — é o api/mock.py local (modo demo), não o pacote "mock"
from schemas import DocumentoOut, FonteOut, PerguntaIn, RespostaOut, SaudeOut, UploadOut

from solufarma_rag.db.models import TIPOS_DOCUMENTO

MODO_DEMO = os.getenv("MODO_DEMO", "1").strip().lower() not in ("0", "false", "nao", "não", "")
# Latência artificial do modo demo, para a tela de "consultando o acervo" ser vista.
LATENCIA_DEMO_S = float(os.getenv("MODO_DEMO_LATENCIA", "1.4"))
# Prefixo público pelo qual o navegador chega à API (o Next faz proxy de /api/* → :8000).
PREFIXO_PUBLICO = os.getenv("API_PREFIXO_PUBLICO", "/api")
LIMITE_UPLOAD = 50 * 1024 * 1024  # espelha file_size_limit de migrations/002_storage.sql

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


@app.post("/upload", response_model=UploadOut, status_code=202)
async def upload(
    arquivo: Annotated[UploadFile, File(description="PDF do documento")],
    orgao: Annotated[str, Form(min_length=2, max_length=200)],
    tipo: Annotated[str, Form()],
) -> UploadOut:
    """STUB — valida o arquivo e devolve 202, mas NÃO guarda nem indexa nada.

    A ingestão real é o pipeline multi-etapa de `workflows/indexacao.md`
    (upload_documento → extract_text → chunk_document → cadastro →
    generate_embeddings), com OCR pago e conferência humana do conteúdo — o
    lote de 28/09 mostrou que o nome do arquivo não basta para catalogar.
    Ligar isto a uma fila de processamento é a próxima etapa.
    """
    if tipo not in TIPOS_DOCUMENTO:
        raise HTTPException(422, f"tipo deve ser um de {', '.join(TIPOS_DOCUMENTO)}")
    conteudo = await arquivo.read(LIMITE_UPLOAD + 1)
    if len(conteudo) > LIMITE_UPLOAD:
        raise HTTPException(413, "O arquivo passa de 50 MB, o limite do bucket")
    if not conteudo.startswith(b"%PDF"):
        raise HTTPException(415, "O arquivo não é um PDF")
    return UploadOut(
        status="recebido_stub",
        arquivo=arquivo.filename or "documento.pdf",
        tamanho_bytes=len(conteudo),
        orgao=orgao,
        tipo=tipo,
        mensagem=(
            "Arquivo validado. A indexação automática ainda não está ligada: nesta versão "
            "o documento não é guardado nem processado."
        ),
    )
