-- 004_qualidade_itens.sql — a qualidade da leitura viaja com o dado.
--
-- POR QUE ESTA MIGRAÇÃO EXISTE
-- O VLM já sabia que não tinha conseguido ler certas células: a página 5 do
-- CAT SJC-003369 veio com confiança 0.55 e a observação nomeando as linhas que
-- os carimbos cobriram. Essa informação morria no JSON de extração e nunca
-- chegava ao banco. Sem ela, uma célula tapada por carimbo fica idêntica à
-- célula de um cabeçalho de seção — que é legitimamente vazia — e um
-- SUM(quantidade) devolve um total menor que o real SEM ERRO NENHUM.
--
-- Idempotente: pode rodar quantas vezes quiser.

alter table itens_planilha
    add column if not exists status      text,
    add column if not exists confianca   real,
    add column if not exists observacoes text;

-- Os quatro estados produzidos por chunking.classificar_lacuna():
--   ok       — linha completa;
--   vazio    — célula vazia sem sinal de problema (cabeçalho de seção);
--   ilegivel — o modelo nomeou ESTA linha como ilegível: o valor existe no
--              papel e não foi capturado. É o que precisa de preenchimento;
--   suspeita — página abaixo do limiar de confiança, sem identificação de quais
--              linhas. Não dá para saber se a lacuna é estrutural ou perdida;
--   corrigido_manual — valor preenchido por uma pessoa a partir do documento
--              original, via tools/relatorio_lacunas.py --aplicar. Fica marcado
--              para sempre: dado vindo de leitura humana não se confunde com
--              dado extraído, e a origem importa numa auditoria.
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'itens_planilha_status_check'
    ) then
        alter table itens_planilha
            add constraint itens_planilha_status_check
            check (status is null or status in
                ('ok','vazio','ilegivel','suspeita','corrigido_manual'));
    end if;
end $$;

-- Linhas que precisam de atenção humana são uma fração pequena da tabela, e a
-- consulta que as busca é sempre a mesma. Índice parcial: só indexa o que
-- interessa, em vez de carregar as ~800 linhas boas de cada documento.
create index if not exists idx_itens_planilha_revisar
    on itens_planilha (documento_id, pagina)
    where status in ('ilegivel','suspeita');

comment on column itens_planilha.status is
    'ok | vazio | ilegivel | suspeita — ver chunking.classificar_lacuna()';
comment on column itens_planilha.confianca is
    'Confiança da PÁGINA de origem (0-1). 1.0 para texto nativo.';
comment on column itens_planilha.observacoes is
    'Observação do VLM sobre a página. Preenchida só quando status != ok.';
