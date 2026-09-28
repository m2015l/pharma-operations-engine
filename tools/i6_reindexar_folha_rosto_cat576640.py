"""I6 (PRECISÃO.md) — correção pontual dos chunks 1-2 da folha de rosto da CAT.

Não reprocessa OCR (o texto já extraído está correto e integral — o problema
é só a divisão em chunks, que engoliu a seção "ATIVIDADE TÉCNICA REALIZADA"
dentro de um chunk genérico sem heading). Reescreve os chunks manualmente com
os mesmos headings sintéticos que I6 pede, isola "ATIVIDADE TÉCNICA REALIZADA"
em chunk próprio, zera embedding para o pipeline reembeddar só o que mudou.

Tratado como patch pontual deste documento, não como heurística genérica de
código — PRECISÃO.md §I6 avisa para não generalizar sem um segundo documento.

JÁ EXECUTADO em produção em 28/09/2026 (ver docs/DIARIO_DE_BORDO.md). NÃO
RODAR DE NOVO: é idempotente apenas na leitura, não na escrita — rodar outra
vez duplicaria o chunk "ATIVIDADE TÉCNICA REALIZADA" e voltaria a colidir a
renumeração de chunk_index. Mantido no repo só para auditoria/reprodução —
se precisar generalizar para outro documento, escreva a heurística em
`src/solufarma/chunking.py` (parsear_blocos) em vez de copiar este script.
"""
import hashlib
import sys

sys.path.insert(0, "src")
from solufarma_rag.db.repository import criar_conexao

DOC_TITULO = "SENAI CETIQT CAT 576640 Implant. laboratório ISI"
DOC_ID = "7dac2d66-0e1d-41ff-b46f-dde1db6aca26"

