
-- BANK ROBBER ARENA V2. Apply on the GiveAwayBot Supabase project ONLY,
-- never on the unrelated STRS | TG database. Service-role RPCs are server-only.
create table if not exists public.arena_wallets (
  user_id bigint primary key references public.users(telegram_id),
  balance bigint not null default 50 check (balance >= 0),
  updated_at timestamptz not null default now()
);
create table if not exists public.arena_ledger (
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(telegram_id),
  delta bigint not null,
  event text not null,
  ref text not null,
  created_at timestamptz not null default now(),
  unique (user_id, ref)
);
create table if not exists public.arena_fights (
  id uuid primary key default gen_random_uuid(),
  host_id bigint not null references public.users(telegram_id),
  guest_id bigint references public.users(telegram_id),
  host_name text not null,
  guest_name text,
  stake bigint not null check (stake >= 15),
  chat_id bigint not null,
  announcement_id bigint,
  language text not null default 'en' check (language in ('en','ru')),
  status text not null default 'waiting' check (status in ('waiting','finished','cancelled','expired')),
  winner_id bigint references public.users(telegram_id),
  loser_id bigint references public.users(telegram_id),
  created_at timestamptz not null default clock_timestamp(),
  deadline timestamptz not null default (clock_timestamp() + interval '5 minutes'),
  matched_at timestamptz,
  reveal_at timestamptz,
  notified_at timestamptz,
  notification_claimed_at timestamptz,
  unique (host_id, id),
  check (guest_id is null or guest_id <> host_id),
  check (winner_id is null or winner_id in (host_id,guest_id))
);
create index if not exists arena_waiting_idx on public.arena_fights(deadline) where status='waiting';
create index if not exists arena_results_idx on public.arena_fights(reveal_at) where status='finished' and notified_at is null;
create unique index if not exists arena_one_waiting_per_host on public.arena_fights(host_id) where status='waiting';

alter table public.arena_wallets enable row level security;
alter table public.arena_ledger enable row level security;
alter table public.arena_fights enable row level security;
revoke all on public.arena_wallets,public.arena_ledger,public.arena_fights from public,anon,authenticated;
grant select,insert,update on public.arena_wallets,public.arena_fights to service_role;
grant select,insert on public.arena_ledger to service_role;
revoke all on sequence public.arena_ledger_id_seq from public,anon,authenticated;
grant usage,select on sequence public.arena_ledger_id_seq to service_role;

create or replace function public.arena_balance(p_user_id bigint)
returns bigint language plpgsql security invoker set search_path=public,pg_temp as $$
declare v bigint;
begin
  if not exists(select 1 from public.users where telegram_id=p_user_id) then return null; end if;
  insert into public.arena_wallets(user_id) values(p_user_id) on conflict do nothing;
  select balance into v from public.arena_wallets where user_id=p_user_id;
  return v;
end $$;

create or replace function public.arena_convert(p_user_id bigint, p_rp integer, p_key text)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare p public.points%rowtype; v bigint;
begin
  if p_rp not between 1 and 10000 or length(coalesce(p_key,'')) not between 4 and 120 then
    return jsonb_build_object('ok',false,'error','INVALID');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('arena:money',0));
  if exists(select 1 from public.arena_ledger where user_id=p_user_id and ref='convert:'||p_key) then
    return jsonb_build_object('ok',true,'duplicate',true,'balance',public.arena_balance(p_user_id));
  end if;
  select * into p from public.points where user_id=p_user_id for update;
  if not found or p.total_points < p_rp then
    return jsonb_build_object('ok',false,'error','RP_LOW');
  end if;
  insert into public.arena_wallets(user_id) values(p_user_id) on conflict do nothing;
  update public.points set spent_points=coalesce(spent_points,0)+p_rp,
     total_points=total_points-p_rp,updated_at=now() where user_id=p_user_id;
  insert into public.points_transactions(user_id,amount,transaction_type,reference_type,reference_id,idempotency_key)
     values(p_user_id,-p_rp,'ARENA_CONVERT','arena',0,'arena:convert:'||p_key);
  update public.arena_wallets set balance=balance+p_rp*100,updated_at=now() where user_id=p_user_id
     returning balance into v;
  insert into public.arena_ledger(user_id,delta,event,ref) values(p_user_id,p_rp*100,'CONVERT','convert:'||p_key);
  return jsonb_build_object('ok',true,'balance',v,'rp_used',p_rp);
end $$;

create or replace function public.arena_open(p_user_id bigint,p_stake bigint,p_chat_id bigint,p_name text,p_language text)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare f public.arena_fights%rowtype; w bigint;
begin
  if p_stake < 15 or p_stake > 100000000 or p_chat_id = 0 then
    return jsonb_build_object('ok',false,'error','INVALID');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('arena:money',0));
  if exists(select 1 from public.arena_fights where host_id=p_user_id and status='waiting') then
    return jsonb_build_object('ok',false,'error','ALREADY_WAITING');
  end if;
  insert into public.arena_wallets(user_id) values(p_user_id) on conflict do nothing;
  select balance into w from public.arena_wallets where user_id=p_user_id for update;
  -- 50 🎃 is non-burnable. Entry requires at least 20 spendable 🎃.
  if w < 70 or w - p_stake < 50 then
    return jsonb_build_object('ok',false,'error','INSUFFICIENT');
  end if;
  insert into public.arena_fights(host_id,stake,chat_id,host_name,language)
    values(p_user_id,p_stake,p_chat_id,left(p_name,80),case when p_language='ru' then 'ru' else 'en' end)
    returning * into f;
  update public.arena_wallets set balance=balance-p_stake,updated_at=now() where user_id=p_user_id;
  insert into public.arena_ledger(user_id,delta,event,ref)
    values(p_user_id,-p_stake,'RESERVE','fight:'||f.id||':host');
  return jsonb_build_object('ok',true,'fight',to_jsonb(f),'balance',w-p_stake);
