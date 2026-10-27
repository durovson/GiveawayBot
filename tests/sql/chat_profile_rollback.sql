begin;
insert into public.chats(chat_id,title) values(-928001,'before');
insert into public.chats(chat_id,title) values(-928001,'after') on conflict(chat_id) do update set title=excluded.title;
do $$begin
    assert (select title='after' and updated_at is not null from public.chats where chat_id=-928001),'chat upsert trigger';
end$$;
insert into public.users(telegram_id) values(-928001),(-928002);
insert into public.points(user_id,total_points,packs,active_referrals) values(-928001,1000000,3,0),(-928002,1000000,2,0);
insert into public.safe_attacks(chat_id,command_message_id,attacker_id,victim_id,language,attacker_name,victim_name,status,preview_amount,amount,game_day)
values
(-928001,1,-928001,-928002,'ru','a','b','stolen',1,15,'2026-01-01'),
(-928001,2,-928001,-928002,'ru','a','b','defended',1,0,'2026-01-02'),
(-928001,3,-928002,-928001,'ru','b','a','defended',1,0,'2026-01-03'),
(-928001,4,-928002,-928001,'ru','b','a','stolen',1,15,'2026-01-04'),
(-928001,5,-928001,-928002,'ru','a','b','stolen',1,0,'2026-01-05'),
(-928001,6,-928001,-928002,'ru','a','b','cancelled',1,0,'2026-01-06'),
(-928001,7,-928001,-928002,'ru','a','b','pending',1,0,'2026-01-07');
set local role service_role;
do $$declare p jsonb;begin
    p:=public.get_chat_game_profile(-928001);
    assert p->>'wins'='2' and p->>'losses'='2','settled positive loot and defenses only';
    assert p->>'balance'='1000000' and p->>'rank'='1','same tie ordering as /top';
    assert public.get_chat_game_profile(-928002)->>'rank'='2','packs tie breaker';
    assert public.get_chat_game_profile(-999999)->>'balance'='0','missing points fallback';
    assert not has_function_privilege('anon','public.get_chat_game_profile(bigint)','execute'),'profile RPC private';
end$$;
rollback;
