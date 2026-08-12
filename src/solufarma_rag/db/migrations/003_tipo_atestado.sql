-- ============================================================================
-- Migração 003 — `atestado` como tipo de documento de primeira classe
--
-- POR QUE
-- O DDL original previa `edital | ata | resultado | anexo | proposta | recurso
-- | outro`, desenhado a partir do fluxo de uma licitação em andamento. O
-- primeiro documento real do acervo não é nada disso: é uma CAT (Certidão de
-- Acervo Técnico do CAU) com atestado de capacidade técnica — a prova de que a
-- Solufarma executou determinada obra.
--
-- A equipe chama esses documentos de "Atestado" (confirmado 2026-08-11), e eles
-- são justamente o material que responde a pergunta central do produto: "já
-- fizemos isso antes?". Deixá-los em `outro` jogaria no balaio genérico o tipo
-- de documento de maior valor de consulta, e tornaria o filtro por tipo inútil
-- exatamente onde ele mais importa.
--
-- Idempotente: descobre o nome real do CHECK antes de dropar (o Postgres nomeia
-- automaticamente, e o nome varia se a tabela foi criada por outro caminho).
-- ============================================================================

do $$
declare
    nome_constraint text;
begin
    select conname into nome_constraint
      from pg_constraint
     where conrelid = 'documentos'::regclass
       and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%tipo%';

    if nome_constraint is not null then
        execute format('alter table documentos drop constraint %I', nome_constraint);
    end if;
end $$;

alter table documentos
    add constraint documentos_tipo_check
    check (tipo in (
        'edital',
        'ata',
        'resultado',
        'atestado',   -- CAT / atestado de capacidade técnica (novo na 003)
        'anexo',
        'proposta',
        'recurso',
        'outro'
    ));

-- Reclassifica o que já entrou como 'outro' por falta do tipo correto.
-- Restrito ao título conhecido de propósito: um UPDATE amplo em 'outro'
-- reclassificaria documentos que legitimamente não são atestado.
update documentos
   set tipo = 'atestado'
 where tipo = 'outro'
   and titulo ilike '%CAT%';
