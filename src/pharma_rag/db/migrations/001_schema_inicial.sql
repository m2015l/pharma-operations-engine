-- ============================================================================
-- Migração 001 — schema inicial do Pharma Operations Platform
--
-- Aplicar no SQL Editor do Supabase, ou via `python tools/setup_supabase.py`.
-- Idempotente: pode rodar mais de uma vez sem quebrar nada.
--
-- Base: docs/ARQUITETURA.md §3, com as duas lacunas de DDL resolvidas:
--   1. doc_chunks ganhou `content_hash` + `embedding_content_hash` (indexação
--      incremental: só re-embedda o que mudou);
--   2. `orgao` e `data` continuam só em `licitacoes` — acessados por JOIN, sem
--      duplicar escrita. A RPC já projeta as duas colunas, então o backend monta
--      o Chunk completo numa consulta só.
-- ============================================================================

-- Extensões -----------------------------------------------------------------
create extension if not exists vector;
create extension if not exists pg_trgm;
create extension if not exists unaccent;

-- `unaccent()` é declarada STABLE, não IMMUTABLE, porque o dicionário que ela
-- usa pode ser recarregado em tempo de execução. O Postgres recusa função
-- STABLE dentro de índice e de coluna gerada — foi o erro
-- "functions in index expression must be marked IMMUTABLE".
--
-- O contorno padrão é este wrapper: a forma de dois argumentos fixa o
-- dicionário explicitamente, o que torna o resultado de fato determinístico e
-- a declaração IMMUTABLE defensável. O `search_path` fixo garante que o
-- dicionário seja encontrado independente de quem chama.
--
-- ATENÇÃO: toda busca textual precisa usar `f_unaccent`, nunca `unaccent`
-- direto — senão a consulta normaliza diferente do índice e não casa.
create or replace function public.f_unaccent(text)
returns text
language sql
immutable
parallel safe
strict
set search_path = public, extensions, pg_catalog
as $$ select unaccent('unaccent', $1) $$;

