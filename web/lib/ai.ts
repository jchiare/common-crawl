import "server-only";
import Anthropic from "@anthropic-ai/sdk";
import { betaZodOutputFormat } from "@anthropic-ai/sdk/helpers/beta/zod";
import { z } from "zod";

// The AI only ever drafts. Nothing it writes reaches a parent until the
// therapist has reviewed it (draft plans are unpublished; summaries are drafts;
// goals arrive as "suggested").

const MODEL = "claude-opus-5-5";

export type AiContext = {
  /** Approximate age in years, if known. The child's name is never sent. */
  age: number | null;
  therapistNotes: string;
  goals: { id: string; title: string; detail: string; status: string }[];
  /** Most recent first. */
  weeks: {
    weekStart: string;
    noteToParents: string;
    tasks: {
      title: string;
      instructions: string;
      words: string[];
      minutesPerDay: number;
      daysPerWeek: number;
      goal: string | null;
      logs: { date: string; rating: string; note: string }[];
    }[];
  }[];
  /** The therapist's own exercise library, as a guide to their style. */
  library: { title: string; instructions: string; words: string[] }[];
};

const SYSTEM = `You assist a licensed speech-language therapist who assigns short home-practice tasks that a parent does with their child each week. You draft; the therapist reviews and edits everything before a parent sees it.

Write for a parent with no clinical training: plain words, concrete steps, a friendly and encouraging tone, no jargon unless you explain it. Keep practice playful and short, since these are young children and tired parents.

Base everything on the record you are given: the child's goals, the therapist's notes, and how recent practice went. Parents rate each practice day easy, ok or hard and may leave a note; treat repeated "hard" ratings or skipped days as a sign to make a task smaller or more fun, and repeated "easy" as a sign the child is ready for the next step. Do not diagnose, and do not invent facts about the child that are not in the record. If the record is thin, say so and keep suggestions conservative.`;

export class AiError extends Error {}

function client(): Anthropic {
  if (!process.env.ANTHROPIC_API_KEY && !process.env.ANTHROPIC_AUTH_TOKEN) {
    throw new AiError("AI is not configured: set ANTHROPIC_API_KEY on the server.");
  }
  return new Anthropic();
}

async function ask<T extends z.ZodType>(schema: T, prompt: string): Promise<z.infer<T>> {
  let response;
  try {
    response = await client().beta.messages.parse({
      model: MODEL,
      max_tokens: 16000,
      thinking: { type: "adaptive" },
      output_config: { effort: "medium", format: betaZodOutputFormat(schema) },
      // If the model declines a request, the API retries it on a fallback model.
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      system: SYSTEM,
      messages: [{ role: "user", content: prompt }],
    });
  } catch (error) {
    if (error instanceof Anthropic.AuthenticationError) {
      throw new AiError("The AI key was rejected. Check ANTHROPIC_API_KEY.");
    }
    if (error instanceof Anthropic.RateLimitError) {
      throw new AiError("The AI service is busy. Try again in a minute.");
    }
    if (error instanceof Anthropic.APIError) {
      throw new AiError(`The AI request failed (${error.status ?? "network"}). Try again.`);
    }
    throw error;
  }
  if (response.stop_reason === "refusal") {
    throw new AiError("The AI declined this request. Write this one by hand.");
  }
  if (response.stop_reason === "max_tokens" || !response.parsed_output) {
    throw new AiError("The AI response was incomplete. Try again.");
  }
  return response.parsed_output;
}

function record(context: AiContext): string {
  return `<child_record>\n${JSON.stringify(context, null, 2)}\n</child_record>`;
}

// ---------------------------------------------------------------- plan draft

