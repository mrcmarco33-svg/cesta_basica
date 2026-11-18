-- ============================================================
-- FUSO HORÁRIO DO BANCO (America/Manaus)
-- ============================================================
-- Problema: o banco do Supabase usa UTC. A função liberar_cesta_rpc grava
-- a data/hora da retirada pelo relógio do banco, então o horário ficava
-- 4 horas adiantado (o app já grava no fuso certo desde o PR #1).
--
-- Como usar: Supabase -> SQL Editor -> New query -> cole tudo -> Run.
-- Rode fora do horário de entrega: o último passo reinicia as conexões
-- da API (leva poucos segundos e reconecta sozinho).
-- Pode rodar mais de uma vez.

-- 1) Fuso padrão do banco e da conexão usada pela API (PostgREST).
alter database postgres set timezone to 'America/Manaus';
alter role authenticator set timezone to 'America/Manaus';

-- 2) Reinicia as conexões da API para elas já usarem o novo fuso.
select pg_terminate_backend(pid)
from pg_stat_activity
where usename = 'authenticator'
  and pid <> pg_backend_pid();

-- 3) Conferência: devem aparecer 2 linhas com TimeZone=America/Manaus.
select coalesce(r.rolname, '(banco inteiro)') as aplicado_em, c.config
from pg_db_role_setting s
left join pg_roles r on r.oid = s.setrole
cross join lateral unnest(s.setconfig) as c(config)
where c.config ilike 'timezone=%';
