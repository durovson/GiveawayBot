begin;

alter table public.giveaway_ticket_balances
    drop constraint if exists giveaway_ticket_balances_tickets_check;
alter table public.giveaway_ticket_balances
    add constraint giveaway_ticket_balances_tickets_check check (tickets >= 1);

-- The former "fill to 10" offer becomes a repeatable +10 purchase.
update public.ticket_offers
set ticket_count = 10,
    mode = 'add',
    pricing_mode = 'per_ticket',
    updated_at = now()
where code = 'max';

-- Preserve already joined users' current weight and reopen their balance for top-ups.
update public.giveaway_ticket_balances b
set tickets = greatest(b.tickets, p.tickets_used, 1),
    consumed_at = null,
    updated_at = now()
from public.participants p
join public.giveaways g on g.id = p.giveaway_id and g.status = 'active'
where b.giveaway_id = p.giveaway_id and b.user_id = p.user_id;

create or replace function public.purchase_giveaway_tickets(
    p_user_id bigint,
    p_giveaway_id bigint,
    p_offer_code text,
    p_idempotency_key text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_status text;
    v_offer public.ticket_offers%rowtype;
    v_points public.points%rowtype;
    v_existing public.points_transactions%rowtype;
    v_current integer;
    v_legacy integer;
    v_add integer;
    v_cost integer;
    v_new integer;
    v_new_balance integer;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_idempotency_key, 0));

    select * into v_existing from public.points_transactions
    where idempotency_key = p_idempotency_key;
    if found then
        return jsonb_build_object(
            'ok', true, 'duplicate', true,
            'tickets', coalesce((v_existing.metadata->>'tickets')::integer, 1),
            'added', coalesce((v_existing.metadata->>'added')::integer, 0),
            'cost', abs(v_existing.amount),
            'new_balance', coalesce((v_existing.metadata->>'new_balance')::integer, 0)
        );
    end if;

    select status into v_status from public.giveaways
    where id = p_giveaway_id for share;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'GIVEAWAY_NOT_FOUND');
    end if;
    if v_status <> 'active' then
        return jsonb_build_object('ok', false, 'error', 'GIVEAWAY_NOT_ACTIVE');
    end if;

    select * into v_offer from public.ticket_offers
    where code = p_offer_code and active = true;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'OFFER_NOT_FOUND');
    end if;

    select coalesce(active_tickets, 0) into v_legacy
    from public.users where telegram_id = p_user_id for update;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'USER_NOT_FOUND');
    end if;

    insert into public.giveaway_ticket_balances (giveaway_id, user_id, tickets)
    values (p_giveaway_id, p_user_id, greatest(1, v_legacy))
    on conflict (giveaway_id, user_id) do nothing;

    select tickets into v_current from public.giveaway_ticket_balances
    where giveaway_id = p_giveaway_id and user_id = p_user_id for update;

    v_add := v_offer.ticket_count;
    if v_add <= 0 then
        return jsonb_build_object('ok', false, 'error', 'INVALID_TICKET_AMOUNT');
    end if;
    v_cost := case
        when v_offer.pricing_mode = 'per_ticket' then v_offer.price_rp * v_add
        else v_offer.price_rp
    end;

    select * into v_points from public.points
    where user_id = p_user_id for update;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'POINTS_NOT_FOUND');
    end if;
    if coalesce(v_points.total_points, 0) < v_cost then
        return jsonb_build_object('ok', false, 'error', 'INSUFFICIENT_POINTS');
    end if;

    v_new := v_current + v_add;
    v_new_balance := coalesce(v_points.total_points, 0) - v_cost;

    update public.giveaway_ticket_balances
    set tickets = v_new,
        purchased_rp = purchased_rp + v_cost,
        consumed_at = null,
        updated_at = now()
    where giveaway_id = p_giveaway_id and user_id = p_user_id;

    -- If the user already joined, immediately update their raffle weight.
    update public.participants
    set tickets_used = v_new
    where giveaway_id = p_giveaway_id and user_id = p_user_id;

    update public.users set active_tickets = 0 where telegram_id = p_user_id;
    update public.points
    set spent_points = coalesce(spent_points, 0) + v_cost,
        total_points = v_new_balance,
        updated_at = now()
    where user_id = p_user_id;

    insert into public.points_transactions (
        user_id, amount, transaction_type, reference_type,
        reference_id, idempotency_key, metadata
    ) values (
        p_user_id, -v_cost, 'giveaway_ticket_purchase', 'giveaway',
        p_giveaway_id, p_idempotency_key,
        jsonb_build_object(
            'offer_code', p_offer_code, 'added', v_add,
            'tickets', v_new, 'new_balance', v_new_balance
        )
    );

    return jsonb_build_object(
        'ok', true, 'tickets', v_new, 'added', v_add,
        'cost', v_cost, 'new_balance', v_new_balance
    );
