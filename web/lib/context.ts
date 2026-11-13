import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { AiContext } from "./ai";
import { today } from "./week";

const WEEKS_OF_HISTORY = 4;

/**
 * Gathers what the AI needs about one child: goals, therapist notes and the
 * last few weeks of tasks with how practice went. `throughWeek` is the latest
 * week to include. Runs as the signed-in therapist, so RLS scopes it.
 */
export async function buildAiContext(
  supabase: SupabaseClient,
  childId: string,
  throughWeek: string,
): Promise<AiContext | null> {
  const { data: child } = await supabase
    .from("children")
    .select("birth_year, notes")
    .eq("id", childId)
    .maybeSingle();
  if (!child) return null;

  const [goals, plans, library] = await Promise.all([
    supabase
      .from("goals")
      .select("id, title, detail, status")
      .eq("child_id", childId)
      .neq("status", "suggested")
      .order("sort"),
    supabase
      .from("weekly_plans")
      .select("id, week_start, note")
      .eq("child_id", childId)
      .lte("week_start", throughWeek)
      .order("week_start", { ascending: false })
      .limit(WEEKS_OF_HISTORY),
    supabase.from("exercises").select("title, instructions, words").limit(30),
  ]);

  const planIds = (plans.data ?? []).map((p) => p.id);
  const { data: tasks } = planIds.length
    ? await supabase
        .from("tasks")
        .select("id, plan_id, goal_id, title, instructions, words, minutes_per_day, days_per_week")
        .in("plan_id", planIds)
        .order("sort")
    : { data: [] };
  const taskIds = (tasks ?? []).map((t) => t.id);
  const { data: logs } = taskIds.length
    ? await supabase
        .from("practice_logs")
        .select("task_id, practiced_on, rating, note")
        .in("task_id", taskIds)
        .order("practiced_on")
    : { data: [] };

  const goalTitle = new Map((goals.data ?? []).map((g) => [g.id, g.title]));
  const thisYear = Number(today().slice(0, 4));

  return {
    age: child.birth_year ? thisYear - child.birth_year : null,
    therapistNotes: child.notes,
    goals: goals.data ?? [],
    weeks: (plans.data ?? []).map((plan) => ({
      weekStart: plan.week_start,
      noteToParents: plan.note,
      tasks: (tasks ?? [])
        .filter((t) => t.plan_id === plan.id)
        .map((t) => ({
          title: t.title,
          instructions: t.instructions,
          words: t.words,
          minutesPerDay: t.minutes_per_day,
          daysPerWeek: t.days_per_week,
          goal: t.goal_id ? (goalTitle.get(t.goal_id) ?? null) : null,
          logs: (logs ?? [])
            .filter((l) => l.task_id === t.id)
            .map((l) => ({ date: l.practiced_on, rating: l.rating, note: l.note })),
        })),
    })),
    library: library.data ?? [],
  };
}
