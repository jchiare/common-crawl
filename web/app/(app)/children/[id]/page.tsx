import Link from "next/link";
import { notFound } from "next/navigation";
import { ConfirmButton, SubmitButton } from "@/components/buttons";
import { requireUser } from "@/lib/supabase/server";
import type { Child, Goal, GoalStatus, Invite } from "@/lib/types";
import { addDays, currentWeek, formatWeek } from "@/lib/week";
import {
  addGoal,
  deleteChild,
  deleteGoal,
  inviteParent,
  revokeInvite,
  setGoalStatus,
  updateChild,
} from "../../actions";

const GOAL_GROUPS: { status: GoalStatus; title: string; empty: string }[] = [
  { status: "active", title: "Working on now", empty: "No active goals yet." },
  { status: "next", title: "Up next", empty: "Nothing queued." },
  { status: "achieved", title: "Achieved", empty: "" },
];

// Where a goal can move from each state: [target status, button label].
const MOVES: Record<GoalStatus, [GoalStatus, string][]> = {
  suggested: [
    ["next", "Accept as next"],
    ["active", "Start now"],
  ],
  next: [["active", "Start now"]],
  active: [
    ["achieved", "Mark achieved"],
    ["next", "Move to next"],
  ],
  achieved: [["active", "Reopen"]],
};

