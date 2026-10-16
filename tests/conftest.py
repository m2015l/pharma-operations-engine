"""
Fixtures dos quatro invariantes do CLAUDE.md.

São SINTÉTICAS por ora — o `INSTITUTO BIOPHARMA_CAT_100200.pdf` ainda não está no
repositório. Cada uma reproduz numericamente a condição descrita no CLAUDE.md
(347 caracteres de carimbo em área A4, tabela sem cabeçalho na página seguinte,
etc.), mas nenhuma prova que o documento REAL se comporta como esperado.

Quando o PDF chegar, trocar por extratos reais e reconferir os números.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from pharma_rag.db.models import Chunk, DocumentoParaChunking, PaginaDocumento
from pharma_rag.db.repository import InMemoryChunkRepository
from pharma_rag.ingestion.chunking import gerar_chunks
from pharma_rag.ingestion.embeddings import FakeEmbeddingProvider

# A4 renderizada com lado maior = 1500px (config.LADO_MAIOR_PX).
A4_ALTURA_PX = 1500
A4_LARGURA_PX = 1061  # 1500 / 1.414
AREA_A4_PX = A4_ALTURA_PX * A4_LARGURA_PX  # ~1,59M px²

# O carimbo do CAU embutido nas págs. 3-60: 347 caracteres idênticos.
# Passa em MIN_CARACTERES_UTEIS (220) e reprova em MIN_DENSIDADE — que é
# exatamente o ponto do invariante 2.
CARIMBO_CAU = (
    "Certidão nº 100200/2020 - 01/09/2020, 18:04 - Chave de Impressão: 0000000A000AA0A0AAA0 "
    "O atestado neste ato registrado foi emitido em 01/09/2020, e contém 60 folhas vinculado "
    "à Certidão De Acervo Técnico Com Atestado nº 100200, emitida em 01/09/2020 "
    "Este documento encontra-se registrado no Conselho de Arquitetura e Urbanismo do Brasil,"
)


@pytest.fixture
def zip_disfarcado(tmp_path: Path) -> Path:
    """
    INVARIANTE 1 — extensão mente.

    Arquivo com sufixo `.pdf` cujos bytes são um ZIP com 3 JPEGs, igual ao
    documento do Instituto BioPharma. Nomes fora de ordem alfabética (2, 10, 1) para o teste
    também cobrir a ordenação numérica.
    """
    destino = tmp_path / "documento.pdf"
    with zipfile.ZipFile(destino, "w") as z:
        for numero in (2, 10, 1):
            buf = io.BytesIO()
            Image.new("RGB", (400, 560), "white").save(buf, format="JPEG")
            z.writestr(f"pagina_{numero}.jpg", buf.getvalue())
    return destino


@pytest.fixture
def pdf_verdadeiro(tmp_path: Path) -> Path:
    """Controle: um `.pdf` que é de fato um PDF."""
    destino = tmp_path / "real.pdf"
    destino.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    return destino


@pytest.fixture
def paginas_marca_dagua() -> list[str]:
    """
    INVARIANTE 2 — texto nativo pode ser só marca d'água.

    60 páginas: as duas primeiras com texto real (o PDF nativo do SICCAU), as
    58 seguintes só com o carimbo. É o formato exato do CAT do Instituto BioPharma.
    """
    reais = [
        "CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO\n" + ("conteúdo real da página. " * 120),
        "DADOS DO PROFISSIONAL\n" + ("conteúdo real da página. " * 120),
    ]
    return reais + [CARIMBO_CAU] * 58


@pytest.fixture
def tabela_dividida() -> list[dict]:
    """
    INVARIANTE 3 — página não é fronteira semântica.

    Tabela começa na pág. 44 com cabeçalho e continua na 45 sem repeti-lo.
    O OCR marcou a continuação com `<!-- TABELA_CONTINUA -->` e reimprimiu o
    cabeçalho herdado — que a costura precisa descartar.
    """
    return [
        {
            "numero": 44,
            "markdown": (
                "| Descrição | Unidade | Quantidade |\n"
                "|---|---|---|\n"
                "| #2,5MM2 COR PRETO (FASE) | M | 19.541,00 |\n"
                "| #2,5MM2 COR AZUL CLARO (NEUTRO) | M | 16.250,00 |"
            ),
        },
        {
            "numero": 45,
            "markdown": (
                "<!-- TABELA_CONTINUA -->\n"
                "| Descrição | Unidade | Quantidade |\n"
                "|---|---|---|\n"
                "| #4MM2 COR PRETO (FASE) | M | 3.050,00 |\n"
                "| #240MM2 COR VERDE (TERRA) | M | 300,00 |"
            ),
        },
    ]


@pytest.fixture
def paragrafo_dividido() -> list[dict]:
    """INVARIANTE 3, outra face: parágrafo cortado pela paginação física."""
    return [
        {"numero": 8, "markdown": "As mantas vinílicas atendem às rígidas requisições de"},
        {
            "numero": 9,
            "markdown": "<!-- PARAGRAFO_CONTINUA -->\nresistência química e de abrasão.",
        },
    ]


@pytest.fixture
def prosa_hierarquica() -> list[dict]:
    """
    INVARIANTE 4 — a saída do OCR é Markdown estruturado.

    Hierarquia `A.` / `A.1` / `A.1.1` como aparece no memorial descritivo.
    O caminho de seção do chunk depende inteiramente destes headings.
    """
    return [
        {
            "numero": 8,
            "markdown": (
                "## A. Arquitetura\n"
                "Descrição geral do partido arquitetônico adotado na reforma.\n\n"
                "### A.1 acabamentos de pisos\n"
                "Em geral, o mais significativo neste caso é a especificação.\n\n"
                "#### A.1.1 vinílicos\n"
                "As mantas vinílicas atendem às rígidas requisições de resistência."
            ),
        }
    ]


@pytest.fixture
def documento_extraido(prosa_hierarquica, tabela_dividida) -> dict:
    """JSON de extração completo, no formato que o chunking consome."""
    return {
        "arquivo": "INSTITUTO BIOPHARMA_CAT_100200.pdf",
        "hash_documento": "abc123def456",
        "n_paginas": 3,
        "formato_detectado": "zip_imagens",
        "paginas": prosa_hierarquica + tabela_dividida,
    }


# ===========================================================================
# Fixtures da frente RAG & Agente (pacote pharma_rag)
#
# Convivem com as fixtures de extração/chunking acima sem colisão de nome.
# Enquanto o port do pacote para `src/pharma_ops/` não acontece (item 14 do
# PLANO_PROJETO), estas fixtures importam de `pharma_rag`.
# ===========================================================================

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


@pytest.fixture(autouse=True)
def _piso_de_similaridade_fixo(monkeypatch):
    """Isola os testes do SIMILARIDADE_MINIMA do `.env` do desenvolvedor.

    O piso da busca vetorial passou a ser configurável por ambiente, porque o
    valor certo depende do modelo de embeddings (`tools/avaliar.py --calibrar`).
    Sem esta fixture, a suíte passaria a depender de qual calibração está no
    `.env` da máquina: alguém mede 0.62 para o modelo de produção, comita, e os
    testes de retrieval quebram sem que uma linha de código tenha mudado — com
    um erro que não aponta para a causa.

    0.15 é o valor calibrado contra o FakeEmbeddingProvider, que é o provedor
    que os testes usam. Fixá-lo aqui mantém os testes medindo o CÓDIGO.
    """
    monkeypatch.setenv("SIMILARIDADE_MINIMA", "0.15")
    # Mesmo motivo para o reranker: a suíte roda offline e não pode chamar a
    # Voyage só porque o `.env` da máquina diz RERANKER=voyage.
    monkeypatch.setenv("RERANKER", "nenhum")


@pytest.fixture
def provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def repo_indexado(documento, provider) -> InMemoryChunkRepository:
    """Repositório com o documento de exemplo já chunkado e embeddado."""
    from pharma_rag.ingestion.embeddings import gerar_embeddings_pendentes

    repo = InMemoryChunkRepository()
    repo.upsert_chunks(gerar_chunks(documento))
    gerar_embeddings_pendentes(repo, provider)
    return repo
