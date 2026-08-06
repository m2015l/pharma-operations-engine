-- ============================================================================
-- SUPERSEDIDO por 001_schema_inicial.sql (06/08/26). Mantido como referência.
--
-- O schema foi para 001_schema_inicial.sql com as duas lacunas de DDL resolvidas.
-- Esta RPC NÃO entrou lá: o RRF já existe em Python (retrieval/hybrid_search.py),
-- coberto por testes, e manter a fusão nas duas linguagens obrigaria a sincronizar
-- a fórmula na mão — com a versão testada sendo justamente a que não roda em
-- produção. O backend faz duas consultas e funde em Python.
--
-- Vale ressuscitar esta função se a latência de dois round-trips incomodar com
-- acervo grande. Nesse caso os testes precisam passar a rodar contra ela.
-- ============================================================================

-- ============================================================================
-- RASCUNHO — NÃO APLICAR AUTOMATICAMENTE
-- Aplicação: frente de Dados & Infraestrutura, após o DDL base
-- (docs/ARQUITETURA.md §3: extensões vector/pg_trgm/unaccent e tabelas
-- licitacoes, licitacao_itens, documentos, doc_chunks).
--
-- Função RPC de busca híbrida chamada pelo backend via Supabase.
-- Fonte: docs/ARQUITETURA.md §3, com uma extensão em relação ao rascunho da
-- arquitetura: filtros de período (filtro_data_inicio / filtro_data_fim),
-- exigidos pelo design do retrieval (§5.1 — filtros por órgão, tipo e data).
-- Espelha a semântica implementada em src/solufarma_rag/retrieval/hybrid_search.py
-- (fusão RRF com k=60) e em db/repository.py (repositório em memória).
-- ============================================================================

create or replace function busca_hibrida(
    query_embedding   vector(1024),
    query_text        text,
    filtro_tipo       text default null,
    -- NOTA: filtro_resultado (ganhou/perdeu) NÃO tem equivalente em FiltrosBusca
    -- no Python. Mantido aqui porque é filtro de valor óbvio para o negócio, mas
    -- ao implementar SupabaseChunkRepository é preciso decidir: ou FiltrosBusca
    -- ganha o campo, ou este parâmetro sai. Hoje as duas camadas divergem.
    filtro_resultado  text default null,
    filtro_orgao      text default null,
    filtro_data_inicio date default null,
    filtro_data_fim    date default null,
    match_count       int default 20,
    -- Piso de relevância: sem ele o ramo vetorial devolve sempre os N chunks
    -- mais próximos, mesmo sem relação com a pergunta, e o agente nunca
    -- consegue dizer "não encontrei no acervo". Espelha SIMILARIDADE_MINIMA_PADRAO
    -- em retrieval/hybrid_search.py — CALIBRAR junto com os embeddings reais.
    similaridade_minima float default 0.15
)
-- As colunas projetadas precisam bastar para montar um Chunk COMPLETO (ver
-- db/models.py): sem secao/pagina_inicio/pagina_fim/tipo/orgao aqui, o backend
-- teria de fazer uma segunda consulta só para conseguir montar a citação — e a
-- citação com página é requisito central do projeto.
returns table (
    chunk_id       uuid,
    documento_id   uuid,
    conteudo       text,
    secao          text,
    pagina_inicio  int,
    pagina_fim     int,
    tipo_documento text,
    orgao          text,
    data_abertura  date,
    score          float
)
language sql stable as $$
    with vetorial as (
        select c.id, 1 - (c.embedding <=> query_embedding) as sim
        from doc_chunks c
        join documentos d on d.id = c.documento_id
        left join licitacoes l on l.id = d.licitacao_id
        where c.embedding is not null
          and 1 - (c.embedding <=> query_embedding) >= similaridade_minima
          and (filtro_tipo is null or d.tipo = filtro_tipo)
          and (filtro_resultado is null or l.resultado = filtro_resultado)
          and (filtro_orgao is null or l.orgao ilike '%' || filtro_orgao || '%')
          and (filtro_data_inicio is null or l.data_abertura >= filtro_data_inicio)
          and (filtro_data_fim is null or l.data_abertura <= filtro_data_fim)
        order by c.embedding <=> query_embedding
        limit match_count * 2
    ),
    lexica as (
        select c.id, ts_rank(c.fts, websearch_to_tsquery('portuguese', unaccent(query_text))) as rank
        from doc_chunks c
        join documentos d on d.id = c.documento_id
        left join licitacoes l on l.id = d.licitacao_id
        where c.fts @@ websearch_to_tsquery('portuguese', unaccent(query_text))
          and (filtro_tipo is null or d.tipo = filtro_tipo)
          and (filtro_resultado is null or l.resultado = filtro_resultado)
          and (filtro_orgao is null or l.orgao ilike '%' || filtro_orgao || '%')
          and (filtro_data_inicio is null or l.data_abertura >= filtro_data_inicio)
          and (filtro_data_fim is null or l.data_abertura <= filtro_data_fim)
        order by rank desc
        limit match_count * 2
    )
    -- Reciprocal Rank Fusion (RRF), k = 60 — mesma constante do módulo Python.
    select c.id, c.documento_id, c.conteudo,
           c.secao, c.pagina_inicio, c.pagina_fim,
           d.tipo, l.orgao, l.data_abertura,
           coalesce(1.0/(60 + vr.pos), 0) + coalesce(1.0/(60 + lr.pos), 0) as score
    from doc_chunks c
    join documentos d on d.id = c.documento_id
    left join licitacoes l on l.id = d.licitacao_id
    left join (select id, row_number() over (order by sim desc)  as pos from vetorial) vr on vr.id = c.id
    left join (select id, row_number() over (order by rank desc) as pos from lexica)  lr on lr.id = c.id
    where vr.id is not null or lr.id is not null
    order by score desc
    limit match_count;
$$;

-- ============================================================================
-- PENDÊNCIAS BLOQUEANTES para a frente de Dados & Infraestrutura
-- (levantadas na revisão de código da frente RAG — precisam de decisão ANTES
--  de implementar SupabaseChunkRepository)
--
-- 1. `doc_chunks` NÃO tem coluna `content_hash` no DDL de docs/ARQUITETURA.md §3.
--    Toda a indexação incremental depende dela (não reindexar o que não mudou —
--    regra da skill rag-licitacoes). `documentos.hash_sha256` não serve: é dedup
--    do arquivo inteiro, não do chunk. AÇÃO: adicionar `content_hash text` a
--    doc_chunks, com índice em (documento_id, chunk_index).
--
-- 2. `Chunk` no Python carrega `orgao` e `data` por chunk, mas no DDL esses
--    campos só existem em `licitacoes`, via JOIN. AÇÃO: decidir entre
--    denormalizar as duas colunas em doc_chunks (leitura mais barata, escrita
--    duplicada) ou manter só o JOIN — neste caso FiltrosBusca no Python precisa
--    parar de assumir que os campos vivem no chunk.
-- ============================================================================
