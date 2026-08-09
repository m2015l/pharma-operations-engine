"""Testes do chunking estrutural de editais."""

from __future__ import annotations

from datetime import date

import pytest

from solufarma_rag.db.models import Chunk, DocumentoParaChunking, PaginaDocumento
from solufarma_rag.ingestion.chunking import estimar_tokens, gerar_chunks


def test_gera_chunks_com_metadados_obrigatorios(documento):
    """Todo chunk carrega os metadados de rastreabilidade exigidos pela skill."""
    chunks = gerar_chunks(documento)

    assert chunks, "documento de exemplo deve produzir ao menos um chunk"
    for chunk in chunks:
        assert chunk.documento_id == "doc-001"
        assert chunk.tipo_documento == "edital"
        assert chunk.orgao == "SES/GO"
        assert chunk.data == date(2023, 5, 10)
        assert chunk.secao
        assert 1 <= chunk.pagina_inicio <= chunk.pagina_fim <= 2
        assert chunk.content_hash


def test_indices_sao_sequenciais_e_chave_unica(documento):
    chunks = gerar_chunks(documento)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len({c.chave for c in chunks}) == len(chunks)


def test_chunking_e_deterministico(documento):
    """Mesmo documento → mesmos hashes. É a base da indexação incremental."""
    hashes_1 = [c.content_hash for c in gerar_chunks(documento)]
    hashes_2 = [c.content_hash for c in gerar_chunks(documento)]

    assert hashes_1 == hashes_2


def test_hash_muda_quando_conteudo_muda(documento):
    original = gerar_chunks(documento)

    documento.paginas[0].texto = documento.paginas[0].texto.replace("autoclave", "estufa")
    alterado = gerar_chunks(documento)

    assert original[0].content_hash != alterado[0].content_hash


def test_respeita_tamanho_maximo_de_tokens(documento):
    """O teto é teto: nenhum chunk pode ultrapassá-lo, nem por pouco.

    A versão anterior deste teste tolerava 2× o máximo e por isso não detectou
    chunks 14% acima do limite com os parâmetros de produção.
    """
    chunks = gerar_chunks(documento, tamanho_max_tokens=200, tamanho_alvo_tokens=150)

    for chunk in chunks:
        assert chunk.token_count <= 200, f"chunk {chunk.chunk_index} acima do teto"


@pytest.mark.parametrize(
    "descricao,texto",
    [
        (
            "parágrafo médio seguido de bloco grande",
            "Texto de paragrafo medio do edital. " * 60
            + "\n\n"
            + "Especificacao tecnica detalhada do equipamento exigido. " * 140,
        ),
        ("sentença gigante sem pontuação", "palavra " * 3000),
        (
            "tabela gigante de itens",
            "\n".join(f"| item {i} | descricao detalhada do equipamento | 10 |" for i in range(300)),
        ),
    ],
)
def test_teto_de_tokens_nunca_e_ultrapassado(descricao, texto):
    """Casos que estouravam o teto antes da contabilidade em caracteres."""
    doc = DocumentoParaChunking(
        documento_id="doc-teto",
        tipo_documento="edital",
        orgao="Secretaria Municipal de Saude de Sao Jose dos Campos - Estado de Sao Paulo",
        numero_edital="PREGAO ELETRONICO 000123/2024-SMS",
        paginas=[PaginaDocumento(numero=1, texto="1. DO OBJETO\n" + texto)],
    )

    chunks = gerar_chunks(doc, tamanho_max_tokens=1000, tamanho_alvo_tokens=800)

    maior = max(c.token_count for c in chunks)
    assert maior <= 1000, f"{descricao}: chunk de {maior} tokens acima do teto de 1000"


def test_detecta_secoes_do_edital(documento):
    chunks = gerar_chunks(documento)
    secoes = {c.secao for c in chunks}

    assert any("OBJETO" in s for s in secoes)
    assert any("HABILITAÇÃO" in s or "HABILITACAO" in s for s in secoes)
    assert any("ANEXO I" in s.upper() for s in secoes)


def test_nao_mistura_secoes_no_mesmo_chunk(documento):
    """Cada chunk pertence a exatamente uma seção (filtro por seção é confiável)."""
    chunks = gerar_chunks(documento)

    for chunk in chunks:
        assert chunk.secao in chunk.conteudo.split("\n", 1)[0]


def test_prefixo_contextual_presente(documento):
    """O embedding precisa carregar o contexto do documento (§4.6)."""
    chunks = gerar_chunks(documento)

    primeira_linha = chunks[0].conteudo.split("\n", 1)[0]
    assert "PE 045/2023" in primeira_linha
    assert "SES/GO" in primeira_linha


def test_tabela_de_itens_nao_e_quebrada(documento):
    """Tabelas de itens/equipamentos devem ficar íntegras em um único chunk."""
    chunks = gerar_chunks(documento)

    com_tabela = [c for c in chunks if "| Item |" in c.conteudo]
    assert len(com_tabela) == 1
    assert "Autoclave horizontal 100L" in com_tabela[0].conteudo
    assert "Centrífuga laboratorial refrigerada" in com_tabela[0].conteudo


def test_overlap_entre_chunks_da_mesma_secao():
    """Chunks consecutivos da mesma seção compartilham a cauda do anterior."""
    paragrafos = "\n\n".join(
        f"Parágrafo {i} do termo de referência com texto suficientemente longo "
        f"para forçar a quebra em múltiplos chunks dentro da mesma seção do edital."
        for i in range(40)
    )
    doc = DocumentoParaChunking(
        documento_id="doc-overlap",
        tipo_documento="edital",
        orgao="SES/GO",
        paginas=[PaginaDocumento(numero=1, texto="1. DO OBJETO\n" + paragrafos)],
    )

    chunks = gerar_chunks(doc, tamanho_alvo_tokens=200, tamanho_max_tokens=250)

    assert len(chunks) > 1, "texto longo deve gerar múltiplos chunks"
    corpo_anterior = chunks[0].conteudo.rsplit("\n\n", 1)[-1]
    assert corpo_anterior[-40:] in chunks[1].conteudo, "faltou overlap entre chunks"


def test_documento_exige_ao_menos_uma_pagina():
    with pytest.raises(ValueError):
        DocumentoParaChunking(
            documento_id="x", tipo_documento="edital", orgao="SES/GO", paginas=[]
        )


def test_tipo_documento_invalido_e_rejeitado():
    with pytest.raises(ValueError, match="tipo_documento"):
        DocumentoParaChunking(
            documento_id="x",
            tipo_documento="planilha",
            orgao="SES/GO",
            paginas=[PaginaDocumento(numero=1, texto="texto")],
        )


def test_estimar_tokens_nunca_retorna_zero():
    assert estimar_tokens("") == 1
    assert estimar_tokens("a" * 400) == 100


def test_hash_e_estavel_entre_processos():
    """Usa SHA-256, não hash() — que é salteado por processo."""
    assert Chunk.calcular_hash("texto") == (
        "f46e3b17a6b639e5efddc3d1498ad73491599c22220f7ef6e14772f4ee25b913"
    )
