-- No real users, time travel only in fixtures; all changes roll back.
begin;
insert into public.users(telegram_id,username) values
    (-927001,'robber'),(-927002,'victim'),(-927003,'second'),(-927004,'third'),(-927005,'fourth'),(-927006,'poor');
insert into public.points(user_id,total_points,external_points)
    select telegram_id,case when telegram_id=-927006 then 14 else 100 end,
        case when telegram_id=-927006 then 14 else 100 end from public.users where telegram_id between -927006 and -927001;
set local role service_role;
do $$
declare r jsonb; aid bigint; before_balance integer; result_count integer;
begin
    r:=public.start_safe_attack(-100,1,-927001,-927001,'ru','robber','victim');
    assert r->>'error'='SELF';
    r:=public.start_safe_attack(-100,2,-927006,-927002,'ru','poor','victim');
    assert r->>'error'='LOW_ATTACKER';
    r:=public.start_safe_attack(-100,3,-927001,-9999999,'ru','robber','unknown');
    assert r->>'error'='NOT_REGISTERED';
    r:=public.start_safe_attack(-100,4,-927001,-927002,'ru','robber','victim');
    assert (r->>'ok')::boolean;
    aid:=(r->'attack'->>'id')::bigint;
    assert (select total_points=85 and spent_points=15 from public.points where user_id=-927001);
    r:=public.start_safe_attack(-100,4,-927001,-927002,'ru','robber','victim');
    assert (r->>'duplicate')::boolean;
    assert (select total_points=85 from public.points where user_id=-927001);
    r:=public.start_safe_attack(-100,5,-927001,-927002,'ru','robber','victim');
    assert r->>'error'='REPEAT_VICTIM';
    r:=public.finish_safe_attack(aid);
    assert r->>'error'='TOO_EARLY';
    result_count:=public.react_to_safe_attacks(-101,-927002,10,clock_timestamp());
    assert result_count=0; -- Other chat cannot defend.
    result_count:=public.react_to_safe_attacks(-100,-927003,10,clock_timestamp());
    assert result_count=0; -- Other player cannot defend.
    result_count:=public.react_to_safe_attacks(-100,-927002,10,clock_timestamp());
    assert result_count=1;
    result_count:=public.react_to_safe_attacks(-100,-927002,10,clock_timestamp());
    assert result_count=0; -- Replayed defense cannot credit twice.
    assert (select total_points=85 from public.points where user_id=-927001);
    assert (select total_points=110 from public.points where user_id=-927002);
    assert public.get_safe_burned()=5;
    assert (select sum(amount)=-5 from public.points_transactions where reference_type='safe_attack');

    -- Success, round(110*0.15)=17 (not Python's bankers rounding).
    r:=public.start_safe_attack(-100,11,-927003,-927002,'en','second','victim'); aid:=(r->'attack'->>'id')::bigint;
    update public.safe_attacks set announcement_id=12,started_at=now()-interval '6 minutes',deadline=now()-interval '1 minute' where id=aid;
    r:=public.finish_safe_attack(aid);
    assert r->'attack'->>'status'='stolen' and (r->'attack'->>'amount')::integer=17;
    assert (select total_points=93 from public.points where user_id=-927002);
    assert (select total_points=117 from public.points where user_id=-927003);
    r:=public.finish_safe_attack(aid); assert (r->>'duplicate')::boolean;
    assert public.update_calculated_rp(-927003,0,0)=117; -- Credits survive recalculation.
    assert public.update_calculated_rp(-927002,0,0)=93; -- Debits survive recalculation.
    assert public.update_calculated_rp(-927001,0,0)=85; -- Penalty survives recalculation.

    -- Protected floor: a 51 RP target can lose only 1 RP.
    update public.points set external_points=51,total_points=51 where user_id=-927004;
    r:=public.start_safe_attack(-100,20,-927001,-927004,'ru','robber','third'); aid:=(r->'attack'->>'id')::bigint;
    assert (r->'attack'->>'preview_amount')::integer=1;
    update public.safe_attacks set announcement_id=21,started_at=now()-interval '6 minutes',deadline=now()-interval '1 minute' where id=aid;
    r:=public.finish_safe_attack(aid); assert (r->'attack'->>'amount')::integer=1;
    assert (select total_points=50 from public.points where user_id=-927004);
    r:=public.start_safe_attack(-100,22,-927003,-927004,'en','second','third'); assert r->>'error'='LOW_VICTIM';

    r:=public.start_safe_attack(-100,30,-927001,-927005,'ru','robber','fourth'); aid:=(r->'attack'->>'id')::bigint;
    r:=public.start_safe_attack(-100,31,-927001,-927003,'ru','robber','second'); assert r->>'error'='DAILY_LIMIT';
    assert (select game_day=(clock_timestamp() at time zone 'Europe/Moscow')::date from public.safe_attacks where id=aid);
    -- Unannounced attacks after a restart are cancelled, not stolen.
    select total_points into before_balance from public.points where user_id=-927001;
    update public.safe_attacks set started_at=now()-interval '6 minutes',deadline=now()-interval '1 minute' where id=aid;
    r:=public.finish_safe_attack(aid); assert r->'attack'->>'status'='cancelled';
    assert (select total_points=before_balance+15 from public.points where user_id=-927001);
    r:=public.start_safe_attack(-100,32,-927001,-927005,'ru','robber','fourth');
    assert (r->>'ok')::boolean; -- Cancelled warnings do not consume daily quota/target.
    aid:=(r->'attack'->>'id')::bigint;
    r:=public.finish_safe_attack(aid,p_cancel=>true); assert r->'attack'->>'status'='cancelled';

    -- Multiple attackers, one message defeats all of them.
    r:=public.start_safe_attack(-100,40,-927004,-927005,'en','third','fourth');
    r:=public.start_safe_attack(-100,41,-927003,-927005,'en','second','fourth');
    result_count:=public.react_to_safe_attacks(-100,-927005,42,clock_timestamp()); assert result_count=2;
    assert public.get_safe_burned()=15;
    assert (select total_points=120 from public.points where user_id=-927005);
    -- Outbox claims are exclusive until their leases expire.
    select count(*) into result_count from public.claim_safe_notifications(); assert result_count=5;
    select count(*) into result_count from public.claim_safe_notifications(); assert result_count=0;
    assert not has_function_privilege('anon','public.start_safe_attack(bigint,bigint,bigint,bigint,text,text,text,bigint)','EXECUTE');
    assert not has_table_privilege('authenticated','public.safe_attacks','SELECT');
end $$;
reset role;
insert into public.users(telegram_id,username) values(-928001,'boundary_robber'),(-928002,'boundary_victim'),(-928003,'other_robber');
insert into public.points(user_id,total_points,external_points) values(-928001,100,100),(-928002,100,100),(-928003,100,100);
set local role service_role;
set local timezone='Pacific/Honolulu';
do $$
declare r jsonb; aid bigint; other_id bigint; count_defended integer;
begin
    r:=public.start_safe_attack(-200,1,-928001,-928002,'en','A','B'); aid:=(r->'attack'->>'id')::bigint;
    assert (select game_day=(clock_timestamp() at time zone 'Europe/Moscow')::date from public.safe_attacks where id=aid);
    update public.safe_attacks set announcement_id=2,started_at=now()-interval '6 minutes',deadline=now()-interval '1 minute' where id=aid;
    -- A message after the deadline is not a defense, even before settlement.
    count_defended:=public.react_to_safe_attacks(-200,-928002,3,now()); assert count_defended=0;
    -- Price at completion, not the 15 RP preview: the balance fell to 60 RP.
    update public.points set external_points=60,total_points=60 where user_id=-928002;
    r:=public.finish_safe_attack(aid);
    assert (r->'attack'->>'amount')::integer=9;
    assert (select total_points=51 from public.points where user_id=-928002);
    r:=public.start_safe_attack(-200,4,-928003,-928002,'en','C','B'); aid:=(r->'attack'->>'id')::bigint;
    update public.safe_attacks set announcement_id=5,started_at=now()-interval '6 minutes',deadline=now()-interval '1 minute' where id=aid;
    -- If the victim spends below the floor during the attack, nothing is stolen.
    update public.points set total_points=40,spent_points=20 where user_id=-928002;
    r:=public.finish_safe_attack(aid);
    assert (r->'attack'->>'amount')::integer=0;
    assert (select total_points=100 from public.points where user_id=-928003);

    -- The next Moscow day releases the target limit.
    update public.safe_attacks set game_day=game_day-1 where attacker_id=-928001;
    update public.points set total_points=100,external_points=100,spent_points=0 where user_id=-928002;
    r:=public.start_safe_attack(-200,10,-928001,-928002,'en','A','B');
    assert (r->>'ok')::boolean; aid:=(r->'attack'->>'id')::bigint;
    update public.safe_attacks set announcement_id=11 where id=aid;
    -- Timestamp exactly at the deadline is a valid defense.
    select public.react_to_safe_attacks(-200,-928002,12,deadline) into count_defended
        from public.safe_attacks where id=aid;
    assert count_defended=1;
    assert (select status='defended' from public.safe_attacks where id=aid);
end $$;
rollback;
