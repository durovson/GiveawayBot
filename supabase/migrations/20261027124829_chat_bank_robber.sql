-- Bank Robber: server-only API. All money movements share a transaction.
do $$ begin
    if not exists(select 1 from pg_trigger where tgrelid='public.points'::regclass
        and tgname='trg_apply_manual_points_adjustment' and tgenabled<>'D') then
        raise exception 'Apply holder_bonus_and_manual_adjustment migration first: RP adjustment trigger is required';
    end if;
end $$;
create table public.safe_attacks (
    id bigint generated always as identity primary key,
    chat_id bigint not null,
    command_message_id bigint not null,
    attacker_id bigint not null references public.users(telegram_id),
    victim_id bigint not null references public.users(telegram_id),
    game_day date not null default ((now() at time zone 'Europe/Moscow')::date),
    language text not null check (language in ('ru', 'en')),
    attacker_name text not null,
    victim_name text not null,
    started_at timestamptz not null default clock_timestamp(),
    deadline timestamptz not null default (clock_timestamp() + interval '5 minutes'),
    status text not null default 'pending' check (status in ('pending','stolen','defended','cancelled')),
    preview_amount integer not null check (preview_amount>0),
    amount integer not null default 0 check (amount >= 0),
    burned integer not null default 0 check (burned in (0,5)),
    announcement_id bigint,
    thread_id bigint,
    finished_at timestamptz,
    notified_at timestamptz,
    notification_claimed_until timestamptz,
    check (deadline>started_at),
    check (attacker_id <> victim_id),
    unique (chat_id, command_message_id)
);
create unique index safe_attacks_daily_target on public.safe_attacks(attacker_id,victim_id,game_day) where status<>'cancelled';
create index safe_attacks_due on public.safe_attacks(deadline) where status='pending';
create index safe_attacks_victim on public.safe_attacks(chat_id,victim_id) where status='pending';
create index safe_attacks_daily on public.safe_attacks(attacker_id,game_day);
create index safe_attacks_victim_fk on public.safe_attacks(victim_id);
create index safe_attacks_outbox on public.safe_attacks(finished_at) where notified_at is null and status<>'pending';
alter table public.safe_attacks enable row level security;
revoke all on public.safe_attacks from public, anon, authenticated;
grant select,insert,update on public.safe_attacks to service_role;
revoke all on sequence public.safe_attacks_id_seq from public,anon,authenticated;
grant usage,select on sequence public.safe_attacks_id_seq to service_role;

create function public.start_safe_attack(
    p_chat_id bigint, p_message_id bigint, p_attacker bigint, p_victim bigint,
    p_language text, p_attacker_name text, p_victim_name text, p_thread_id bigint default null
) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare a public.safe_attacks%rowtype; attacker_balance integer; victim_balance integer;
    today date := (clock_timestamp() at time zone 'Europe/Moscow')::date;
