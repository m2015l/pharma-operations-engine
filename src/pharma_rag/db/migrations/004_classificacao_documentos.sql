-- ============================================================================
-- Migração 004 — classificação estruturada de cada documento (item 19 do plano)
--
-- O QUE MUDA
-- `documentos.classificacao jsonb` guarda a saída validada de
-- `pharma_ops.classificacao` (tipo, contratante, executante e grupo
-- Pharma Operations Platform/Enterprise Vendor Hub, disciplinas, tipo de instalação, ISO, período, valor,
-- quantitativos, local — cada campo com a página de origem). O sumário vai na
-- coluna `documentos.resumo`, que já existe desde a 001 e nunca foi preenchida.
--
-- POR QUE JSONB E NÃO COLUNAS
-- O vocabulário (disciplinas, tipos de instalação) ainda vai mudar enquanto o
-- acervo cresce; cada mudança como coluna seria uma migração nova. Os filtros
-- que o agente vai usar ("atestados da Pharma Operations Platform com HVAC") são de
-- containment (`@>`), que o GIN `jsonb_path_ops` atende — índice 2-3x menor
-- que o `jsonb_ops` padrão, e `@>` é o único operador de que precisamos.
--
-- SEGURANÇA
-- Só ADD. Nada é removido ou reescrito: outras sessões escrevem em
-- `documentos` ao mesmo tempo. `lock_timeout` curto para o ALTER não ficar
-- enfileirado atrás de uma transação longa e travar a tabela inteira.
-- RLS de `documentos` já está ligado (001); coluna nova herda — nenhuma
-- policy nova, a postura continua "negar por padrão via API".
--
-- Idempotente: pode rodar mais de uma vez.
-- ============================================================================

set lock_timeout = '5s';

alter table public.documentos
    add column if not exists classificacao jsonb;

comment on column public.documentos.classificacao is
    'Classificação do documento por LLM, validada em código '
    '(src/pharma_ops/classificacao.py). Campo ausente no texto = null. '
    'Gerada por tools/classificar_documentos.py.';

comment on column public.documentos.resumo is
    'Sumário factual de 3 a 5 frases gerado junto com a classificação.';

-- Garante que ninguém grave escalar/array solto no lugar do objeto.
do $$
begin
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.documentos'::regclass
           and conname = 'documentos_classificacao_objeto_check'
    ) then
        alter table public.documentos
            add constraint documentos_classificacao_objeto_check
            check (classificacao is null or jsonb_typeof(classificacao) = 'object');
    end if;
end $$;

create index if not exists idx_documentos_classificacao
    on public.documentos using gin (classificacao jsonb_path_ops);

reset lock_timeout;