def hash_de(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()

def cabecalho(secao: str, pagina) -> str:
    partes = [DOC_TITULO]
    if secao:
        partes.append(secao)
    partes.append(f"p. {pagina}")
    return "[" + " | ".join(partes) + "]"

CHUNK_A_ID = "d9754c6e-dd98-4e75-b65c-a8a157eb4ecb"  # idx 2, mantém
CHUNK_C_ID = "98842d4e-432c-4234-bf36-de63b3290790"  # idx 3 -> vira idx 4

secao_a = "DADOS DO CONTRATO"
corpo_a = """rá o INSTITUTO SENAI DE INOVAÇÃO (ISI) contemplando
execução de estrutura metálica 23.537kg, paredes em dry-wall 1.445m², piso vinílico em manta 3.488,44m²,piso laminado 800m², forro
tipo metalgrade 577,37m², porta de madeira de alto tráfego 47 unid. Empresa contratada: SOLUFARMA DO BRASIL ENGENHARIA LTDA - ME
CNPJ: 07.746.677/0001-12
 DADOS DO CONTRATO
Contratante: SERVIÇO NACIONAL DE APRENDIZAGEM INDUSTRIAL - CENTRO DE TECNOLOGIA DA INDUSTRIA QUÍMICA E
TÊXTIL - SENAI CETIQT
CPF/CNPJ: 03851105000142
RUA DOUTOR MANUEL COTRIM
Nº 195
Complemento:
Cidade: RIO DE JANEIRO
Bairro: RIACHUELO
UF: RJ
CEP: 20961040
Contrato: C2 003B-2018
Celebrado em: 07/02/2019
Valor do Contrato: R$ 9.120.045,54
Tipo do Contratante: Pessoa jurídica de direito privado
Data de Início: 13/03/2019
Data de término da atividade: 2019-12-06"""
conteudo_a = cabecalho(secao_a, "1-2") + "\n" + corpo_a

secao_b = "ATIVIDADE TÉCNICA REALIZADA"
corpo_b = """ ATIVIDADE TÉCNICA REALIZADA
2.1.1 - Execução de obra, 5655.00 m² - metro quadrado; 2.1.2 - Execução de reforma de edificação, 5655.00 m² - metro quadrado; 2.2.4 - Execução de estrutura metálica, 23537.00 kg - quilograma; 2.6.2 - Execução de recuperação paisagística, 625.00 m² - metro quadrado."""
conteudo_b = cabecalho(secao_b, 2) + "\n" + corpo_b

secao_c = "ENDEREÇO DA OBRA/SERVIÇO"
corpo_c = """ ENDEREÇO DA OBRA/SERVIÇO
RUA PAULO EMIDIO BARBOSA, S/N
Nº 485
Complemento:
Cidade: RIO DE JANEIRO
Bairro: CIDADE UNIVERSITÁRIA
UF: RJ
CEP: 21941907
Coordenadas Geográficas: 0 0
 DESCRIÇÃO
CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO
Impresso em: 01/09/2020 às 18:04:15 por: ILZA MARIA COPPIO SATTELMAYER, ip: 172.18.1.8
Página 2/60
Conselho de Arquitetura e Urbanismo
do Brasil
CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO
Resolução Nº 93 de 07 de Novembro de 2014
CERTIDÃO DE ACERVO TÉCNICO COM ATESTADO
Nº 0000000576640
 INFORMAÇÕES IMPORTANTES
- Esta certidão perderá a validade e será anulada, caso ocorra alterações das informações constantes do Atestado registrado ou do RRT vinculado ou caso sejam constatadas que são inverídicas as informações constantes do RRT, do atestado ou do requerimento da certidão. - Certificamos que se encontra vinculado à presente CAT o atestado apresentado em cumprimento à Lei nº 8.666/93, expedido pela pessoa jurídica contratante, a quem cabe a responsabilidade pela veracidade e exatidão das informações nele constantes. É de responsabilidade deste Conselho a verificação da atividade profissional em conformidade com a Lei nº 12.378/2010 e Resoluções do Conselho de Arquitetura e Urbanismo do Brasil (CAU/BR)
- A Certidão de Acervo Técnico (CAT) à qual o atestado está vinculado constituirá prova da capacidade técnico-profissional da pessoa jurídica somente se o responsável técnico indicado estiver ou venha a ser integrado ao seu quadro técnico por meio de declaração entregue no momento da habilitação ou da entrega das propostas
- Certificamos, ainda, que nos termos do artigo 2º da Lei nº 12.378/2010 e artigos 2º e 3º da Resolução nº 21/2012-CAU/BR, esta Certidão é válida somente para os serviços condizentes com as atribuições profissionais acima discriminadas
- Em conformidade com o que determina o Art. 45 da Lei 12.378, toda realização de trabalho de competência privativa ou de atuação compartilhadas com outras profissões regulamentadas será objeto de Registro de Responsabilidade Técnica - RRT
- Válida em todo o território nacional. Certidão nº 576640/2020
Expedida em 06/07/2020 12:07:00, São José dos Campos/SP, CAU/SP"""
conteudo_c = cabecalho(secao_c, 2) + "\n" + corpo_c

OFFSET = 100000

conn = criar_conexao()
try:
    with conn.cursor() as cur:
        # 0) Abre espaço para o novo chunk_index=3: desloca 3..161 por um offset
        # grande (evita colisão com a unique(documento_id, chunk_index) durante
        # a operação) e depois traz de volta em +1 — abre exatamente uma vaga.
        cur.execute(
            "update doc_chunks set chunk_index = chunk_index + %s "
            "where documento_id = %s and chunk_index >= 3",
            (OFFSET, DOC_ID),
        )
        cur.execute(
            "update doc_chunks set chunk_index = chunk_index - %s "
            "where documento_id = %s and chunk_index >= %s",
            (OFFSET - 1, DOC_ID, OFFSET + 3),
        )

        # A) reescreve o chunk existente (mesmo id/idx=2), sem a atividade técnica
        cur.execute(
            """update doc_chunks set conteudo=%s, secao=%s, token_count=%s,
               content_hash=%s, embedding=NULL, embedding_model=NULL,
               embedding_content_hash=NULL where id=%s""",
            (conteudo_a, secao_a, len(conteudo_a) // 4, hash_de(conteudo_a), CHUNK_A_ID),
        )
        # C) o velho idx=3 agora está em idx=4 (pela renumeração acima);
        #    reescreve com o conteúdo completo do endereço/rodapé
        cur.execute(
            """update doc_chunks set conteudo=%s, secao=%s,
               token_count=%s, content_hash=%s, embedding=NULL,
               embedding_model=NULL, embedding_content_hash=NULL where id=%s""",
            (conteudo_c, secao_c, len(conteudo_c) // 4, hash_de(conteudo_c), CHUNK_C_ID),
        )
        # B) insere o novo chunk dedicado, na vaga aberta (idx=3)
        cur.execute(
            """insert into doc_chunks
               (documento_id, chunk_index, secao, pagina_inicio, pagina_fim,
                conteudo, token_count, content_hash)
               values (%s, 3, %s, 2, 2, %s, %s, %s)""",
            (DOC_ID, secao_b, conteudo_b, len(conteudo_b) // 4, hash_de(conteudo_b)),
        )

        # Confere que não sobrou nenhuma colisão e que a contagem bate (161 + 1 novo)
        cur.execute("select count(*) from doc_chunks where documento_id=%s", (DOC_ID,))
        total = cur.fetchone()[0]
        cur.execute(
            "select count(*), count(distinct chunk_index) from doc_chunks where documento_id=%s",
            (DOC_ID,),
        )
        n, n_distintos = cur.fetchone()
        assert n == n_distintos, f"colisão de chunk_index! {n} linhas, {n_distintos} índices distintos"
        assert total == 162, f"esperava 162 chunks (161 + 1 novo), achei {total}"
    conn.commit()
    print(f"OK: chunks da folha de rosto reescritos (I6). Total agora: {total} chunks, sem colisão.")
finally:
    conn.close()
