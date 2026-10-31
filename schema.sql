-- Home Tasks: run the entire script in Supabase SQL Editor.
-- Private tables: no direct access for anon/authenticated clients.
create table if not exists public.task_state (
    id integer primary key check (id = 1),
    orders jsonb not null,
    updated_at timestamptz not null default now()
);

insert into public.task_state (id, orders)
values (
    1,
    '{
      "جارو": ["هانی", "احمرضا", "ارمیا"],
      "ظرف‌ها": ["هانی", "احمرضا", "ارمیا"],
      "آشغال": ["هانی", "احمرضا", "ارمیا"],
      "سفره": ["هانی", "احمرضا", "ارمیا"],
      "خرید": ["هانی", "احمرضا", "ارمیا"],
      "لباس‌ها": ["هانی", "احمرضا", "ارمیا"]
    }'::jsonb
)
on conflict (id) do nothing;

create table if not exists public.admin_credentials (
    id integer primary key check (id = 1),
    username text not null unique,
    password_salt text not null,
    password_hash text not null,
    created_at timestamptz not null default now()
);

alter table public.task_state enable row level security;
alter table public.admin_credentials enable row level security;

-- No policies are created. The app accesses these tables only with the
-- Supabase service-role key, which must remain in server-side secrets.

create or replace function public.complete_task(p_task text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_orders jsonb;
    people jsonb;
    first_person jsonb;
    new_people jsonb;
    allowed_tasks text[] := array['جارو','ظرف‌ها','آشغال','سفره','خرید','لباس‌ها'];
begin
    if not (p_task = any(allowed_tasks)) then
        raise exception 'Invalid task';
    end if;

    select orders into current_orders
    from public.task_state
    where id = 1
    for update;

    people := current_orders -> p_task;
    if people is null or jsonb_array_length(people) <> 3 then
        raise exception 'Invalid task order';
    end if;

    first_person := people -> 0;
    new_people := (people - 0) || jsonb_build_array(first_person);
    current_orders := jsonb_set(current_orders, array[p_task], new_people, false);

    update public.task_state
    set orders = current_orders, updated_at = now()
    where id = 1;

    return current_orders -> p_task;
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
begin
    update public.task_state
    set orders = default_orders, updated_at = now()
    where id = 1;
    return default_orders;
end;
$$;

-- Only the server-side service_role can execute these mutation functions.
revoke all on function public.complete_task(text) from public, anon, authenticated;
revoke all on function public.reset_all_tasks() from public, anon, authenticated;
grant execute on function public.complete_task(text) to service_role;
grant execute on function public.reset_all_tasks() to service_role;

revoke all on table public.task_state from anon, authenticated;
revoke all on table public.admin_credentials from anon, authenticated;
