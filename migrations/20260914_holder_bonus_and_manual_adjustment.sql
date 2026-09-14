begin;

-- A current holder receives the same 50 RP bonus as an OG holder, never both.
alter table public.users
    add column if not exists holder_join_bonus_awarded_at timestamptz;

-- This is the only field an operator needs to edit for manual corrections.
-- Positive values add RP; negative values remove RP.
alter table public.points
    add column if not exists manual_adjustment integer not null default 0;

create or replace function public.apply_manual_points_adjustment()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    if new.manual_adjustment is distinct from old.manual_adjustment then
        new.total_points := greatest(
            0,
            coalesce(old.total_points, 0)
                + coalesce(new.manual_adjustment, 0)
                - coalesce(old.manual_adjustment, 0)
        );
        new.updated_at := now();
    end if;
    return new;
end;
$$;

drop trigger if exists trg_apply_manual_points_adjustment on public.points;
create trigger trg_apply_manual_points_adjustment
before update of manual_adjustment on public.points
for each row execute function public.apply_manual_points_adjustment();

create or replace function public.claim_holder_join_bonus(p_user_id bigint)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_claimed boolean := false;
begin
    update public.users
    set holder_join_bonus_awarded_at = now(),
        holder_verified_at = coalesce(holder_verified_at, now())
    where telegram_id = p_user_id
      and holder_join_bonus_awarded_at is null
    returning true into v_claimed;

    if not coalesce(v_claimed, false) then
        return false;
    end if;

    -- Add only the missing part. OG users already have holder_bonus = 50,
    -- so they never receive a duplicate 50 RP award.
    insert into public.points (user_id, is_holder, holder_bonus, total_points)
    values (p_user_id, true, 50, 50)
    on conflict (user_id) do update
    set is_holder = true,
        total_points = coalesce(public.points.total_points, 0)
            + greatest(0, 50 - coalesce(public.points.holder_bonus, 0)),
        holder_bonus = greatest(coalesce(public.points.holder_bonus, 0), 50),
        updated_at = now();

    return true;
end;
$$;

revoke all on function public.claim_holder_join_bonus(bigint)
from public, anon, authenticated;
grant execute on function public.claim_holder_join_bonus(bigint) to service_role;

commit;