export default async function ChildPage({ params }: PageProps<"/children/[id]">) {
  const { id } = await params;
  const { supabase } = await requireUser();

  const [childResult, goalsResult, invitesResult, plansResult] = await Promise.all([
    supabase.from("children").select("id, first_name, birth_year, notes").eq("id", id).maybeSingle(),
    supabase
      .from("goals")
      .select("id, child_id, title, detail, status, source")
      .eq("child_id", id)
      .order("sort")
      .order("created_at"),
    supabase.from("invites").select("id, email, accepted_at").eq("child_id", id).order("created_at"),
    supabase
      .from("weekly_plans")
      .select("week_start, status")
      .eq("child_id", id)
      .order("week_start", { ascending: false })
      .limit(12),
  ]);
  const child = childResult.data as Child | null;
  if (!child) notFound();
  const goals = (goalsResult.data ?? []) as Goal[];
  const invites = (invitesResult.data ?? []) as Invite[];

  const thisWeek = currentWeek();
  const nextWeek = addDays(thisWeek, 7);
  const planStatus = new Map((plansResult.data ?? []).map((p) => [p.week_start, p.status]));
  const pastWeeks = (plansResult.data ?? []).filter((p) => p.week_start < thisWeek);
  const suggested = goals.filter((g) => g.status === "suggested");

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-muted hover:text-brand">
          ← Children
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">{child.first_name}</h1>
      </div>

      {/* ---------------------------------------------------------- weeks */}
      <section className="space-y-3">
        <h2 className="h2">Weekly plans</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            { week: thisWeek, label: "This week" },
            { week: nextWeek, label: "Next week" },
          ].map(({ week, label }) => (
            <Link
              key={week}
              href={`/children/${child.id}/weeks/${week}`}
              className="card flex items-center hover:border-brand"
            >
              <div>
                <div className="font-medium">{label}</div>
                <div className="text-sm text-muted">{formatWeek(week)}</div>
              </div>
              <span
                className={`chip ml-auto ${planStatus.get(week) === "published" ? "chip-brand" : ""}`}
              >
                {planStatus.get(week) ?? "not started"}
              </span>
            </Link>
          ))}
        </div>
        {pastWeeks.length > 0 && (
          <div className="flex flex-wrap gap-2 text-sm">
            <span className="text-muted">Earlier:</span>
            {pastWeeks.map((p) => (
              <Link
                key={p.week_start}
                href={`/children/${child.id}/weeks/${p.week_start}`}
                className="underline decoration-line underline-offset-4 hover:text-brand"
              >
                {formatWeek(p.week_start)}
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------- goals */}
      <section className="space-y-3">
        <h2 className="h2">Goals</h2>

        {suggested.length > 0 && (
          <div className="card border-brand/40 bg-brand-soft/40">
            <p className="mb-3 text-sm font-medium text-brand-dark">
              ✦ Suggested by AI from recent weeks. Parents don&apos;t see these unless you accept
              them.
            </p>
            <GoalList childId={child.id} goals={suggested} />
          </div>
        )}

        <div className="card space-y-5">
          {GOAL_GROUPS.map((group) => {
            const inGroup = goals.filter((g) => g.status === group.status);
            if (inGroup.length === 0 && !group.empty) return null;
            return (
              <div key={group.status}>
                <h3 className="mb-2 text-sm font-semibold">{group.title}</h3>
                {inGroup.length === 0 ? (
                  <p className="text-sm text-muted">{group.empty}</p>
                ) : (
                  <GoalList childId={child.id} goals={inGroup} />
                )}
              </div>
            );
          })}

          <form
            action={addGoal.bind(null, child.id)}
            className="grid gap-3 border-t border-line pt-4 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end"
          >
            <div>
              <label className="label" htmlFor="goal_title">
                New goal
              </label>
              <input
                id="goal_title"
                name="title"
                required
                placeholder="e.g. /s/ at the start of words"
                className="input"
              />
            </div>
            <div>
              <label className="label" htmlFor="goal_detail">
                Detail (optional)
              </label>
              <input id="goal_detail" name="detail" className="input" />
            </div>
            <div>
              <label className="label" htmlFor="goal_status">
                When
              </label>
              <select id="goal_status" name="status" className="input">
                <option value="active">Now</option>
                <option value="next">Next</option>
              </select>
            </div>
            <SubmitButton pending="Adding…">Add goal</SubmitButton>
          </form>
        </div>
      </section>

      {/* ---------------------------------------------------------- profile */}
      <section className="space-y-3">
        <h2 className="h2">Profile</h2>
        <form action={updateChild.bind(null, child.id)} className="card space-y-3">
          <div className="flex flex-wrap gap-3">
            <div className="min-w-40 flex-1">
              <label className="label" htmlFor="first_name">
                First name
              </label>
              <input
                id="first_name"
                name="first_name"
                required
                defaultValue={child.first_name}
                className="input"
              />
            </div>
            <div className="w-32">
              <label className="label" htmlFor="birth_year">
                Birth year
              </label>
              <input
                id="birth_year"
                name="birth_year"
                type="number"
                min={1990}
                max={2100}
                defaultValue={child.birth_year ?? ""}
                className="input"
              />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="notes">
              Your notes (private; also used to guide AI drafts)
            </label>
            <textarea
              id="notes"
              name="notes"
              rows={4}
              defaultValue={child.notes}
              placeholder="What you're seeing, what motivates this child, what to avoid…"
              className="input"
            />
          </div>
          <SubmitButton pending="Saving…">Save profile</SubmitButton>
        </form>
      </section>

      {/* ---------------------------------------------------------- parents */}
      <section className="space-y-3">
        <h2 className="h2">Parents</h2>
        <div className="card space-y-4">
          {invites.length === 0 ? (
            <p className="text-sm text-muted">
              No parents yet. Invite one by email; they sign in to the iPhone app with that same
              address.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {invites.map((invite) => (
                <li key={invite.id} className="flex items-center gap-3 py-2 text-sm">
                  <span>{invite.email}</span>
                  <span className={`chip ${invite.accepted_at ? "chip-brand" : ""}`}>
                    {invite.accepted_at ? "joined" : "invited"}
                  </span>
                  <form action={revokeInvite.bind(null, child.id, invite.id)} className="ml-auto">
                    <ConfirmButton
                      message={`Remove ${invite.email}? They will lose access to ${child.first_name}'s plan.`}
                    >
                      Remove
                    </ConfirmButton>
                  </form>
                </li>
              ))}
            </ul>
          )}
          <form action={inviteParent.bind(null, child.id)} className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1">
              <label className="label" htmlFor="parent_email">
                Parent&apos;s email
              </label>
              <input id="parent_email" name="email" type="email" required className="input" />
            </div>
            <SubmitButton pending="Inviting…">Invite</SubmitButton>
          </form>
        </div>
      </section>

      <form action={deleteChild.bind(null, child.id)}>
        <ConfirmButton
          className="btn btn-quiet text-hard"
          message={`Delete ${child.first_name} and all of their plans and practice history? This cannot be undone.`}
        >
          Delete {child.first_name}
        </ConfirmButton>
      </form>
    </div>
  );
}

function GoalList({ childId, goals }: { childId: string; goals: Goal[] }) {
  return (
    <ul className="space-y-2">
      {goals.map((goal) => (
        <li key={goal.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <div className="min-w-0 flex-1">
            <span className="text-sm font-medium">{goal.title}</span>
            {goal.detail && <span className="text-sm text-muted"> — {goal.detail}</span>}
          </div>
          <div className="flex items-center gap-1">
            {MOVES[goal.status].map(([status, label]) => (
              <form key={status} action={setGoalStatus.bind(null, childId, goal.id, status)}>
                <button className="btn btn-quiet">{label}</button>
              </form>
            ))}
            <form action={deleteGoal.bind(null, childId, goal.id)}>
              <ConfirmButton message={`Delete the goal "${goal.title}"?`}>
                {goal.status === "suggested" ? "Dismiss" : "Delete"}
              </ConfirmButton>
            </form>
          </div>
        </li>
      ))}
    </ul>
  );
}
