-- Speech-therapy home practice: core schema.
-- Access is relationship-based: a therapist owns children; parents are linked
-- to children as guardians. There is no global "role" column.

-- ---------------------------------------------------------------- tables

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null default '',
  full_name text not null default '',
  created_at timestamptz not null default now()
);

create table public.children (
  id uuid primary key default gen_random_uuid(),
  therapist_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  first_name text not null check (length(trim(first_name)) > 0),
  birth_year int check (birth_year between 1990 and 2100),
  -- Therapist's working notes: diagnosis, what motivates the child, etc.
  notes text not null default '',
  created_at timestamptz not null default now()
);
create index children_therapist_idx on public.children (therapist_id);

create table public.child_guardians (
  child_id uuid not null references public.children (id) on delete cascade,
  parent_id uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (child_id, parent_id)
);
create index child_guardians_parent_idx on public.child_guardians (parent_id);

-- A therapist invites a parent by email; the parent claims it on first sign-in.
create table public.invites (
  id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children (id) on delete cascade,
  email text not null check (email = lower(trim(email)) and position('@' in email) > 1),
  created_at timestamptz not null default now(),
  accepted_at timestamptz,
  unique (child_id, email)
);
create index invites_email_idx on public.invites (email);

-- suggested: proposed by AI, therapist has not accepted it yet (hidden from parents)
-- next:      agreed upcoming goal
-- active:    being worked on now
-- achieved:  done
create table public.goals (
  id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children (id) on delete cascade,
  title text not null check (length(trim(title)) > 0),
  detail text not null default '',
  status text not null default 'active' check (status in ('suggested', 'next', 'active', 'achieved')),
  source text not null default 'therapist' check (source in ('therapist', 'ai')),
  sort int not null default 0,
  created_at timestamptz not null default now(),
  achieved_at timestamptz
);
create index goals_child_idx on public.goals (child_id);

-- Therapist's reusable exercise library.
create table public.exercises (
  id uuid primary key default gen_random_uuid(),
  therapist_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  title text not null check (length(trim(title)) > 0),
  instructions text not null default '',
  words text[] not null default '{}',
  minutes_per_day int not null default 5 check (minutes_per_day between 1 and 120),
  days_per_week int not null default 5 check (days_per_week between 1 and 7),
  media_url text,
  created_at timestamptz not null default now()
);
create index exercises_therapist_idx on public.exercises (therapist_id);

create table public.weekly_plans (
  id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children (id) on delete cascade,
  -- Always a Monday.
  week_start date not null check (extract(isodow from week_start) = 1),
  status text not null default 'draft' check (status in ('draft', 'published')),
  -- Shown to parents once published.
  note text not null default '',
  parent_summary text not null default '',
  created_at timestamptz not null default now(),
  unique (child_id, week_start)
);

-- Therapist-only review of a week (kept out of weekly_plans so parents can't read it).
create table public.plan_insights (
  plan_id uuid primary key references public.weekly_plans (id) on delete cascade,
  child_id uuid not null references public.children (id) on delete cascade,
  summary text not null default '',
  -- AI-written draft of the parent-facing summary; the therapist reviews it
  -- and copies it to weekly_plans.parent_summary to share it.
  parent_summary_draft text not null default '',
  generated_at timestamptz not null default now()
);

create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.weekly_plans (id) on delete cascade,
  child_id uuid not null references public.children (id) on delete cascade,
  goal_id uuid references public.goals (id) on delete set null,
  title text not null check (length(trim(title)) > 0),
  instructions text not null default '',
  words text[] not null default '{}',
  minutes_per_day int not null default 5 check (minutes_per_day between 1 and 120),
  days_per_week int not null default 5 check (days_per_week between 1 and 7),
  media_url text,
  source text not null default 'therapist' check (source in ('therapist', 'ai')),
  sort int not null default 0,
  created_at timestamptz not null default now()
);
create index tasks_plan_idx on public.tasks (plan_id);
create index tasks_child_idx on public.tasks (child_id);

-- One row per task per day the parent practised.
create table public.practice_logs (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks (id) on delete cascade,
  child_id uuid not null references public.children (id) on delete cascade,
  parent_id uuid references public.profiles (id) on delete set null,
  practiced_on date not null,
  rating text not null check (rating in ('easy', 'ok', 'hard')),
  note text not null default '',
  created_at timestamptz not null default now(),
  unique (task_id, practiced_on)
);
create index practice_logs_child_idx on public.practice_logs (child_id, practiced_on);

-- ---------------------------------------------------------------- triggers

-- Create a profile row for every new auth user.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email)
  values (new.id, lower(coalesce(new.email, '')))
  on conflict (id) do nothing;
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- child_id on tasks / insights / logs is derived, never trusted from the client.
create function public.set_child_from_plan() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  select p.child_id into strict new.child_id from public.weekly_plans p where p.id = new.plan_id;
  return new;
end $$;

create trigger tasks_set_child before insert or update of plan_id, child_id on public.tasks
  for each row execute function public.set_child_from_plan();
create trigger plan_insights_set_child before insert or update of plan_id, child_id on public.plan_insights
  for each row execute function public.set_child_from_plan();

create function public.set_log_owner() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  select t.child_id into strict new.child_id from public.tasks t where t.id = new.task_id;
  if tg_op = 'INSERT' then
    new.parent_id := auth.uid();
  else
    new.parent_id := old.parent_id;
  end if;
  return new;
end $$;

create trigger practice_logs_set_owner before insert or update on public.practice_logs
  for each row execute function public.set_log_owner();

