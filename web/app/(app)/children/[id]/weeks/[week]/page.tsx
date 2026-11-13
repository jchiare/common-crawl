import Link from "next/link";
import { notFound } from "next/navigation";
import { AiAction, ConfirmButton, SubmitButton } from "@/components/buttons";
import { TaskFields } from "@/components/task-fields";
import { requireUser } from "@/lib/supabase/server";
import type { Exercise, Goal, Insight, Plan, PracticeLog, Task } from "@/lib/types";
import {
  addDays,
  currentWeek,
  formatDay,
  formatWeek,
  isMonday,
  weekDays,
  weekdayLetter,
} from "@/lib/week";
import {
  addTask,
  addTaskFromExercise,
  deleteTask,
  draftWeekWithAi,
  reviewWeekWithAi,
  savePlanNote,
  setPlanPublished,
  shareParentSummary,
  updateTask,
} from "../../../../actions";

// AI drafting can take a while; allow the server action time to finish.
export const maxDuration = 120;

const RATING_COLOR = { easy: "bg-easy", ok: "bg-ok", hard: "bg-hard" } as const;

export default async function WeekPage({ params }: PageProps<"/children/[id]/weeks/[week]">) {
  const { id: childId, week } = await params;
  if (!isMonday(week)) notFound();
  const { supabase } = await requireUser();

  const [childResult, planResult, goalsResult, libraryResult] = await Promise.all([
    supabase.from("children").select("id, first_name").eq("id", childId).maybeSingle(),
    supabase
      .from("weekly_plans")
      .select("id, child_id, week_start, status, note, parent_summary")
      .eq("child_id", childId)
      .eq("week_start", week)
      .maybeSingle(),
    supabase
      .from("goals")
      .select("id, child_id, title, detail, status, source")
      .eq("child_id", childId)
      .in("status", ["active", "next"])
      .order("sort"),
    supabase
      .from("exercises")
      .select("id, title, instructions, words, minutes_per_day, days_per_week, media_url")
      .order("title"),
  ]);
  const child = childResult.data;
  if (!child) notFound();
  const plan = planResult.data as Plan | null;
  const goals = (goalsResult.data ?? []) as Goal[];
  const library = (libraryResult.data ?? []) as Exercise[];

  let tasks: Task[] = [];
  let logs: PracticeLog[] = [];
  let insight: Insight | null = null;
  if (plan) {
    const [taskResult, logResult, insightResult] = await Promise.all([
      supabase
        .from("tasks")
        .select(
          "id, plan_id, goal_id, title, instructions, words, minutes_per_day, days_per_week, media_url, source, sort",
        )
        .eq("plan_id", plan.id)
        .order("sort"),
      supabase
        .from("practice_logs")
        .select("id, task_id, practiced_on, rating, note, tasks!inner(plan_id)")
        .eq("tasks.plan_id", plan.id)
        .order("practiced_on"),
      supabase
        .from("plan_insights")
        .select("plan_id, summary, parent_summary_draft, generated_at")
        .eq("plan_id", plan.id)
        .maybeSingle(),
    ]);
    tasks = (taskResult.data ?? []) as Task[];
    logs = (logResult.data ?? []) as PracticeLog[];
    insight = insightResult.data as Insight | null;
  }

  const published = plan?.status === "published";
  const days = weekDays(week);
  const goalTitle = new Map(goals.map((g) => [g.id, g.title]));
  const notes = logs.filter((l) => l.note);
  const taskTitle = new Map(tasks.map((t) => [t.id, t.title]));
  const thisWeek = currentWeek();
  const weekLabel =
    week === thisWeek ? "This week" : week === addDays(thisWeek, 7) ? "Next week" : "Week";

  return (
    <div className="space-y-8">
      <div>
        <Link href={`/children/${childId}`} className="text-sm text-muted hover:text-brand">
          ← {child.first_name}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">
            {weekLabel}: {formatWeek(week)}
          </h1>
          <span className={`chip ${published ? "chip-brand" : ""}`}>
            {published ? "published" : plan ? "draft" : "not started"}
          </span>
          <div className="ml-auto flex gap-2 text-sm">
            <Link href={`/children/${childId}/weeks/${addDays(week, -7)}`} className="btn btn-quiet">
              ← Previous
            </Link>
            <Link href={`/children/${childId}/weeks/${addDays(week, 7)}`} className="btn btn-quiet">
              Next →
            </Link>
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------- tasks */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="h2">Tasks</h2>
          <div className="ml-auto">
            {published ? (
              <form action={setPlanPublished.bind(null, childId, week, false)}>
                <SubmitButton pending="Unpublishing…">Unpublish</SubmitButton>
              </form>
            ) : (
              tasks.length > 0 && (
                <form action={setPlanPublished.bind(null, childId, week, true)}>
                  <SubmitButton className="btn btn-primary" pending="Publishing…">
                    Publish to parents
                  </SubmitButton>
                </form>
              )
            )}
          </div>
        </div>

        {tasks.length === 0 && (
          <p className="card text-sm text-muted">
            No tasks yet. Write one, pull one from your library, or let AI draft the week from{" "}
            {child.first_name}&apos;s goals and recent practice.
          </p>
        )}

        {tasks.map((task) => {
          const taskLogs = new Map(
            logs.filter((l) => l.task_id === task.id).map((l) => [l.practiced_on, l]),
          );
          return (
            <article key={task.id} className="card">
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium">
                    {task.title}{" "}
                    {task.source === "ai" && <span className="chip chip-brand">✦ AI draft</span>}
                  </h3>
                  <div className="text-xs text-muted">
                    {task.minutes_per_day} min a day · {task.days_per_week} days a week
                    {task.goal_id && goalTitle.has(task.goal_id) && (
                      <> · Goal: {goalTitle.get(task.goal_id)}</>
                    )}
                  </div>
                </div>
                {/* Practice grid: one dot per day of the week. */}
                <div
                  className="flex gap-1"
                  role="img"
                  aria-label={`Practised ${taskLogs.size} of ${task.days_per_week} planned days`}
                >
                  {days.map((day) => {
                    const log = taskLogs.get(day);
                    return (
                      <div key={day} className="flex flex-col items-center gap-0.5">
                        <span className="text-[10px] text-muted">{weekdayLetter(day)}</span>
                        <span
                          title={log ? `${formatDay(day)}: ${log.rating}` : formatDay(day)}
                          className={`h-4 w-4 rounded-full ${log ? RATING_COLOR[log.rating] : "border border-line bg-paper"}`}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>

              {task.instructions && (
                <p className="mt-3 text-sm whitespace-pre-line">{task.instructions}</p>
              )}
              {task.words.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {task.words.map((word) => (
                    <span key={word} className="chip">
                      {word}
                    </span>
                  ))}
                </div>
              )}
              {task.media_url && (
                <a
                  href={task.media_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-sm text-brand underline"
                >
                  Demo link
                </a>
              )}

              <details className="mt-3 border-t border-line pt-3">
                <summary className="cursor-pointer text-xs text-muted hover:text-ink">Edit</summary>
                <form
                  action={updateTask.bind(null, childId, week, task.id)}
                  className="mt-3 space-y-3"
                >
                  <TaskFields idPrefix={task.id} values={task} goals={goals} />
                  <SubmitButton pending="Saving…">Save changes</SubmitButton>
                </form>
                <form action={deleteTask.bind(null, childId, week, task.id)} className="mt-2">
                  <ConfirmButton
                    className="btn btn-quiet text-hard"
                    message={`Delete "${task.title}"? Any practice logged against it is deleted too.`}
                  >
                    Delete task
                  </ConfirmButton>
                </form>
              </details>
            </article>
          );
        })}

        {tasks.length > 0 && (
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
            <span className="flex items-center gap-1">
              <span className="h-3 w-3 rounded-full bg-easy" /> easy
            </span>
            <span className="flex items-center gap-1">
              <span className="h-3 w-3 rounded-full bg-ok" /> ok
            </span>
            <span className="flex items-center gap-1">
              <span className="h-3 w-3 rounded-full bg-hard" /> hard
            </span>
            <span className="flex items-center gap-1">
              <span className="h-3 w-3 rounded-full border border-line bg-paper" /> not practised
            </span>
          </div>
        )}

        {/* ---- add tasks */}
        <div className="card space-y-4">
          <AiAction
            action={draftWeekWithAi.bind(null, childId, week)}
            label={tasks.length ? "Draft more tasks with AI" : "Draft this week with AI"}
            pending="Drafting… this can take a minute"
          />

          {library.length > 0 && (
            <form
              action={addTaskFromExercise.bind(null, childId, week)}
              className="flex flex-wrap items-end gap-3 border-t border-line pt-4"
            >
              <div className="min-w-56 flex-1">
                <label className="label" htmlFor="exercise_id">
                  From your library
                </label>
                <select id="exercise_id" name="exercise_id" required className="input">
                  {library.map((exercise) => (
                    <option key={exercise.id} value={exercise.id}>
                      {exercise.title}
                    </option>
                  ))}
                </select>
              </div>
              <SubmitButton pending="Adding…">Add to week</SubmitButton>
            </form>
          )}

          <details className="border-t border-line pt-4">
            <summary className="cursor-pointer text-sm font-medium">Write a task</summary>
            <form action={addTask.bind(null, childId, week)} className="mt-3 space-y-3">
              <TaskFields idPrefix="new-task" goals={goals} />
              <SubmitButton pending="Adding…">Add task</SubmitButton>
            </form>
          </details>
        </div>
      </section>

      {/* ---------------------------------------------------------- note */}
      <section className="space-y-3">
        <h2 className="h2">Note to parents</h2>
        <form action={savePlanNote.bind(null, childId, week)} className="card space-y-3">
          <label className="label" htmlFor="note">
            Shown at the top of the week in the parent app
          </label>
          <textarea id="note" name="note" rows={2} defaultValue={plan?.note ?? ""} className="input" />
          <SubmitButton pending="Saving…">Save note</SubmitButton>
        </form>
      </section>

      {/* ---------------------------------------------------------- review */}
      {plan && (
        <section className="space-y-3">
          <h2 className="h2">How the week went</h2>

          {notes.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold">Parent notes</h3>
              <ul className="space-y-2 text-sm">
                {notes.map((log) => (
                  <li key={log.id}>
                    <span className="text-muted">
                      {formatDay(log.practiced_on)} · {taskTitle.get(log.task_id)} · {log.rating}:
                    </span>{" "}
                    {log.note}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="card space-y-4">
            {insight ? (
              <div>
                <h3 className="mb-1 text-sm font-semibold">
                  ✦ AI review <span className="font-normal text-muted">(only you see this)</span>
                </h3>
                <p className="text-sm whitespace-pre-line">{insight.summary}</p>
              </div>
            ) : (
              <p className="text-sm text-muted">
                {logs.length === 0
                  ? "Nothing has been logged for this week yet."
                  : "Get a summary of this week, a review of each goal, and suggested next goals."}
              </p>
            )}
            <AiAction
              action={reviewWeekWithAi.bind(null, childId, week)}
              label={insight ? "Refresh review" : "Review this week with AI"}
              pending="Reviewing… this can take a minute"
            />

            {(insight || plan.parent_summary) && (
              <form
                action={shareParentSummary.bind(null, childId, week)}
                className="space-y-3 border-t border-line pt-4"
              >
                <label className="label" htmlFor="parent_summary">
                  Summary for parents{" "}
                  {plan.parent_summary
                    ? "(shared; edit and save to update, or clear it to unshare)"
                    : "(AI draft; not shared until you save it)"}
                </label>
                <textarea
                  id="parent_summary"
                  name="parent_summary"
                  rows={4}
                  defaultValue={plan.parent_summary || insight?.parent_summary_draft || ""}
                  className="input"
                />
                <SubmitButton pending="Saving…">
                  {plan.parent_summary ? "Update shared summary" : "Share with parents"}
                </SubmitButton>
              </form>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