end $$;

create or replace function public.arena_join(p_id uuid,p_user_id bigint,p_name text)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare f public.arena_fights%rowtype; w bigint; win bigint; lose bigint;
begin
  perform pg_advisory_xact_lock(hashtextextended('arena:money',0));
  select * into f from public.arena_fights where id=p_id for update;
  if not found then return jsonb_build_object('ok',false,'error','NOT_FOUND'); end if;
  if f.status='finished' and f.guest_id=p_user_id then
    return jsonb_build_object('ok',true,'duplicate',true,'fight',to_jsonb(f));
  end if;
  if f.status <> 'waiting' or clock_timestamp()>=f.deadline or f.announcement_id is null then
    return jsonb_build_object('ok',false,'error','CLOSED');
  end if;
  if f.host_id=p_user_id then return jsonb_build_object('ok',false,'error','SELF'); end if;
  insert into public.arena_wallets(user_id) values(p_user_id) on conflict do nothing;
  select balance into w from public.arena_wallets where user_id=p_user_id for update;
  if w < 70 or w-f.stake < 50 then
    return jsonb_build_object('ok',false,'error','INSUFFICIENT');
  end if;
  update public.arena_wallets set balance=balance-f.stake,updated_at=now() where user_id=p_user_id;
  insert into public.arena_ledger(user_id,delta,event,ref)
    values(p_user_id,-f.stake,'RESERVE','fight:'||f.id||':guest');
  if random() < 0.5 then win:=f.host_id;lose:=p_user_id;
  else win:=p_user_id;lose:=f.host_id; end if;
  update public.arena_wallets set balance=balance+f.stake*2,updated_at=now()
    where user_id=win;
  insert into public.arena_ledger(user_id,delta,event,ref)
    values(win,f.stake*2,'WIN','fight:'||f.id||':prize');
  update public.arena_fights set guest_id=p_user_id,guest_name=left(p_name,80),
    winner_id=win,loser_id=lose,status='finished',matched_at=clock_timestamp(),
    reveal_at=clock_timestamp()+interval '12 seconds' where id=f.id returning * into f;
  return jsonb_build_object('ok',true,'fight',to_jsonb(f));
end $$;

create or replace function public.arena_cancel(p_id uuid,p_user_id bigint,p_expire boolean default false)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare f public.arena_fights%rowtype;
begin
  perform pg_advisory_xact_lock(hashtextextended('arena:money',0));
  select * into f from public.arena_fights where id=p_id for update;
  if not found then return jsonb_build_object('ok',false,'error','NOT_FOUND'); end if;
  if f.status<>'waiting' then return jsonb_build_object('ok',false,'error','CLOSED'); end if;
  if not p_expire and f.host_id<>p_user_id then return jsonb_build_object('ok',false,'error','FORBIDDEN'); end if;
  if p_expire and f.deadline>clock_timestamp() and f.announcement_id is not null then
    return jsonb_build_object('ok',false,'error','TOO_EARLY');
  end if;
  update public.arena_wallets set balance=balance+f.stake,updated_at=now() where user_id=f.host_id;
  insert into public.arena_ledger(user_id,delta,event,ref) values(f.host_id,f.stake,'REFUND','fight:'||f.id||':refund');
  update public.arena_fights set status=case when p_expire then 'expired' else 'cancelled' end
    where id=f.id returning * into f;
  return jsonb_build_object('ok',true,'fight',to_jsonb(f));
end $$;

create or replace function public.arena_expire()
returns setof public.arena_fights language plpgsql security invoker set search_path=public,pg_temp as $$
declare f record; result jsonb;
begin
  for f in select id from public.arena_fights
    where status='waiting' and (deadline<clock_timestamp() or
         (announcement_id is null and created_at<clock_timestamp()-interval '30 seconds'))
    order by created_at limit 50 loop
    result:=public.arena_cancel(f.id,0,true);
    if coalesce((result->>'ok')::boolean,false) then
      return query select * from public.arena_fights where id=f.id;
    end if;
  end loop;
end $$;

create or replace function public.arena_claim_results()
returns setof public.arena_fights language sql security invoker set search_path=public,pg_temp as $$
  update public.arena_fights set notification_claimed_at=clock_timestamp()
  where id in (
    select id from public.arena_fights where status='finished' and notified_at is null
      and reveal_at<=clock_timestamp()
      and (notification_claimed_at is null or notification_claimed_at<clock_timestamp()-interval '60 seconds')
    order by reveal_at limit 20 for update skip locked
  ) returning *;
$$;

revoke all on function public.arena_balance(bigint),public.arena_convert(bigint,integer,text),
  public.arena_open(bigint,bigint,bigint,text,text),public.arena_join(uuid,bigint,text),
  public.arena_cancel(uuid,bigint,boolean),public.arena_expire(),public.arena_claim_results()
  from public,anon,authenticated;
grant execute on function public.arena_balance(bigint),public.arena_convert(bigint,integer,text),
  public.arena_open(bigint,bigint,bigint,text,text),public.arena_join(uuid,bigint,text),
  public.arena_cancel(uuid,bigint,boolean),public.arena_expire(),public.arena_claim_results()
  to service_role;