end;
$$;

create or replace function public.join_giveaway_atomic(
    p_giveaway_id bigint,
    p_user_id bigint,
    p_username text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_status text;
    v_legacy integer;
    v_tickets integer;
    v_participant_id bigint;
begin
    select status into v_status from public.giveaways
    where id = p_giveaway_id for share;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'GIVEAWAY_NOT_FOUND');
    end if;
    if v_status <> 'active' then
        return jsonb_build_object('ok', false, 'error', 'GIVEAWAY_NOT_ACTIVE');
    end if;

    select coalesce(active_tickets, 0) into v_legacy from public.users
    where telegram_id = p_user_id for update;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'USER_NOT_FOUND');
    end if;

    insert into public.giveaway_ticket_balances (giveaway_id, user_id, tickets)
    values (p_giveaway_id, p_user_id, greatest(1, v_legacy))
    on conflict (giveaway_id, user_id) do nothing;

    select tickets into v_tickets from public.giveaway_ticket_balances
    where giveaway_id = p_giveaway_id and user_id = p_user_id for update;

    insert into public.participants (giveaway_id, user_id, username, tickets_used)
    values (p_giveaway_id, p_user_id, p_username, v_tickets)
    on conflict (giveaway_id, user_id) do nothing
    returning id into v_participant_id;
    if v_participant_id is null then
        return jsonb_build_object('ok', false, 'error', 'ALREADY_JOINED');
    end if;

    update public.giveaway_ticket_balances set consumed_at = null, updated_at = now()
    where giveaway_id = p_giveaway_id and user_id = p_user_id;
    update public.users set active_tickets = 0 where telegram_id = p_user_id;

    return jsonb_build_object(
        'ok', true, 'participant_id', v_participant_id,
        'tickets_used', v_tickets, 'bonus_tickets_consumed', greatest(0, v_tickets - 1)
    );
end;
$$;

create or replace function public.get_giveaway_ticket_ranking(
    p_giveaway_id bigint,
    p_user_id bigint
)
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    with ranked as (
        select
            user_id,
            username,
            greatest(1, coalesce(tickets_used, 1)) as tickets_used,
            row_number() over (
                order by greatest(1, coalesce(tickets_used, 1)) desc, user_id asc
            ) as rank
        from public.participants
        where giveaway_id = p_giveaway_id
    )
    select jsonb_build_object(
        'top', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'user_id', user_id,
                    'username', username,
                    'tickets_used', tickets_used,
                    'rank', rank
                ) order by rank
            )
            from ranked where rank <= 10
        ), '[]'::jsonb),
        'rank', (select rank from ranked where user_id = p_user_id),
        'count', (select count(*) from ranked)
    );
$$;

revoke all on function public.purchase_giveaway_tickets(bigint, bigint, text, text) from public, anon, authenticated;
revoke all on function public.join_giveaway_atomic(bigint, bigint, text) from public, anon, authenticated;
revoke all on function public.get_giveaway_ticket_ranking(bigint, bigint) from public, anon, authenticated;
grant execute on function public.purchase_giveaway_tickets(bigint, bigint, text, text) to service_role;
grant execute on function public.join_giveaway_atomic(bigint, bigint, text) to service_role;
grant execute on function public.get_giveaway_ticket_ranking(bigint, bigint) to service_role;

commit;