begin
    perform pg_advisory_xact_lock(hashtextextended('safe:money-movement',0));
    -- Serialize the daily limit across chats and repeated updates.
    perform pg_advisory_xact_lock(hashtextextended('safe:'||p_attacker,0));
    today := (clock_timestamp() at time zone 'Europe/Moscow')::date;
    select * into a from public.safe_attacks where chat_id=p_chat_id and command_message_id=p_message_id;
    if found then return jsonb_build_object('ok',true,'duplicate',true,'attack',to_jsonb(a)); end if;
    if p_attacker=p_victim then return jsonb_build_object('ok',false,'error','SELF'); end if;
    if not exists(select 1 from public.users where telegram_id=p_attacker)
       or not exists(select 1 from public.users where telegram_id=p_victim) then
        return jsonb_build_object('ok',false,'error','NOT_REGISTERED');
    end if;
    if (select count(*) from public.safe_attacks where attacker_id=p_attacker and game_day=today and status<>'cancelled')>=3 then
        return jsonb_build_object('ok',false,'error','DAILY_LIMIT');
    end if;
    if exists(select 1 from public.safe_attacks where attacker_id=p_attacker and victim_id=p_victim and game_day=today and status<>'cancelled') then
        return jsonb_build_object('ok',false,'error','REPEAT_VICTIM');
    end if;
    insert into public.points(user_id) values(least(p_attacker,p_victim)),(greatest(p_attacker,p_victim))
        on conflict(user_id) do nothing;
    perform user_id from public.points where user_id in(p_attacker,p_victim) order by user_id for update;
    select total_points into attacker_balance from public.points where user_id=p_attacker;
    select total_points into victim_balance from public.points where user_id=p_victim;
    if attacker_balance<15 then return jsonb_build_object('ok',false,'error','LOW_ATTACKER'); end if;
    if victim_balance<=50 then return jsonb_build_object('ok',false,'error','LOW_VICTIM'); end if;
    insert into public.safe_attacks(chat_id,command_message_id,attacker_id,victim_id,game_day,language,
        attacker_name,victim_name,preview_amount,thread_id)
    values(p_chat_id,p_message_id,p_attacker,p_victim,today,case when p_language='ru' then 'ru' else 'en' end,
        p_attacker_name,p_victim_name,least(round(victim_balance::numeric*0.15)::integer,victim_balance-50),p_thread_id)
    returning * into a;
    update public.points set spent_points=coalesce(spent_points,0)+15,
        total_points=total_points-15,updated_at=now() where user_id=p_attacker;
    insert into public.points_transactions(user_id,amount,transaction_type,reference_type,reference_id,idempotency_key)
        values(p_attacker,-15,'SAFE_RESERVE','safe_attack',a.id,'safe:'||a.id||':reserve');
    return jsonb_build_object('ok',true,'attack',to_jsonb(a));
end $$;

create function public.finish_safe_attack(
    p_id bigint, p_reaction_at timestamptz default null, p_reaction_message_id bigint default null,
    p_reaction_user bigint default null, p_reaction_chat bigint default null, p_cancel boolean default false
) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare a public.safe_attacks%rowtype; victim_balance integer; loot integer; defense boolean;
begin
    -- A defense can settle several attacks in one transaction. Take the same
    -- short transaction lock before any attack/points rows to avoid lock cycles.
    perform pg_advisory_xact_lock(hashtextextended('safe:money-movement',0));
    select * into a from public.safe_attacks where id=p_id for update;
    if not found then return jsonb_build_object('ok',false,'error','NOT_FOUND'); end if;
    if a.status<>'pending' then return jsonb_build_object('ok',true,'duplicate',true,'attack',to_jsonb(a)); end if;
    defense := p_reaction_user=a.victim_id and p_reaction_chat=a.chat_id
        and p_reaction_message_id>a.command_message_id
        and p_reaction_at>=date_trunc('second',a.started_at) and p_reaction_at<=a.deadline;
    if not coalesce(defense,false) and not p_cancel and clock_timestamp()<a.deadline+interval '10 seconds' then
        return jsonb_build_object('ok',false,'error','TOO_EARLY');
    end if;
    perform user_id from public.points where user_id in(a.attacker_id,a.victim_id) order by user_id for update;
    if p_cancel or (a.announcement_id is null and not coalesce(defense,false)) then
        -- No public warning was delivered: never steal invisibly.
        update public.points set manual_adjustment=manual_adjustment+15 where user_id=a.attacker_id;
        insert into public.points_transactions(user_id,amount,transaction_type,reference_type,reference_id,idempotency_key)
            values(a.attacker_id,15,'SAFE_REFUND','safe_attack',a.id,'safe:'||a.id||':refund');
        update public.safe_attacks set status='cancelled',finished_at=now(),notified_at=now() where id=a.id returning * into a;
    elsif coalesce(defense,false) then
        update public.points set manual_adjustment=manual_adjustment+10 where user_id=a.victim_id;
        insert into public.points_transactions(user_id,amount,transaction_type,reference_type,reference_id,idempotency_key,
            metadata) values(a.victim_id,10,'SAFE_DEFENSE','safe_attack',a.id,'safe:'||a.id||':defense',jsonb_build_object('burned',5));
        update public.safe_attacks set status='defended',amount=10,burned=5,finished_at=now() where id=a.id returning * into a;
    else
        select total_points into victim_balance from public.points where user_id=a.victim_id;
        loot := greatest(0,least(round(victim_balance::numeric*0.15)::integer,victim_balance-50));
        if loot>0 then
            update public.points set spent_points=coalesce(spent_points,0)+loot,
                total_points=total_points-loot,updated_at=now() where user_id=a.victim_id;
            insert into public.points_transactions(user_id,amount,transaction_type,reference_type,reference_id,idempotency_key)
                values(a.victim_id,-loot,'SAFE_THEFT','safe_attack',a.id,'safe:'||a.id||':debit'),
                    (a.attacker_id,loot,'SAFE_THEFT','safe_attack',a.id,'safe:'||a.id||':credit');
        end if;
        update public.points set manual_adjustment=manual_adjustment+15+loot where user_id=a.attacker_id;
        insert into public.points_transactions(user_id,amount,transaction_type,reference_type,reference_id,idempotency_key)
            values(a.attacker_id,15,'SAFE_REFUND','safe_attack',a.id,'safe:'||a.id||':refund');
        update public.safe_attacks set status='stolen',amount=loot,finished_at=now() where id=a.id returning * into a;
    end if;
    return jsonb_build_object('ok',true,'attack',to_jsonb(a));
