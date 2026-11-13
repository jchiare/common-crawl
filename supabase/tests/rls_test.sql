-- RLS behaviour tests. Run via supabase/tests/run.sh. Any failed assertion aborts.
\set ON_ERROR_STOP on

create function pg_temp.act_as(uid uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', uid::text, false);
end $$;

create function pg_temp.check_eq(label text, got bigint, want bigint) returns void language plpgsql as $$
begin
  if got is distinct from want then
    raise exception 'FAIL %: got %, want %', label, got, want;
  end if;
  raise notice 'ok   %', label;
end $$;

-- Runs a statement that must be rejected (error) or affect zero rows.
create function pg_temp.check_denied(label text, stmt text) returns void language plpgsql as $$
declare n bigint;
begin
  begin
    execute stmt;
    get diagnostics n = row_count;
  exception when others then
    raise notice 'ok   % (rejected: %)', label, sqlerrm;
    return;
  end;
  if n > 0 then
    raise exception 'FAIL %: statement affected % rows', label, n;
  end if;
  raise notice 'ok   % (0 rows)', label;
end $$;

-- ---- fixtures (as superuser)
insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000a1', 'therapist1@example.com'),
  ('00000000-0000-0000-0000-0000000000a2', 'therapist2@example.com'),
  ('00000000-0000-0000-0000-0000000000b1', 'Parent1@Example.com'),
  ('00000000-0000-0000-0000-0000000000b2', 'parent2@example.com');

select pg_temp.check_eq('profiles created by trigger', (select count(*) from public.profiles), 4);

set role authenticated;

-- ---- therapist 1 sets up a child, goals, a draft plan
select pg_temp.act_as('00000000-0000-0000-0000-0000000000a1');

insert into public.children (id, first_name) values ('00000000-0000-0000-0000-00000000c001', 'Sam');
insert into public.invites (id, child_id, email) values
  ('00000000-0000-0000-0000-00000000f001', '00000000-0000-0000-0000-00000000c001', 'parent1@example.com');
insert into public.goals (child_id, title, status) values
  ('00000000-0000-0000-0000-00000000c001', 'Initial /s/ in words', 'active'),
  ('00000000-0000-0000-0000-00000000c001', '/s/ blends', 'next'),
  ('00000000-0000-0000-0000-00000000c001', 'AI idea', 'suggested');
insert into public.weekly_plans (id, child_id, week_start) values
  ('00000000-0000-0000-0000-00000000d001', '00000000-0000-0000-0000-00000000c001', '2026-11-09');
insert into public.tasks (id, plan_id, child_id, title) values
  ('00000000-0000-0000-0000-00000000e001', '00000000-0000-0000-0000-00000000d001',
   '00000000-0000-0000-0000-00000000c001', 'Say sun, sock, soap');
insert into public.plan_insights (plan_id, child_id, summary) values
  ('00000000-0000-0000-0000-00000000d001', '00000000-0000-0000-0000-00000000c001', 'private');

select pg_temp.check_eq('therapist sees own child', (select count(*) from public.children), 1);
select pg_temp.check_denied('weekly plan must start on a Monday',
  $$insert into public.weekly_plans (child_id, week_start) values ('00000000-0000-0000-0000-00000000c001', '2026-11-10')$$);

-- ---- therapist 2 sees nothing of therapist 1's
select pg_temp.act_as('00000000-0000-0000-0000-0000000000a2');
select pg_temp.check_eq('other therapist: children', (select count(*) from public.children), 0);
select pg_temp.check_eq('other therapist: goals', (select count(*) from public.goals), 0);
select pg_temp.check_eq('other therapist: tasks', (select count(*) from public.tasks), 0);
select pg_temp.check_eq('other therapist: invites', (select count(*) from public.invites), 0);
select pg_temp.check_denied('other therapist cannot add a goal',
  $$insert into public.goals (child_id, title) values ('00000000-0000-0000-0000-00000000c001', 'x')$$);
select pg_temp.check_denied('other therapist cannot add a task to the plan',
  $$insert into public.tasks (plan_id, child_id, title) values ('00000000-0000-0000-0000-00000000d001', '00000000-0000-0000-0000-00000000c001', 'x')$$);
select pg_temp.check_denied('cannot create a child owned by someone else',
  $$insert into public.children (therapist_id, first_name) values ('00000000-0000-0000-0000-0000000000a1', 'x')$$);

-- ---- parent 1 before claiming: nothing
select pg_temp.act_as('00000000-0000-0000-0000-0000000000b1');
select pg_temp.check_eq('unlinked parent: children', (select count(*) from public.children), 0);
select pg_temp.check_denied('parent cannot link themselves directly',
  $$insert into public.child_guardians (child_id, parent_id) values ('00000000-0000-0000-0000-00000000c001', '00000000-0000-0000-0000-0000000000b1')$$);

-- ---- claim (email match is case-insensitive)
select pg_temp.check_eq('claim_invites links one invite', public.claim_invites(), 1);
select pg_temp.check_eq('claim_invites is idempotent', public.claim_invites(), 0);
select pg_temp.check_eq('parent sees child', (select count(*) from public.children), 1);
select pg_temp.check_eq('parent sees active+next goals only', (select count(*) from public.goals), 2);
select pg_temp.check_eq('parent cannot see draft plan', (select count(*) from public.weekly_plans), 0);
select pg_temp.check_eq('parent cannot see draft tasks', (select count(*) from public.tasks), 0);
select pg_temp.check_eq('parent cannot see therapist insights', (select count(*) from public.plan_insights), 0);
select pg_temp.check_eq('parent cannot see invites', (select count(*) from public.invites), 0);
select pg_temp.check_denied('parent cannot log against a draft plan',
  $$insert into public.practice_logs (task_id, child_id, practiced_on, rating) values ('00000000-0000-0000-0000-00000000e001', '00000000-0000-0000-0000-00000000c001', '2026-11-10', 'ok')$$);

-- ---- parent 2 (not invited) claims nothing
select pg_temp.act_as('00000000-0000-0000-0000-0000000000b2');
select pg_temp.check_eq('uninvited parent claims nothing', public.claim_invites(), 0);
select pg_temp.check_eq('uninvited parent: children', (select count(*) from public.children), 0);

-- ---- therapist publishes
select pg_temp.act_as('00000000-0000-0000-0000-0000000000a1');
update public.weekly_plans set status = 'published' where id = '00000000-0000-0000-0000-00000000d001';
select pg_temp.check_eq('therapist sees accepted invite',
  (select count(*) from public.invites where accepted_at is not null), 1);
select pg_temp.check_eq('therapist sees guardian link', (select count(*) from public.child_guardians), 1);

-- ---- parent 1 can now see and log
select pg_temp.act_as('00000000-0000-0000-0000-0000000000b1');
select pg_temp.check_eq('parent sees published plan', (select count(*) from public.weekly_plans), 1);
select pg_temp.check_eq('parent sees tasks', (select count(*) from public.tasks), 1);
insert into public.practice_logs (task_id, child_id, practiced_on, rating, note) values
  ('00000000-0000-0000-0000-00000000e001', '00000000-0000-0000-0000-00000000c001', '2026-11-10', 'hard', 'tired today');
select pg_temp.check_eq('log owner stamped from session',
  (select count(*) from public.practice_logs where parent_id = '00000000-0000-0000-0000-0000000000b1'), 1);
select pg_temp.check_denied('one log per task per day',
  $$insert into public.practice_logs (task_id, child_id, practiced_on, rating) values ('00000000-0000-0000-0000-00000000e001', '00000000-0000-0000-0000-00000000c001', '2026-11-10', 'ok')$$);
update public.practice_logs set rating = 'ok' where task_id = '00000000-0000-0000-0000-00000000e001';
select pg_temp.check_denied('parent cannot edit tasks',
  $$update public.tasks set title = 'hacked'$$);
select pg_temp.check_denied('parent cannot edit goals',
  $$update public.goals set status = 'achieved'$$);
select pg_temp.check_denied('parent cannot edit the plan',
  $$update public.weekly_plans set note = 'hacked'$$);

-- ---- parent 2 still locked out, and cannot log for a child that is not theirs
select pg_temp.act_as('00000000-0000-0000-0000-0000000000b2');
select pg_temp.check_eq('uninvited parent: tasks', (select count(*) from public.tasks), 0);
select pg_temp.check_eq('uninvited parent: logs', (select count(*) from public.practice_logs), 0);
select pg_temp.check_denied('uninvited parent cannot log',
  $$insert into public.practice_logs (task_id, child_id, practiced_on, rating) values ('00000000-0000-0000-0000-00000000e001', '00000000-0000-0000-0000-00000000c001', '2026-11-11', 'ok')$$);

-- ---- therapist reads logs but cannot write them; achieved goals get stamped
select pg_temp.act_as('00000000-0000-0000-0000-0000000000a1');
select pg_temp.check_eq('therapist reads logs', (select count(*) from public.practice_logs where rating = 'ok'), 1);
select pg_temp.check_denied('therapist cannot forge a log',
  $$insert into public.practice_logs (task_id, child_id, practiced_on, rating) values ('00000000-0000-0000-0000-00000000e001', '00000000-0000-0000-0000-00000000c001', '2026-11-12', 'easy')$$);
update public.goals set status = 'achieved' where title = 'Initial /s/ in words';
select pg_temp.check_eq('achieved_at stamped',
  (select count(*) from public.goals where status = 'achieved' and achieved_at is not null), 1);

-- ---- revoking an invite removes the parent's access
select pg_temp.act_as('00000000-0000-0000-0000-0000000000a2');
select pg_temp.check_denied('other therapist cannot revoke the invite',
  $$select public.revoke_invite('00000000-0000-0000-0000-00000000f001')$$);
select pg_temp.act_as('00000000-0000-0000-0000-0000000000a1');
select public.revoke_invite('00000000-0000-0000-0000-00000000f001');
select pg_temp.check_eq('invite gone', (select count(*) from public.invites), 0);
select pg_temp.check_eq('guardian link gone', (select count(*) from public.child_guardians), 0);
select pg_temp.act_as('00000000-0000-0000-0000-0000000000b1');
select pg_temp.check_eq('revoked parent: children', (select count(*) from public.children), 0);
select pg_temp.check_eq('revoked parent: tasks', (select count(*) from public.tasks), 0);

-- ---- signed-out callers get nothing
reset role;
set role anon;
select pg_temp.check_denied('anon cannot read children', $$select * from public.children$$);
select pg_temp.check_denied('anon cannot claim invites', $$select public.claim_invites()$$);
reset role;

\echo ALL RLS TESTS PASSED
