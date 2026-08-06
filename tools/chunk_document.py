"""CLI de chunking — etapa 5 de workflows/ingestao_documento.md.

Recebe um JSON com o documento já extraído (saída da etapa de OCR/extração,
frente de OCR & Processamento) e imprime os chunks gerados em JSON.

Uso:
    python tools/chunk_document.py documento.json > chunks.json

Formato de entrada (campos de DocumentoParaChunking):
    {
      "documento_id": "uuid",
      "tipo_documento": "edital",
      "orgao": "SES/GO",
      "numero_edital": "PE 045/2023",
      "data": "2023-05-10",
      "paginas": [{"numero": 1, "texto": "..."}]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from solufarma_rag.db.models import DocumentoParaChunking
from solufarma_rag.ingestion.chunking import gerar_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path, help="JSON do documento extraído")
    parser.add_argument("--alvo", type=int, default=800, help="Tokens alvo por chunk")
    args = parser.parse_args()

    # utf-8-sig lê com ou sem BOM: ferramentas Windows (Bloco de Notas,
    # Set-Content -Encoding utf8) gravam BOM, e o pipeline de OCR roda no Windows.
    dados = json.loads(args.arquivo.read_text(encoding="utf-8-sig"))
    documento = DocumentoParaChunking.model_validate(dados)
    chunks = gerar_chunks(documento, tamanho_alvo_tokens=args.alvo)

    print(json.dumps([c.model_dump(mode="json") for c in chunks], ensure_ascii=False, indent=2))
    print(f"{len(chunks)} chunks gerados", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
