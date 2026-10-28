
-- One-time, audit-logged reconciliation of legacy BANK ROBBER RP operations.
-- Must be run ONLY against the existing GiveawayBot project's DB, after
-- disabling old /safe routes and the legacy safe-attack worker.
create table if not exists public.arena_rp_grants (
  user_id bigint primary key references public.users(telegram_id),
  granted_rp integer not null default 15,
  granted_at timestamptz not null default now()
);
create table if not exists public.arena_legacy_restitutions (
  attack_id bigint primary key references public.safe_attacks(id),
  attacker_id bigint not null references public.users(telegram_id),
  victim_id bigint not null references public.users(telegram_id),
  attacker_refund integer not null default 0,
  attacker_clawback integer not null default 0,
  victim_refund integer not null default 0,
  restored_at timestamptz not null default now()
);
alter table public.arena_rp_grants enable row level security;
alter table public.arena_legacy_restitutions enable row level security;
revoke all on public.arena_rp_grants,public.arena_legacy_restitutions from public,anon,authenticated;
grant select,insert on public.arena_rp_grants,public.arena_legacy_restitutions to service_role;

do $$
declare a record; ra integer; cv integer; rv integer; uid bigint;
begin
  perform pg_advisory_xact_lock(hashtextextended('safe:money-movement',0));
  perform pg_advisory_xact_lock(hashtextextended('arena:money',0));

  insert into public.points(user_id)
    select telegram_id from public.users on conflict(user_id) do nothing;

  -- The one-time +15 RP is independent of the user's new pumpkin wallet.
  for uid in select telegram_id from public.users order by telegram_id loop
    insert into public.arena_rp_grants(user_id) values(uid) on conflict do nothing;
    if found then
      update public.points set manual_adjustment=manual_adjustment+15,updated_at=now()
        where user_id=uid;
      insert into public.points_transactions(
        user_id,amount,transaction_type,reference_type,reference_id,idempotency_key
      ) values(uid,15,'ARENA_LAUNCH_BONUS','arena',0,'arena:v2:bonus:'||uid)
      on conflict(idempotency_key) do nothing;
    end if;
  end loop;

  for a in select * from public.safe_attacks
        where status in ('pending','stolen','defended')
        order by id loop
    ra:=case when a.status='pending' then 15 when a.status='defended' then a.burned else 0 end;
    cv:=case when a.status='stolen' then a.amount else 0 end;
    rv:=case when a.status='stolen' then a.amount else 0 end;
    insert into public.arena_legacy_restitutions(
      attack_id,attacker_id,victim_id,attacker_refund,attacker_clawback,victim_refund
    ) values(a.id,a.attacker_id,a.victim_id,ra,cv,rv) on conflict(attack_id) do nothing;
    if not found then continue; end if;

    if ra>0 then
      update public.points set manual_adjustment=manual_adjustment+ra,updated_at=now()
        where user_id=a.attacker_id;
      insert into public.points_transactions(
        user_id,amount,transaction_type,reference_type,reference_id,idempotency_key
      ) values(a.attacker_id,ra,'ARENA_RESTITUTION','safe_attack',a.id,
         'arena:v2:restore:attacker:'||a.id)
      on conflict(idempotency_key) do nothing;
    end if;
    if cv>0 then
      -- Historical stolen RP leaves the attacker. A negative adjustment
      -- remains as a debt if that RP has already been spent.
      update public.points set manual_adjustment=manual_adjustment-cv,updated_at=now()
        where user_id=a.attacker_id;
      insert into public.points_transactions(
        user_id,amount,transaction_type,reference_type,reference_id,idempotency_key
      ) values(a.attacker_id,-cv,'ARENA_RESTITUTION','safe_attack',a.id,
         'arena:v2:clawback:'||a.id)
      on conflict(idempotency_key) do nothing;
    end if;
    if rv>0 then
      update public.points set manual_adjustment=manual_adjustment+rv,updated_at=now()
        where user_id=a.victim_id;
      insert into public.points_transactions(
        user_id,amount,transaction_type,reference_type,reference_id,idempotency_key
      ) values(a.victim_id,rv,'ARENA_RESTITUTION','safe_attack',a.id,
         'arena:v2:restore:victim:'||a.id)
      on conflict(idempotency_key) do nothing;
    end if;
    if a.status='pending' then
      update public.safe_attacks set status='cancelled',finished_at=now(),notified_at=now()
        where id=a.id and status='pending';
    end if;
  end loop;
end $$;
