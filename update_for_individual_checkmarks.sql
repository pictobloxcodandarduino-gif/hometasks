-- Run this once in Supabase SQL Editor for an existing installation.
-- Adds per-person, per-task completion totals and lets the admin select any person.

alter table public.task_state
add column if not exists completion_counts jsonb not null default '{
  "جارو": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
  "ظرف‌ها": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
  "آشغال": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
  "سفره": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
  "خرید": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
  "لباس‌ها": {"هانی": 0, "احمرضا": 0, "ارمیا": 0}
}'::jsonb;

create or replace function public.complete_task(p_task text, p_person text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_orders jsonb;
    current_counts jsonb;
    people jsonb;
    new_people jsonb;
    next_count integer;
    allowed_tasks text[] := array['جارو','ظرف‌ها','آشغال','سفره','خرید','لباس‌ها'];
    allowed_people text[] := array['هانی','احمرضا','ارمیا'];
begin
    if not (p_task = any(allowed_tasks)) then raise exception 'Invalid task'; end if;
    if not (p_person = any(allowed_people)) then raise exception 'Invalid person'; end if;

    select orders, completion_counts into current_orders, current_counts
    from public.task_state where id = 1 for update;
    if current_orders is null then raise exception 'Task state not found'; end if;

    people := current_orders -> p_task;
    if people is null or not (people @> jsonb_build_array(p_person)) then
        raise exception 'Person is not in task order';
    end if;

    select coalesce(jsonb_agg(value order by ordinality), '[]'::jsonb)
    into new_people
    from jsonb_array_elements(people) with ordinality
    where value #>> '{}' <> p_person;
    new_people := new_people || jsonb_build_array(p_person);
    current_orders := jsonb_set(current_orders, array[p_task], new_people, false);

    next_count := coalesce((current_counts #>> array[p_task, p_person])::integer, 0) + 1;
    current_counts := jsonb_set(current_counts, array[p_task, p_person], to_jsonb(next_count), true);

    update public.task_state
    set orders = current_orders, completion_counts = current_counts, updated_at = now()
    where id = 1;

    return jsonb_build_object('orders', current_orders -> p_task, 'count', next_count);
end;
$$;

create or replace function public.reset_all_tasks()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    default_orders jsonb := '{
      "جارو": ["هانی", "احمرضا", "ارمیا"],
      "ظرف‌ها": ["هانی", "احمرضا", "ارمیا"],
      "آشغال": ["هانی", "احمرضا", "ارمیا"],
      "سفره": ["هانی", "احمرضا", "ارمیا"],
      "خرید": ["هانی", "احمرضا", "ارمیا"],
      "لباس‌ها": ["هانی", "احمرضا", "ارمیا"]
    }'::jsonb;
    default_counts jsonb := '{
      "جارو": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
      "ظرف‌ها": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
      "آشغال": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
      "سفره": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
      "خرید": {"هانی": 0, "احمرضا": 0, "ارمیا": 0},
      "لباس‌ها": {"هانی": 0, "احمرضا": 0, "ارمیا": 0}
    }'::jsonb;
begin
    update public.task_state
    set orders = default_orders, completion_counts = default_counts, updated_at = now()
    where id = 1;
    return jsonb_build_object('orders', default_orders, 'completion_counts', default_counts);
end;
$$;

revoke all on function public.complete_task(text, text) from public, anon, authenticated;
grant execute on function public.complete_task(text, text) to service_role;
revoke all on function public.reset_all_tasks() from public, anon, authenticated;
grant execute on function public.reset_all_tasks() to service_role;