-- 1. Licitações --------------------------------------------------------------
create table if not exists licitacoes (
    id              uuid primary key default gen_random_uuid(),
    numero_edital   text,
    modalidade      text,
    orgao           text not null,
    uf              char(2),
    municipio       text,
    objeto          text,
    data_abertura   date,
    data_resultado  date,
    valor_estimado  numeric(15,2),
    valor_homologado numeric(15,2),
    resultado       text check (resultado in ('ganha','perdida','deserta','cancelada','em_andamento','nao_participou')),
    motivo_resultado text,
    portal          text,
    metadata        jsonb not null default '{}',
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index if not exists idx_licitacoes_orgao on licitacoes using gin (to_tsvector('portuguese', public.f_unaccent(orgao)));
create index if not exists idx_licitacoes_resultado on licitacoes (resultado);
create index if not exists idx_licitacoes_data on licitacoes (data_abertura);

-- 2. Itens/equipamentos ------------------------------------------------------
create table if not exists licitacao_itens (
    id              uuid primary key default gen_random_uuid(),
    licitacao_id    uuid not null references licitacoes(id) on delete cascade,
    numero_item     text,
    descricao       text not null,
    categoria       text,
    quantidade      numeric,
    unidade         text,
    valor_unitario_estimado numeric(15,2),
    valor_unitario_ofertado numeric(15,2),
    marca_modelo_ofertado   text,
    vencedor        text,
    resultado_item  text check (resultado_item in ('ganho','perdido','deserto','cancelado')),
    metadata        jsonb not null default '{}'
);
create index if not exists idx_itens_licitacao on licitacao_itens (licitacao_id);
create index if not exists idx_itens_descricao_trgm on licitacao_itens using gin (descricao gin_trgm_ops);

-- 3. Documentos --------------------------------------------------------------
create table if not exists documentos (
    id              uuid primary key default gen_random_uuid(),
    licitacao_id    uuid references licitacoes(id) on delete set null,
    tipo            text not null check (tipo in ('edital','ata','resultado','anexo','proposta','recurso','outro')),
    titulo          text,
    storage_path    text not null,
    hash_sha256     text unique,
    num_paginas     int,
    ocr_aplicado    boolean not null default false,
    metodo_extracao text,
    resumo          text,
    status_processamento text not null default 'pendente'
        check (status_processamento in ('pendente','extraido','chunked','indexado','erro')),
    erro_processamento   text,
    created_at      timestamptz not null default now()
);
create index if not exists idx_documentos_licitacao on documentos (licitacao_id);
create index if not exists idx_documentos_status on documentos (status_processamento);

-- 4. Chunks + embeddings + full-text ----------------------------------------
create table if not exists doc_chunks (
    id              uuid primary key default gen_random_uuid(),
    documento_id    uuid not null references documentos(id) on delete cascade,
    chunk_index     int not null,
    secao           text,
    pagina_inicio   int,
    pagina_fim      int,
    conteudo        text not null,
    token_count     int,
    embedding       vector(1024),
    embedding_model text,
    -- LACUNA 1 RESOLVIDA: hash do conteúdo atual vs. hash do que foi embeddado.
    -- Um chunk é "pendente" quando embedding is null OU os dois hashes diferem.
    -- `documentos.hash_sha256` não serve aqui: é dedup do arquivo, não do chunk.
    content_hash           text not null,
    embedding_content_hash text,
    fts             tsvector generated always as (to_tsvector('portuguese', public.f_unaccent(conteudo))) stored,
    unique (documento_id, chunk_index)
);

-- Colunas novas em bancos que já tinham doc_chunks do DDL antigo.
alter table doc_chunks add column if not exists content_hash text;
alter table doc_chunks add column if not exists embedding_content_hash text;
alter table doc_chunks alter column embedding_model drop not null;

create index if not exists idx_chunks_embedding on doc_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists idx_chunks_fts on doc_chunks using gin (fts);
-- Suporta o "listar pendentes" sem varrer a tabela inteira.
create index if not exists idx_chunks_pendentes on doc_chunks (documento_id, chunk_index)
    where embedding is null;

-- 5. Linhas de planilha (ADR-006) --------------------------------------------
--
-- Uma planilha de quantitativos precisa de SQL, não de busca vetorial:
-- "quanto de piso vinílico já fornecemos no total?" é um SUM, e RAG não soma.
-- `chunking.extrair_linhas_tabela()` produz estas linhas em paralelo aos chunks.
--
-- Duas colunas de documento, de propósito:
--   `documento_hash` é o que o pipeline de extração produz hoje (hash_documento,
--   16 hex) — permite gravar sem depender de cadastro prévio;
--   `documento_id` é a FK de verdade, preenchida quando o documento for
--   registrado em `documentos`. Nula até lá, em vez de bloquear a ingestão.
create table if not exists itens_planilha (
    id              uuid primary key default gen_random_uuid(),
    documento_hash  text not null,
    documento_id    uuid references documentos(id) on delete cascade,
    pagina          int,
    secao           text,
    -- Células cruas, na ordem da linha. Valores em formato pt-BR ("19.541,00")
    -- ficam como string: o parse é responsabilidade de quem consulta, e
    -- converter cedo perderia o original em caso de erro de OCR.
    celulas         text[] not null,
    created_at      timestamptz not null default now()
);
-- FK sem índice faz JOIN e DELETE CASCADE varrerem a tabela inteira.
create index if not exists idx_itens_planilha_documento on itens_planilha (documento_id);
-- O caminho de acesso enquanto o documento_id ainda não foi resolvido.
create index if not exists idx_itens_planilha_hash on itens_planilha (documento_hash);
-- Índice de busca por conteúdo de célula fica para quando as consultas reais
-- existirem: sem saber a ordem das colunas do acervo, qualquer índice aqui é
-- chute — e índice não usado só custa escrita.

-- 6. Log de consultas do agente ---------------------------------------------
create table if not exists agent_query_log (
    id              uuid primary key default gen_random_uuid(),
    session_id      uuid,
    usuario         text,
    tipo_fluxo      text check (tipo_fluxo in ('consulta_historico','analise_edital','outro')),
    pergunta        text not null,
    resposta        text,
    chunks_citados  uuid[],
    documentos_citados uuid[],
    modelo          text,
    tokens_input    int,
    tokens_output   int,
    custo_estimado_usd numeric(10,6),
    latencia_ms     int,
    feedback        smallint,
    created_at      timestamptz not null default now()
);
create index if not exists idx_query_log_session on agent_query_log (session_id);

-- ============================================================================
-- Row Level Security — OBRIGATÓRIO no Supabase
--
-- Tudo em `public` é publicado automaticamente pela API REST do Supabase. Sem
-- RLS, qualquer um com a publishable key — que por definição vai embutida no
-- frontend e é pública — consegue ler e escrever o acervo inteiro de editais.
--
-- A postura aqui é negar por padrão: RLS ligado e NENHUMA policy. Com isso
-- ninguém acessa via API. O backend continua funcionando porque fala com o
-- banco por conexão direta (DATABASE_URL), e a secret key ignora RLS por
-- definição — as duas credenciais são de servidor e nunca vão para o cliente.
--
-- Quando entrar login de usuário (Supabase Auth), as policies para o papel
-- `authenticated` entram aqui, numa migração própria.
-- ============================================================================
alter table licitacoes       enable row level security;
alter table licitacao_itens  enable row level security;
alter table documentos       enable row level security;
alter table doc_chunks       enable row level security;
alter table itens_planilha   enable row level security;
alter table agent_query_log  enable row level security;

-- ============================================================================
-- Sobre a RPC `busca_hibrida` do rascunho: NÃO entra aqui, de propósito.
--
-- Ela fundia os dois rankings por RRF dentro do SQL. Só que o mesmo RRF já
-- existe em Python (retrieval/hybrid_search.py) e é o que os 56 testes cobrem.
-- Ter as duas implementações significa manter a fórmula sincronizada em duas
-- linguagens — e a versão testada seria justamente a que NÃO roda em produção.
--
-- Em vez disso o backend faz duas consultas (vetorial e léxica, cada uma com
-- seus filtros e limites) e funde em Python. Custa um round-trip a mais e
-- garante que o comportamento testado offline é o comportamento de produção.
-- Se a latência incomodar com acervo grande, a RPC volta — e aí os testes
-- passam a rodar contra ela.
-- ============================================================================