end $$;

create function public.react_to_safe_attacks(p_chat_id bigint,p_user_id bigint,p_message_id bigint,p_message_at timestamptz)
returns integer language plpgsql security invoker set search_path=public,pg_temp as $$
declare attack_id bigint; result jsonb; n integer:=0;
begin
    if not exists(select 1 from public.safe_attacks where chat_id=p_chat_id and victim_id=p_user_id
        and status='pending' and command_message_id<p_message_id
        and date_trunc('second',started_at)<=p_message_at and deadline>=p_message_at) then return 0; end if;
    perform pg_advisory_xact_lock(hashtextextended('safe:money-movement',0));
    -- Ordinary messages never register users or send onboarding prompts.
    for attack_id in select id from public.safe_attacks where chat_id=p_chat_id and victim_id=p_user_id
        and status='pending' and command_message_id<p_message_id
        and date_trunc('second',started_at)<=p_message_at and deadline>=p_message_at order by id loop
        result:=public.finish_safe_attack(attack_id,p_message_at,p_message_id,p_user_id,p_chat_id);
        if result->'attack'->>'status'='defended' and not coalesce((result->>'duplicate')::boolean,false) then n:=n+1; end if;
    end loop;
    return n;
end $$;

create function public.claim_safe_notifications() returns setof public.safe_attacks
language sql security invoker set search_path=public,pg_temp as $$
    update public.safe_attacks set notification_claimed_until=now()+interval '60 seconds'
    where id in(select id from public.safe_attacks where status in('stolen','defended') and notified_at is null
        and (notification_claimed_until is null or notification_claimed_until<now())
        order by finished_at,id limit 30 for update skip locked) returning *;
$$;

create function public.get_safe_burned() returns bigint language sql stable security invoker
set search_path=public,pg_temp as $$ select coalesce(sum(burned),0)::bigint from public.safe_attacks $$;

-- Use current credit/debit columns under the row lock, not a stale Python snapshot.
create function public.update_calculated_rp(p_user_id bigint,p_holder_bonus integer,p_calculated integer)
returns integer language plpgsql security invoker set search_path=public,pg_temp as $$
declare result integer;
begin
    insert into public.points(user_id) values(p_user_id) on conflict(user_id) do nothing;
    update public.points set holder_bonus=p_holder_bonus,
        total_points=greatest(0,p_calculated+external_points+manual_adjustment-coalesce(spent_points,0)),updated_at=now()
        where user_id=p_user_id returning total_points into result;
    return result;
end $$;

revoke all on function public.start_safe_attack(bigint,bigint,bigint,bigint,text,text,text,bigint),
    public.finish_safe_attack(bigint,timestamptz,bigint,bigint,bigint,boolean),
    public.react_to_safe_attacks(bigint,bigint,bigint,timestamptz),public.claim_safe_notifications(),
    public.get_safe_burned(),public.update_calculated_rp(bigint,integer,integer) from public,anon,authenticated;
grant execute on function public.start_safe_attack(bigint,bigint,bigint,bigint,text,text,text,bigint),
    public.finish_safe_attack(bigint,timestamptz,bigint,bigint,bigint,boolean),
    public.react_to_safe_attacks(bigint,bigint,bigint,timestamptz),public.claim_safe_notifications(),
    public.get_safe_burned(),public.update_calculated_rp(bigint,integer,integer) to service_role;