const PlanDraft = z.object({
  tasks: z.array(
    z.object({
      title: z.string().describe("Short, parent-friendly name of the activity."),
      instructions: z
        .string()
        .describe("What the parent does, step by step, in 2 to 5 short sentences."),
      words: z
        .array(z.string())
        .describe("Practice words or phrases for this task. Empty if not applicable."),
      minutes_per_day: z.number().int(),
      days_per_week: z.number().int(),
      goal_id: z
        .string()
        .nullable()
        .describe("id of the goal from the record this task works on, or null."),
    }),
  ),
  note_to_parents: z
    .string()
    .describe("One or two warm sentences for the parent about this week's focus."),
});

export type PlanDraft = z.infer<typeof PlanDraft>;

export async function draftPlan(context: AiContext, weekStart: string): Promise<PlanDraft> {
  const draft = await ask(
    PlanDraft,
    `${record(context)}

Draft the home-practice plan for the week starting ${weekStart}.

- Propose 2 to 4 tasks. Each should take 3 to 10 minutes a day; a parent should be able to do the whole plan in about 15 minutes a day.
- Work on the goals marked "active". Only touch a "next" goal if the record shows the child is ready.
- Build on previous weeks: carry forward what is working, step up what was easy, shrink or reshape what was hard. Do not repeat last week unchanged unless the record gives a reason.
- Where the therapist's library has a fitting exercise, follow its style.
- If there are no previous weeks, start gently.`,
  );

  const goalIds = new Set(context.goals.map((g) => g.id));
  const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(n)));
  return {
    note_to_parents: draft.note_to_parents.trim(),
    tasks: draft.tasks
      .filter((t) => t.title.trim())
      .slice(0, 6)
      .map((t) => ({
        title: t.title.trim(),
        instructions: t.instructions.trim(),
        words: t.words.map((w) => w.trim()).filter(Boolean),
        minutes_per_day: clamp(t.minutes_per_day, 1, 30),
        days_per_week: clamp(t.days_per_week, 1, 7),
        goal_id: t.goal_id && goalIds.has(t.goal_id) ? t.goal_id : null,
      })),
  };
}

// ---------------------------------------------------------------- weekly review

const WeekReview = z.object({
  therapist_summary: z
    .string()
    .describe(
      "For the therapist: 3 to 6 sentences on adherence, what was easy or hard, patterns in parent notes, and what to adjust.",
    ),
  parent_summary: z
    .string()
    .describe(
      "For the parent: 2 to 4 encouraging, specific sentences about the week. No clinical claims.",
    ),
  goal_reviews: z.array(
    z.object({
      goal_id: z.string(),
      recommendation: z.enum(["keep_going", "ready_to_mark_achieved", "consider_easing"]),
      reason: z.string().describe("One sentence grounded in the record."),
    }),
  ),
  suggested_goals: z
    .array(
      z.object({
        title: z.string(),
        detail: z.string().describe("One sentence: what it means and why it comes next."),
      }),
    )
    .describe(
      "0 to 2 goals to work on next, only when the record supports it and no existing goal already covers it.",
    ),
});

export type WeekReview = z.infer<typeof WeekReview>;

export async function reviewWeek(context: AiContext, weekStart: string): Promise<WeekReview> {
  const review = await ask(
    WeekReview,
    `${record(context)}

Review the week starting ${weekStart} (the first entry in "weeks"), using earlier weeks for trend.

- Review each "active" goal. Recommend "ready_to_mark_achieved" only with clear, repeated evidence; when unsure, "keep_going".
- If nothing was logged this week, say so plainly in both summaries; do not guess how practice went, and keep the parent summary kind and free of blame.`,
  );

  const goalIds = new Set(context.goals.map((g) => g.id));
  const existing = new Set(context.goals.map((g) => g.title.trim().toLowerCase()));
  return {
    therapist_summary: review.therapist_summary.trim(),
    parent_summary: review.parent_summary.trim(),
    goal_reviews: review.goal_reviews.filter((r) => goalIds.has(r.goal_id)),
    suggested_goals: review.suggested_goals
      .map((g) => ({ title: g.title.trim(), detail: g.detail.trim() }))
      .filter((g) => g.title && !existing.has(g.title.toLowerCase()))
      .slice(0, 2),
  };
}
