-- Run once in Supabase SQL Editor after the existing individual-checkmark migration.
-- Adds a safe RPC for accumulating elapsed seconds while a checkbox is active.
create or replace function public.increment_task_seconds(
    p_task text,
    p_person text,
    p_seconds integer
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_counts jsonb;
    next_count integer;
    allowed_tasks text[] := array['جارو','ظرف‌ها','آشغال','سفره','خرید','لباس‌ها'];
    allowed_people text[] := array['هانی','احمرضا','ارمیا'];
begin
    if not (p_task = any(allowed_tasks)) then raise exception 'Invalid task'; end if;
    if not (p_person = any(allowed_people)) then raise exception 'Invalid person'; end if;
    if p_seconds is null or p_seconds < 1 or p_seconds > 3600 then
        raise exception 'Invalid seconds';
    end if;

    select completion_counts into current_counts
    from public.task_state where id = 1 for update;

    if current_counts is null then raise exception 'Completion counts not initialized'; end if;

    next_count := coalesce(
        (current_counts #>> array[p_task, p_person])::integer, 0
    ) + p_seconds;

    current_counts := jsonb_set(
        current_counts, array[p_task, p_person], to_jsonb(next_count), true
    );

    update public.task_state
    set completion_counts = current_counts, updated_at = now()
    where id = 1;

    return next_count;
end;
$$;

revoke all on function public.increment_task_seconds(text, text, integer)
from public, anon, authenticated;
grant execute on function public.increment_task_seconds(text, text, integer)
to service_role;
