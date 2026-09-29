"""Sobe um documento original para o Supabase Storage.

Uso:
    python tools/upload_documento.py "data/brutos/EDITAL.pdf"
    python tools/upload_documento.py "data/brutos/*.pdf"      # lote
    python tools/upload_documento.py ARQUIVO --listar         # só lista o que já subiu

Etapa 6 de workflows/indexacao.md. Devolve o `storage_path` e o `hash_sha256` —
os dois campos que o passo de cadastro (§4 do workflow) precisa para inserir a
linha em `documentos`.

POR QUE O CAMINHO É <hash>/<nome>:
O prefixo de hash torna a operação idempotente — subir o mesmo arquivo duas
vezes escreve no mesmo lugar, em vez de duplicar 11 MB no bucket. E resolve
colisão de nome: dois órgãos diferentes mandam "edital.pdf" o tempo todo.

O nome legível vem junto porque `storage_path` é o que aparece no botão
"ver a fonte" — um caminho que é só hash torna qualquer depuração cega.
Acentos e espaços são removidos: a chave do objeto vai dentro de uma URL, e
"laboratório ISI.pdf" vira erro de encoding em algum ponto do caminho.

O `hash_sha256` não é decoração: a coluna em `documentos` é UNIQUE, e é o que
impede o mesmo edital de entrar duas vezes no acervo por ter sido baixado com
nomes diferentes.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

# O console do Windows abre em cp1252 e derruba o processo com
# UnicodeEncodeError ao imprimir qualquer caractere fora dessa tabela (setas,
# sigma, "aproximadamente"). Forcar UTF-8 na saida evita que um caractere de
# relatorio mate uma execucao que ja gastou chamada paga.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

BUCKET = "documentos"
# Espelha o file_size_limit de migrations/002_storage.sql. Checar no cliente dá
# uma mensagem útil em vez do 413 cru do servidor depois de subir 100 MiB.
LIMITE_BYTES = 100 * 1024 * 1024


def sha256_arquivo(caminho: Path) -> str:
    """SHA-256 em blocos — o acervo tem arquivos de dezenas de MB."""
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def sanitizar(nome: str) -> str:
    """`Implant. laboratório ISI.pdf` -> `Implant.-laboratorio-ISI.pdf`."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^A-Za-z0-9._-]+", "-", sem_acento)).strip("-")


def montar_storage_path(caminho: Path, hash_sha256: str) -> str:
    return f"{hash_sha256[:16]}/{sanitizar(caminho.name)}"


def _credenciais() -> tuple[str, str]:
    from solufarma_rag.config import get_settings

    cfg = get_settings()
    if not cfg.supabase_url or not cfg.supabase_secret_key:
        raise RuntimeError(
            "SUPABASE_URL e SUPABASE_SERVICE_KEY precisam estar no .env. "
            "A publishable key NÃO serve: o bucket é privado e sem policies."
        )
    return cfg.supabase_url.rstrip("/"), cfg.supabase_secret_key


def _headers(chave: str) -> dict[str, str]:
    """Autenticação do Storage: `apikey`, NUNCA `Authorization: Bearer`.

    Com a chave no formato novo (`sb_secret_...`), mandar a chave em
    `Authorization: Bearer` faz o Storage tentar validá-la como JWT e responder
    `400 {"statusCode":"403","message":"Invalid Compact JWS"}` — um erro que não
    diz nada sobre o header errado e manda você procurar chave inválida.

    Confirmado contra o projeto real em 2026-08-11: `apikey` sozinho retorna 200;
    `Authorization: Bearer` sozinho falha. (Com a chave JWT legada os dois
    funcionavam, que é por que a maior parte dos exemplos na internet usa Bearer.)
    """
    return {"apikey": chave}


def listar(client, url: str, chave: str) -> list[dict]:
    """Objetos já no bucket. Usa a API de list, não SQL — é a fonte da verdade."""
    resposta = client.post(
        f"{url}/storage/v1/object/list/{BUCKET}",
        headers=_headers(chave),
        json={"prefix": "", "limit": 1000},
    )
    resposta.raise_for_status()
    return resposta.json()


def enviar(client, url: str, chave: str, caminho: Path) -> tuple[str, str]:
    """Sobe o arquivo. Retorna (storage_path, hash_sha256)."""
    tamanho = caminho.stat().st_size
    if tamanho > LIMITE_BYTES:
        raise ValueError(
            f"{caminho.name}: {tamanho / 1024 / 1024:.1f} MB excede o limite de "
            f"{LIMITE_BYTES / 1024 / 1024:.0f} MB do bucket (ver 002_storage.sql)."
        )

    hash_sha256 = sha256_arquivo(caminho)
    storage_path = montar_storage_path(caminho, hash_sha256)

    resposta = client.post(
        f"{url}/storage/v1/object/{BUCKET}/{storage_path}",
        headers={
            **_headers(chave),
            "Content-Type": "application/pdf",
            # Sem isto, reenviar o mesmo arquivo devolve 409 em vez de ser no-op.
            "x-upsert": "true",
        },
        content=caminho.read_bytes(),
        timeout=300.0,  # 11 MB em conexão ruim passa fácil do default de 5s
    )
    if resposta.status_code >= 400:
        raise RuntimeError(f"{caminho.name}: HTTP {resposta.status_code} — {resposta.text}")

    return storage_path, hash_sha256


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivos", nargs="*", help="PDFs a subir (aceita glob do shell)")
    parser.add_argument("--listar", action="store_true", help="Só lista o que já está no bucket")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if not args.arquivos and not args.listar:
        parser.error("informe ao menos um arquivo, ou use --listar")

    import httpx

    try:
        url, chave = _credenciais()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    with httpx.Client() as client:
        if args.listar:
            objetos = listar(client, url, chave)
            if not objetos:
                print(f"Bucket '{BUCKET}' está vazio.")
            for o in objetos:
                print(f"  {o.get('name')}")
            return 0

        falhas = 0
        for bruto in args.arquivos:
            caminho = Path(bruto)
            if not caminho.is_file():
                print(f"  [FALHA] {bruto}: arquivo não encontrado", file=sys.stderr)
                falhas += 1
                continue
            try:
                storage_path, hash_sha256 = enviar(client, url, chave, caminho)
            except (ValueError, RuntimeError) as exc:
                print(f"  [FALHA] {exc}", file=sys.stderr)
                falhas += 1
                continue
            print(f"  [ok]  {caminho.name}")
            print(f"        storage_path = {storage_path}")
            print(f"        hash_sha256  = {hash_sha256}")

    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
