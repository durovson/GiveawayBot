-- Purchased wallet tickets do not expire when a giveaway finishes.
-- Existing per-giveaway balances remain spendable for backward compatibility.
create table public.ticket_wallets (
    user_id bigint primary key references public.users(telegram_id) on delete cascade,
    balance integer not null default 0 check (balance >= 0),
    updated_at timestamptz not null default now()
);
alter table public.ticket_wallets enable row level security;
revoke all on public.ticket_wallets from public, anon, authenticated;
grant select, insert, update on public.ticket_wallets to service_role;

create function public.purchase_ticket_wallet(
    p_user_id bigint, p_offer_code text, p_idempotency_key text
)
returns jsonb language plpgsql security invoker
set search_path = public, pg_temp as $$
declare
    v_offer public.ticket_offers%rowtype;
    v_existing public.points_transactions%rowtype;
    v_points integer;
    v_cost integer;
    v_balance integer;
begin
    if p_idempotency_key is null or length(trim(p_idempotency_key)) = 0 then
        return jsonb_build_object('ok', false, 'error', 'INVALID_REQUEST');
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_idempotency_key, 0));
    select * into v_existing from public.points_transactions
    where idempotency_key = p_idempotency_key;
    if found then
        if v_existing.user_id <> p_user_id or v_existing.transaction_type <> 'ticket_wallet_purchase' then
            return jsonb_build_object('ok', false, 'error', 'INVALID_REQUEST');
        end if;
        return v_existing.metadata || jsonb_build_object('ok', true, 'duplicate', true);
    end if;
    select * into v_offer from public.ticket_offers
    where code = p_offer_code and active = true;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'OFFER_NOT_FOUND');
    end if;
    v_cost := case when v_offer.pricing_mode = 'per_ticket'
        then v_offer.price_rp * v_offer.ticket_count else v_offer.price_rp end;
    if v_offer.ticket_count <= 0 or v_cost <= 0 then
        return jsonb_build_object('ok', false, 'error', 'INVALID_TICKET_OFFER');
    end if;
    select total_points into v_points from public.points
    where user_id = p_user_id for update;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'POINTS_NOT_FOUND');
    end if;
    if coalesce(v_points, 0) < v_cost then
        return jsonb_build_object('ok', false, 'error', 'INSUFFICIENT_POINTS');
    end if;
    if not exists (select 1 from public.users where telegram_id = p_user_id) then
        return jsonb_build_object('ok', false, 'error', 'USER_NOT_FOUND');
    end if;
    insert into public.ticket_wallets (user_id, balance)
    values (p_user_id, v_offer.ticket_count)
    on conflict (user_id) do update
    set balance = ticket_wallets.balance + excluded.balance, updated_at = now()
    returning balance into v_balance;
    update public.points
    set spent_points = coalesce(spent_points, 0) + v_cost,
        total_points = v_points - v_cost, updated_at = now()
    where user_id = p_user_id;
    insert into public.points_transactions (
        user_id, amount, transaction_type, reference_type, idempotency_key, metadata
    ) values (
        p_user_id, -v_cost, 'ticket_wallet_purchase', 'tickets', p_idempotency_key,
        jsonb_build_object('added', v_offer.ticket_count, 'cost', v_cost,
            'available_tickets', v_balance, 'new_balance', v_points - v_cost,
            'offer_code', p_offer_code)
    );
    return jsonb_build_object('ok', true, 'added', v_offer.ticket_count,
        'cost', v_cost, 'available_tickets', v_balance, 'new_balance', v_points - v_cost);
end;
$$;

create function public.spend_ticket_wallet(
    p_user_id bigint, p_giveaway_id bigint, p_amount integer, p_idempotency_key text
)
returns jsonb language plpgsql security invoker
set search_path = public, pg_temp as $$
declare
    v_status text;
    v_used integer;
    v_scoped integer;
    v_wallet integer;
    v_scoped_spend integer;
    v_existing public.giveaway_ticket_spends%rowtype;
begin
    if p_amount is null or p_amount <= 0 or p_idempotency_key is null
        or length(trim(p_idempotency_key)) = 0 then
        return jsonb_build_object('ok', false, 'error', 'INVALID_TICKET_AMOUNT');
    end if;
    perform pg_advisory_xact_lock(hashtextextended('giveaway-ticket-spend:' || p_idempotency_key, 0));
    select * into v_existing from public.giveaway_ticket_spends
    where idempotency_key = p_idempotency_key;
    if found then
        if v_existing.user_id <> p_user_id or v_existing.giveaway_id <> p_giveaway_id then
            return jsonb_build_object('ok', false, 'error', 'INVALID_REQUEST');
        end if;
        select coalesce(balance, 0) into v_wallet from public.ticket_wallets where user_id = p_user_id;
        select coalesce(available_tickets, 0) into v_scoped from public.giveaway_ticket_balances
        where giveaway_id = p_giveaway_id and user_id = p_user_id;
        select tickets_used into v_used from public.participants
        where giveaway_id = p_giveaway_id and user_id = p_user_id;
        return jsonb_build_object('ok', true, 'duplicate', true, 'spent', v_existing.amount,
            'remaining', coalesce(v_wallet, 0) + coalesce(v_scoped, 0), 'tickets_used', v_used);
    end if;
    select status into v_status from public.giveaways where id = p_giveaway_id for share;
    if not found or v_status <> 'active' then
        return jsonb_build_object('ok', false, 'error', 'GIVEAWAY_NOT_ACTIVE');
    end if;
    -- Serialize against joining (which locks users before scoped balances).
    perform 1 from public.users where telegram_id = p_user_id for update;
    select greatest(1, coalesce(tickets_used, 1)) into v_used from public.participants
    where giveaway_id = p_giveaway_id and user_id = p_user_id for update;
    if not found then
        return jsonb_build_object('ok', false, 'error', 'NOT_PARTICIPATING');
    end if;
    select available_tickets into v_scoped from public.giveaway_ticket_balances
    where giveaway_id = p_giveaway_id and user_id = p_user_id for update;
    v_scoped := coalesce(v_scoped, 0);
    select balance into v_wallet from public.ticket_wallets where user_id = p_user_id for update;
    v_wallet := coalesce(v_wallet, 0);
    if v_scoped::bigint + v_wallet < p_amount then
        return jsonb_build_object('ok', false, 'error', 'INSUFFICIENT_TICKETS');
    end if;
    v_scoped_spend := least(v_scoped, p_amount);
    update public.giveaway_ticket_balances
    set available_tickets = available_tickets - v_scoped_spend, updated_at = now()
    where giveaway_id = p_giveaway_id and user_id = p_user_id;
    update public.ticket_wallets set balance = balance - (p_amount - v_scoped_spend), updated_at = now()
    where user_id = p_user_id;
    update public.participants set tickets_used = v_used + p_amount
    where giveaway_id = p_giveaway_id and user_id = p_user_id;
    insert into public.giveaway_ticket_spends (giveaway_id, user_id, amount, idempotency_key)
    values (p_giveaway_id, p_user_id, p_amount, p_idempotency_key);
    return jsonb_build_object('ok', true, 'spent', p_amount,
        'remaining', v_scoped + v_wallet - p_amount, 'tickets_used', v_used + p_amount);
end;
$$;

revoke all on function public.purchase_ticket_wallet(bigint, text, text) from public, anon, authenticated;
revoke all on function public.spend_ticket_wallet(bigint, bigint, integer, text) from public, anon, authenticated;
grant execute on function public.purchase_ticket_wallet(bigint, text, text) to service_role;
grant execute on function public.spend_ticket_wallet(bigint, bigint, integer, text) to service_role;
