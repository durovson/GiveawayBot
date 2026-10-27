-- Existing chats trigger set_updated_at() requires this column on UPDATE/upsert.
alter table public.chats add column if not exists updated_at timestamptz not null default now();

create or replace function public.get_chat_game_profile(p_user_id bigint)
returns jsonb language sql stable security invoker set search_path=public,pg_temp as $$
    with ranking as (
        select user_id,total_points,
            row_number() over(order by total_points desc,packs desc,active_referrals desc,user_id asc) as position
        from public.points
    ), outcomes as (
        select
            count(*) filter(where (attacker_id=p_user_id and status='stolen' and amount>0)
                or (victim_id=p_user_id and status='defended')) as wins,
            count(*) filter(where (attacker_id=p_user_id and status='defended')
                or (victim_id=p_user_id and status='stolen' and amount>0)) as losses
        from public.safe_attacks where attacker_id=p_user_id or victim_id=p_user_id
    )
    select jsonb_build_object(
        'balance',coalesce((select total_points from ranking where user_id=p_user_id),0),
        'rank',(select position from ranking where user_id=p_user_id),
        'wins',outcomes.wins,'losses',outcomes.losses
    ) from outcomes;
$$;
revoke all on function public.get_chat_game_profile(bigint) from public,anon,authenticated;
grant execute on function public.get_chat_game_profile(bigint) to service_role;
notify pgrst,'reload schema';
