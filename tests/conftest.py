"""Fixtures compartilhadas — tudo offline, sem rede e sem chaves de API."""

from __future__ import annotations

from datetime import date

import pytest

from solufarma_rag.db.models import Chunk, DocumentoParaChunking, PaginaDocumento
from solufarma_rag.db.repository import InMemoryChunkRepository
from solufarma_rag.ingestion.chunking import gerar_chunks
from solufarma_rag.ingestion.embeddings import FakeEmbeddingProvider

PAGINA_1 = """\
1. DO OBJETO
Aquisição de equipamentos hospitalares para o Hospital Regional, conforme
especificações do Termo de Referência, incluindo autoclave horizontal de
100 litros e centrífuga laboratorial refrigerada.

2. DA HABILITAÇÃO
A licitante deverá apresentar registro na ANVISA para todos os equipamentos
médicos ofertados, além de certidão negativa de débitos e atestado de
capacidade técnica emitido por órgão público.
"""

PAGINA_2 = """\
3. DOS ITENS E QUANTIDADES
| Item | Descrição | Quantidade |
| 1 | Autoclave horizontal 100L | 2 |
| 2 | Centrífuga laboratorial refrigerada | 3 |

ANEXO I – TERMO DE REFERÊNCIA
A autoclave deverá possuir câmara em aço inoxidável AISI 316L e ciclo de
esterilização programável, com garantia mínima de 24 meses e assistência
técnica em território nacional.
"""


@pytest.fixture
def fazer_chunk():
    """Fábrica de chunks sintéticos para testes de busca, RRF e citação."""

    def _fazer(indice: int, conteudo: str = "texto", **extra) -> Chunk:
        campos = {
            "documento_id": "doc-001",
            "chunk_index": indice,
            "tipo_documento": "edital",
            "orgao": "SES/GO",
            "secao": "1. DO OBJETO",
            "pagina_inicio": 1,
            "pagina_fim": 1,
            "conteudo": conteudo,
            "token_count": 10,
            "content_hash": f"hash-{indice}",
        }
        campos.update(extra)
        return Chunk(**campos)

    return _fazer


@pytest.fixture
def documento() -> DocumentoParaChunking:
    """Edital de exemplo com seções, tabela e anexo — espelha um caso real."""
    return DocumentoParaChunking(
        documento_id="doc-001",
        tipo_documento="edital",
        orgao="SES/GO",
        numero_edital="PE 045/2023",
        data=date(2023, 5, 10),
        paginas=[
            PaginaDocumento(numero=1, texto=PAGINA_1),
            PaginaDocumento(numero=2, texto=PAGINA_2),
        ],
    )


@pytest.fixture
def provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def repo_indexado(documento, provider) -> InMemoryChunkRepository:
    """Repositório com o documento de exemplo já chunkado e embeddado."""
    from solufarma_rag.ingestion.embeddings import gerar_embeddings_pendentes

    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))
    gerar_embeddings_pendentes(repo, provider)
    return repo
