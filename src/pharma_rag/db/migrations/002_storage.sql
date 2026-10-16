-- ============================================================================
-- Migração 002 — bucket de Storage para os PDFs originais
--
-- Aplicar com `python tools/setup_supabase.py --apply` (aplica todas as
-- migrações `NNN_*.sql` em ordem). Idempotente.
--
-- POR QUE EXISTE
-- A migração 001 cria o schema relacional inteiro, mas o Storage do Supabase
-- não vive em `public` — vive em `storage.buckets`, tabela própria. O bucket
-- ficou de fora e ninguém percebeu porque nada tentou gravar nele ainda.
--
-- É pré-requisito DURO da indexação: `documentos.storage_path` é NOT NULL, então
-- nenhuma linha entra em `documentos` sem que o PDF já esteja no Storage. Sem
-- este bucket, o passo de cadastro do documento (workflows/indexacao.md §4) não
-- tem para onde subir o arquivo.
--
-- POR QUE PRIVADO
-- Um bucket público gera URL aberta na internet — qualquer um com o link lê o
-- arquivo, sem login. São documentos de licitação de um cliente. A postura é a
-- mesma da 001: negar por padrão. O backend acessa por conexão direta com a
-- secret key, que ignora RLS por definição; o frontend nunca fala com o Storage
-- direto, recebe URL assinada com expiração.
-- ============================================================================

insert into storage.buckets (id, name, public, file_size_limit)
values (
    'documentos',
    'documentos',
    false,
    -- 104857600 = 100 MiB. O maior arquivo do acervo hoje tem 11,2 MB, mas
    -- edital escaneado com anexos passa disso com facilidade. Limite existe
    -- para barrar upload acidental de algo absurdo, não para apertar o acervo.
    104857600
)
on conflict (id) do nothing;

-- MIME types: deliberadamente SEM allowlist.
--
-- `documentos.tipo` aceita 'anexo', e anexo de edital vem em qualquer formato
-- (.docx de planilha de composição, .zip de projeto, imagem de croqui). Uma
-- allowlist chutada agora rejeitaria arquivo legítimo em produção, com erro
-- que aparece só na hora do upload. Quando o acervo real mostrar quais formatos
-- de fato existem, a allowlist entra numa migração própria.

-- ============================================================================
-- Sobre policies de RLS em `storage.objects`: NÃO entram aqui, de propósito.
--
-- O Supabase já cria `storage.objects` com RLS ligado. Sem policy nenhuma,
-- ninguém acessa via API — que é exatamente a postura da 001 para as 6 tabelas
-- de `public`. O backend continua funcionando porque a secret key ignora RLS.
--
-- Quando entrar login de usuário (Supabase Auth), as policies para o papel
-- `authenticated` entram junto com as de `public`, numa migração própria.
-- ============================================================================
