import Link from "next/link";
import { SubmitButton } from "@/components/buttons";
import { requireUser } from "@/lib/supabase/server";
import { currentWeek, weekDays } from "@/lib/week";
import { addChild } from "./actions";

export default async function ChildrenPage() {
  const { supabase } = await requireUser();
  const week = currentWeek();
  const days = weekDays(week);

  const [children, plans, logs] = await Promise.all([
    supabase.from("children").select("id, first_name").order("first_name"),
    supabase.from("weekly_plans").select("child_id, status").eq("week_start", week),
    supabase
      .from("practice_logs")
      .select("child_id, practiced_on")
      .gte("practiced_on", days[0])
      .lte("practiced_on", days[6]),
  ]);
  if (children.error) throw new Error(children.error.message);

  const planStatus = new Map((plans.data ?? []).map((p) => [p.child_id, p.status]));
  const daysPractised = new Map<string, Set<string>>();
  for (const log of logs.data ?? []) {
    if (!daysPractised.has(log.child_id)) daysPractised.set(log.child_id, new Set());
    daysPractised.get(log.child_id)!.add(log.practiced_on);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Children</h1>

      {children.data.length === 0 ? (
        <p className="card text-sm text-muted">
          No children yet. Add the first one below, then set goals and build this week&apos;s plan.
        </p>
      ) : (
        <ul className="card divide-y divide-line p-0">
          {children.data.map((child) => {
            const status = planStatus.get(child.id);
            const practised = daysPractised.get(child.id)?.size ?? 0;
            return (
              <li key={child.id}>
                <Link
                  href={`/children/${child.id}`}
                  className="flex items-center gap-3 px-5 py-4 hover:bg-paper"
                >
                  <span className="font-medium">{child.first_name}</span>
                  <span className="ml-auto text-sm text-muted">
                    {status === "published"
                      ? `Practised ${practised} of 7 days this week`
                      : status === "draft"
                        ? "This week's plan is a draft"
                        : "No plan this week"}
                  </span>
                  <span
                    className={`chip ${status === "published" ? "chip-brand" : ""}`}
                    aria-hidden
                  >
                    {status ?? "none"}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      <form action={addChild} className="card flex flex-wrap items-end gap-3">
        <div className="min-w-40 flex-1">
          <label className="label" htmlFor="first_name">
            First name
          </label>
          <input id="first_name" name="first_name" required className="input" />
        </div>
        <div className="w-32">
          <label className="label" htmlFor="birth_year">
            Birth year (optional)
          </label>
          <input id="birth_year" name="birth_year" type="number" min={1990} max={2100} className="input" />
        </div>
        <SubmitButton className="btn btn-primary" pending="Adding…">
          Add child
        </SubmitButton>
      </form>
    </div>
  );
}
