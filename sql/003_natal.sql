-- ============================================================
-- APP DE CESTAS NATALINAS
-- ============================================================
-- Tabelas separadas das cestas básicas: nada aqui altera o app atual.
-- Reaproveita: usuarios (login) e cadastro_colaboradores (crachás).
--
-- Como usar: Supabase -> SQL Editor -> New query -> cole tudo -> Run.
-- Pode rodar mais de uma vez.

-- Campanha (ex.: "Natal 2026"). Só uma fica ativa por vez.
create table if not exists public.natal_campanhas (
    id              bigserial primary key,
    nome            text not null,
    ativa           boolean not null default true,
    status          text not null default 'ABERTA',   -- ABERTA | FINALIZADA
    estoque_inicial integer,                          -- vazio = sem controle
    criado_em       timestamptz not null default now(),
    criado_por      text,
    finalizado_em   timestamptz,
    finalizado_por  text
);

create unique index if not exists natal_campanhas_uma_ativa
    on public.natal_campanhas (ativa) where ativa;

-- Lista de quem tem direito (1 cesta natalina por pessoa).
create table if not exists public.natal_lista (
    id                 bigserial primary key,
    campanha_id        bigint not null references public.natal_campanhas(id) on delete cascade,
    matricula          text not null,
    matricula_num      bigint,
    nome               text,
    setor              text,
    retirado           boolean not null default false,
    data_hora_retirada timestamptz,
    retirado_por       text,          -- usuário do terminal
    forma_retirada     text,          -- CRACHÁ | MATRÍCULA
    importado_em       timestamptz not null default now(),
    unique (campanha_id, matricula)
);

create index if not exists natal_lista_campanha_num_idx
    on public.natal_lista (campanha_id, matricula_num);

-- Todas as leituras do terminal (inclusive repetidas e não encontradas).
create table if not exists public.natal_historico (
    id                 bigserial primary key,
    campanha_id        bigint references public.natal_campanhas(id) on delete cascade,
    data_hora          timestamptz not null default now(),
    tipo_identificacao text,
    valor_lido         text,
    matricula          text,
    nome               text,
    setor              text,
    resultado          text,          -- ENTREGUE | JA_RETIROU | NAO_ESTA_NA_LISTA | SEM_ESTOQUE | FINALIZADA
    motivo             text,
    usuario            text
);

create index if not exists natal_historico_campanha_idx
    on public.natal_historico (campanha_id, id desc);

-- ------------------------------------------------------------
-- Retirada atômica: impede entregar duas vezes, mesmo com dois
-- terminais lendo o mesmo crachá ao mesmo tempo, e respeita o estoque.
-- ------------------------------------------------------------
create or replace function public.natal_retirar(
    p_lista_id bigint,
    p_usuario  text,
    p_forma    text
) returns jsonb
language plpgsql
as $$
declare
    v_item      public.natal_lista%rowtype;
    v_campanha  public.natal_campanhas%rowtype;
    v_entregues integer;
begin
    select * into v_item from public.natal_lista where id = p_lista_id for update;

    if not found then
        return jsonb_build_object('resultado', 'NAO_ESTA_NA_LISTA');
    end if;

    select * into v_campanha from public.natal_campanhas
    where id = v_item.campanha_id for update;

    if v_campanha.status <> 'ABERTA' then
        return jsonb_build_object('resultado', 'FINALIZADA');
    end if;

    if v_item.retirado then
        return jsonb_build_object(
            'resultado', 'JA_RETIROU',
            'data_hora_retirada', v_item.data_hora_retirada,
            'retirado_por', v_item.retirado_por
        );
    end if;

    if v_campanha.estoque_inicial is not null then
        select count(*) into v_entregues
        from public.natal_lista
        where campanha_id = v_item.campanha_id and retirado;

        if v_entregues >= v_campanha.estoque_inicial then
            return jsonb_build_object('resultado', 'SEM_ESTOQUE');
        end if;
    end if;

    update public.natal_lista
    set retirado = true,
        data_hora_retirada = now(),
        retirado_por = p_usuario,
        forma_retirada = p_forma
    where id = p_lista_id
    returning * into v_item;

    return jsonb_build_object(
        'resultado', 'ENTREGUE',
        'data_hora_retirada', v_item.data_hora_retirada
    );
end;
$$;

-- Segurança (RLS): use a mesma configuração das outras tabelas do projeto.
