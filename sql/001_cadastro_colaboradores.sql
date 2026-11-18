-- ============================================================
-- CADASTRO PERMANENTE DE COLABORADORES (matrícula -> crachá)
-- ============================================================
-- Como usar: Supabase -> SQL Editor -> New query -> cole tudo -> Run.
-- Pode rodar mais de uma vez sem problema (não duplica nada).

create table if not exists public.cadastro_colaboradores (
    id             bigserial primary key,
    matricula      text not null unique,
    matricula_num  bigint,
    nome           text,
    setor          text,
    id_cracha      bigint unique,
    criado_em      timestamptz not null default now(),
    atualizado_em  timestamptz not null default now(),
    atualizado_por text
);

create index if not exists cadastro_colaboradores_matricula_num_idx
    on public.cadastro_colaboradores (matricula_num);

-- ------------------------------------------------------------
-- Preenche o cadastro com quem já existe nos períodos
-- (nome/setor do período mais recente de cada matrícula).
-- ------------------------------------------------------------
insert into public.cadastro_colaboradores (matricula, matricula_num, nome, setor)
select distinct on (c.matricula::text)
       c.matricula::text,
       c.matricula_num::bigint,
       c.nome,
       c.setor
from public.colaboradores c
where c.matricula is not null
order by c.matricula::text, c.periodo_id desc
on conflict (matricula) do nothing;

-- Crachás: usa o crachá mais recente de cada matrícula.
-- Se o mesmo crachá passou por duas pessoas, fica com quem o usou por último.
with ultimos as (
    select distinct on (c.matricula::text)
           c.matricula::text as matricula,
           c.id_mat::bigint  as id_mat,
           c.periodo_id
    from public.colaboradores c
    where c.id_mat is not null
    order by c.matricula::text, c.periodo_id desc
),
unicos as (
    select distinct on (id_mat) matricula, id_mat
    from ultimos
    order by id_mat, periodo_id desc
)
update public.cadastro_colaboradores cad
set id_cracha = u.id_mat,
    atualizado_por = 'migração'
from unicos u
where cad.matricula = u.matricula
  and cad.id_cracha is null
  and not exists (
      select 1 from public.cadastro_colaboradores x where x.id_cracha = u.id_mat
  );

-- ------------------------------------------------------------
-- Segurança (RLS)
-- ------------------------------------------------------------
-- O app acessa o Supabase pelo servidor do Streamlit, com a chave dos
-- Secrets. Deixe esta tabela com a mesma configuração de RLS das outras
-- tabelas do projeto (ex.: colaboradores). Se as outras usam RLS com
-- políticas, crie a mesma política aqui.

-- ------------------------------------------------------------
-- Senhas no formato novo (PBKDF2 tem mais de 64 caracteres).
-- Se a coluna já for "text", isso não muda nada.
-- ------------------------------------------------------------
alter table public.usuarios alter column senha type text;
