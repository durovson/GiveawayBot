-- Live integration regression; all fixtures and balances are rolled back.
begin;
set local role service_role;
do $$
declare
    v_result jsonb;
begin
    insert into public.users (telegram_id, username) values
        (-907100701, 'wallet_regression'), (-907100702, 'wallet_empty_regression');
    insert into public.points (user_id, total_points) values (-907100701, 100), (-907100702, 0);
    insert into public.ticket_offers (code, ticket_count, price_rp, pricing_mode) values
        ('__wallet_test_fixed', 2, 10, 'fixed'), ('__wallet_test_unit', 3, 4, 'per_ticket');

    -- Buy before creating a giveaway, using server-side offer pricing.
    v_result := public.purchase_ticket_wallet(-907100701, '__wallet_test_fixed', '__wallet_test_buy1');
    assert (v_result->>'ok')::boolean and (v_result->>'available_tickets')::integer = 2;
    assert (v_result->>'cost')::integer = 10;
    v_result := public.purchase_ticket_wallet(-907100701, '__wallet_test_fixed', '__wallet_test_buy1');
    assert (v_result->>'duplicate')::boolean;
    assert (select balance = 2 from public.ticket_wallets where user_id = -907100701);
    v_result := public.purchase_ticket_wallet(-907100701, '__wallet_test_unit', '__wallet_test_buy2');
    assert (v_result->>'available_tickets')::integer = 5 and (v_result->>'cost')::integer = 12;
    assert (select total_points = 78 and spent_points = 22 from public.points where user_id = -907100701);
    v_result := public.purchase_ticket_wallet(-907100702, '__wallet_test_fixed', '__wallet_test_poor');
    assert v_result->>'error' = 'INSUFFICIENT_POINTS';
    assert not exists (select 1 from public.ticket_wallets where user_id = -907100702);
    v_result := public.purchase_ticket_wallet(-907100701, '__missing_wallet_offer', '__wallet_test_invalid');
    assert v_result->>'error' = 'OFFER_NOT_FOUND';

    insert into public.giveaways (id, title, status) overriding system value
    values (-907100701, 'Wallet regression', 'active');
    v_result := public.spend_ticket_wallet(-907100701, -907100701, 1, '__wallet_test_not_joined');
    assert v_result->>'error' = 'NOT_PARTICIPATING';
    v_result := public.join_giveaway_atomic(-907100701, -907100701, 'wallet_regression');
    assert (v_result->>'ok')::boolean and (v_result->>'tickets_used')::integer = 1;
    assert (select balance = 5 from public.ticket_wallets where user_id = -907100701);
    v_result := public.spend_ticket_wallet(-907100701, -907100701, 2, '__wallet_test_spend');
    assert (v_result->>'ok')::boolean and (v_result->>'remaining')::integer = 3;
    assert (select tickets_used = 3 from public.participants where user_id = -907100701 and giveaway_id = -907100701);
    v_result := public.spend_ticket_wallet(-907100701, -907100701, 2, '__wallet_test_spend');
    assert (v_result->>'duplicate')::boolean;
    assert (select balance = 3 from public.ticket_wallets where user_id = -907100701);
    v_result := public.spend_ticket_wallet(-907100701, -907100701, 4, '__wallet_test_overdraw');
    assert v_result->>'error' = 'INSUFFICIENT_TICKETS';
    assert (select balance = 3 from public.ticket_wallets where user_id = -907100701);

    -- Legacy scoped tickets are spent first, without double-counting entry.
    update public.giveaway_ticket_balances set available_tickets = 2, tickets = 5
    where user_id = -907100701 and giveaway_id = -907100701;
    v_result := public.spend_ticket_wallet(-907100701, -907100701, 3, '__wallet_test_combined');
    assert (v_result->>'remaining')::integer = 2;
    assert (select balance = 2 from public.ticket_wallets where user_id = -907100701);
    assert (select available_tickets = 0 from public.giveaway_ticket_balances where user_id = -907100701 and giveaway_id = -907100701);
    update public.giveaways set status = 'completed' where id = -907100701;
    assert (select balance = 2 from public.ticket_wallets where user_id = -907100701);
    v_result := public.spend_ticket_wallet(-907100701, -907100701, 1, '__wallet_test_finished');
    assert v_result->>'error' = 'GIVEAWAY_NOT_ACTIVE';
    v_result := public.purchase_ticket_wallet(-907100701, '__wallet_test_fixed', '__wallet_test_after');
    assert (v_result->>'ok')::boolean and (v_result->>'available_tickets')::integer = 4;

    assert not has_function_privilege('anon', 'public.purchase_ticket_wallet(bigint,text,text)', 'execute');
    assert not has_function_privilege('authenticated', 'public.spend_ticket_wallet(bigint,bigint,integer,text)', 'execute');
    assert not has_table_privilege('anon', 'public.ticket_wallets', 'select');
end;
$$;
rollback;
