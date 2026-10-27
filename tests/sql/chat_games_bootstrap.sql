-- Isolated PostgreSQL-compatible test harness, NOT a production migration.
create role anon;
create role authenticated;
create role service_role bypassrls;
create table public.users(telegram_id bigint primary key, username text,first_name text,language text default 'en');
create table public.points(
    user_id bigint primary key references public.users(telegram_id), packs integer default 0,
    active_referrals integer default 0, holder_bonus integer default 0,
    external_points integer not null default 0, manual_adjustment integer not null default 0,
    spent_points integer default 0,total_points integer default 0,updated_at timestamptz default now()
);
create function public.apply_manual_points_adjustment() returns trigger language plpgsql as $$
begin
    if new.manual_adjustment is distinct from old.manual_adjustment then
        new.total_points:=greatest(0,coalesce(old.total_points,0)+new.manual_adjustment-old.manual_adjustment);
        new.updated_at:=now();
    end if;
    return new;
end $$;
create trigger trg_apply_manual_points_adjustment before update of manual_adjustment on public.points
    for each row execute function public.apply_manual_points_adjustment();
create table public.points_transactions(
    id bigint generated always as identity primary key,user_id bigint references public.users(telegram_id),
    amount integer not null check(amount<>0),transaction_type text not null,reference_type text,
    reference_id bigint,idempotency_key text not null unique,metadata jsonb not null default '{}',created_at timestamptz default now()
);
grant usage on schema public to service_role;
grant select,insert,update on public.users,public.points,public.points_transactions to service_role;
grant usage,select on all sequences in schema public to service_role;