create function public.stamp_goal_achieved() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.status = 'achieved' and new.achieved_at is null then
    new.achieved_at := now();
  elsif new.status <> 'achieved' then
    new.achieved_at := null;
  end if;
  return new;
end $$;

create trigger goals_stamp_achieved before insert or update of status on public.goals
  for each row execute function public.stamp_goal_achieved();

-- ---------------------------------------------------------------- access helpers
-- SECURITY DEFINER so policies can look across tables without recursing into RLS.

create function public.is_therapist_of(child uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.children c where c.id = child and c.therapist_id = auth.uid()
  );
$$;

create function public.is_guardian_of(child uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.child_guardians g where g.child_id = child and g.parent_id = auth.uid()
  );
$$;

create function public.is_plan_published(plan uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.weekly_plans p where p.id = plan and p.status = 'published'
  );
$$;

-- Called by the parent app after sign-in: links the signed-in user to every
-- child they were invited to (matched on their verified email).
create function public.claim_invites() returns int
language plpgsql security definer set search_path = '' as $$
declare
  me uuid := auth.uid();
  my_email text;
  claimed int;
begin
  if me is null then
    return 0;
  end if;
  select lower(u.email) into my_email from auth.users u where u.id = me;
  if my_email is null then
    return 0;
  end if;

  insert into public.child_guardians (child_id, parent_id)
  select i.child_id, me from public.invites i where i.email = my_email
  on conflict do nothing;

  update public.invites set accepted_at = now()
  where email = my_email and accepted_at is null;
  get diagnostics claimed = row_count;
  return claimed;
end $$;

revoke execute on function public.claim_invites() from public, anon;
grant execute on function public.claim_invites() to authenticated;

-- Therapist removes an invite and, if it was already accepted, the parent's access.
create function public.revoke_invite(invite uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare
  inv public.invites;
begin
  select * into inv from public.invites i where i.id = invite;
  if inv.id is null or not public.is_therapist_of(inv.child_id) then
    raise exception 'invite not found' using errcode = '42501';
  end if;
  delete from public.child_guardians g
  using public.profiles p
  where g.child_id = inv.child_id and g.parent_id = p.id and p.email = inv.email;
  delete from public.invites i where i.id = inv.id;
end $$;

revoke execute on function public.revoke_invite(uuid) from public, anon;
grant execute on function public.revoke_invite(uuid) to authenticated;

-- ---------------------------------------------------------------- row level security

alter table public.profiles enable row level security;
alter table public.children enable row level security;
alter table public.child_guardians enable row level security;
alter table public.invites enable row level security;
alter table public.goals enable row level security;
alter table public.exercises enable row level security;
alter table public.weekly_plans enable row level security;
alter table public.plan_insights enable row level security;
alter table public.tasks enable row level security;
alter table public.practice_logs enable row level security;

grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;

-- profiles: own row only
create policy profiles_select_own on public.profiles for select to authenticated
  using (id = auth.uid());
create policy profiles_update_own on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- children
create policy children_therapist_all on public.children for all to authenticated
  using (therapist_id = auth.uid()) with check (therapist_id = auth.uid());
create policy children_guardian_select on public.children for select to authenticated
  using (public.is_guardian_of(id));

-- guardians: rows are only created through claim_invites()
create policy guardians_select on public.child_guardians for select to authenticated
  using (parent_id = auth.uid() or public.is_therapist_of(child_id));
create policy guardians_therapist_delete on public.child_guardians for delete to authenticated
  using (public.is_therapist_of(child_id));

-- invites: therapist only
create policy invites_therapist_all on public.invites for all to authenticated
  using (public.is_therapist_of(child_id)) with check (public.is_therapist_of(child_id));

-- goals
create policy goals_therapist_all on public.goals for all to authenticated
  using (public.is_therapist_of(child_id)) with check (public.is_therapist_of(child_id));
create policy goals_guardian_select on public.goals for select to authenticated
  using (status <> 'suggested' and public.is_guardian_of(child_id));

-- exercise library
create policy exercises_owner_all on public.exercises for all to authenticated
  using (therapist_id = auth.uid()) with check (therapist_id = auth.uid());

-- weekly plans
create policy plans_therapist_all on public.weekly_plans for all to authenticated
  using (public.is_therapist_of(child_id)) with check (public.is_therapist_of(child_id));
create policy plans_guardian_select on public.weekly_plans for select to authenticated
  using (status = 'published' and public.is_guardian_of(child_id));

-- therapist-only insights
create policy insights_therapist_all on public.plan_insights for all to authenticated
  using (public.is_therapist_of(child_id)) with check (public.is_therapist_of(child_id));

-- tasks
create policy tasks_therapist_all on public.tasks for all to authenticated
  using (public.is_therapist_of(child_id)) with check (public.is_therapist_of(child_id));
create policy tasks_guardian_select on public.tasks for select to authenticated
  using (public.is_guardian_of(child_id) and public.is_plan_published(plan_id));

-- practice logs: parents write, therapist reads
create policy logs_therapist_select on public.practice_logs for select to authenticated
  using (public.is_therapist_of(child_id));
create policy logs_guardian_select on public.practice_logs for select to authenticated
  using (public.is_guardian_of(child_id));
create policy logs_guardian_insert on public.practice_logs for insert to authenticated
  with check (
    public.is_guardian_of(child_id)
    and exists (
      select 1 from public.tasks t
      where t.id = task_id and public.is_plan_published(t.plan_id)
    )
  );
create policy logs_guardian_update on public.practice_logs for update to authenticated
  using (public.is_guardian_of(child_id)) with check (public.is_guardian_of(child_id));
create policy logs_guardian_delete on public.practice_logs for delete to authenticated
  using (public.is_guardian_of(child_id));
