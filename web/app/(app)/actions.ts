"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { SupabaseClient } from "@supabase/supabase-js";
import { AiError, draftPlan, reviewWeek } from "@/lib/ai";
import { buildAiContext } from "@/lib/context";
import { requireUser } from "@/lib/supabase/server";
import type { GoalStatus } from "@/lib/types";
import { addDays, isMonday } from "@/lib/week";

// Every action runs as the signed-in user; RLS in the database decides what
// they may touch, so there are no separate ownership checks here.

export type ActionState = { error?: string; ok?: string } | null;

const GOAL_STATUSES: GoalStatus[] = ["suggested", "next", "active", "achieved"];

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function int(form: FormData, key: string, fallback: number, lo: number, hi: number): number {
  const n = Number.parseInt(text(form, key), 10);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback;
}

function words(form: FormData): string[] {
  return text(form, "words")
    .split(/[,\n]/)
    .map((w) => w.trim())
    .filter(Boolean);
}

function fail(error: { message: string } | null): asserts error is null {
  if (error) throw new Error(error.message);
}

const childPath = (childId: string) => `/children/${childId}`;
const weekPath = (childId: string, week: string) => `/children/${childId}/weeks/${week}`;

// ---------------------------------------------------------------- session

export async function signOut() {
  const { supabase } = await requireUser();
  await supabase.auth.signOut();
  redirect("/login");
}

// ---------------------------------------------------------------- children

export async function addChild(form: FormData) {
  const { supabase } = await requireUser();
  const first_name = text(form, "first_name");
  if (!first_name) return;
  const birth = Number.parseInt(text(form, "birth_year"), 10);
  const { data, error } = await supabase
    .from("children")
    .insert({ first_name, birth_year: Number.isFinite(birth) ? birth : null })
    .select("id")
    .single();
  fail(error);
  redirect(childPath(data!.id));
}

export async function updateChild(childId: string, form: FormData) {
  const { supabase } = await requireUser();
  const first_name = text(form, "first_name");
  const birth = Number.parseInt(text(form, "birth_year"), 10);
  const { error } = await supabase
    .from("children")
    .update({
      ...(first_name ? { first_name } : {}),
      birth_year: Number.isFinite(birth) ? birth : null,
      notes: text(form, "notes"),
    })
    .eq("id", childId);
  fail(error);
  revalidatePath(childPath(childId));
}

export async function deleteChild(childId: string) {
  const { supabase } = await requireUser();
  const { error } = await supabase.from("children").delete().eq("id", childId);
  fail(error);
  redirect("/");
}

// ---------------------------------------------------------------- parents

export async function inviteParent(childId: string, form: FormData) {
  const { supabase } = await requireUser();
  const email = text(form, "email").toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return;
  const { error } = await supabase
    .from("invites")
    .upsert({ child_id: childId, email }, { onConflict: "child_id,email", ignoreDuplicates: true });
  fail(error);
  revalidatePath(childPath(childId));
}

export async function revokeInvite(childId: string, inviteId: string) {
  const { supabase } = await requireUser();
  const { error } = await supabase.rpc("revoke_invite", { invite: inviteId });
  fail(error);
  revalidatePath(childPath(childId));
}

// ---------------------------------------------------------------- goals

export async function addGoal(childId: string, form: FormData) {
  const { supabase } = await requireUser();
  const title = text(form, "title");
  if (!title) return;
  const status = text(form, "status") === "next" ? "next" : "active";
  const { error } = await supabase
    .from("goals")
    .insert({ child_id: childId, title, detail: text(form, "detail"), status });
  fail(error);
  revalidatePath(childPath(childId));
}

export async function setGoalStatus(childId: string, goalId: string, status: GoalStatus) {
  if (!GOAL_STATUSES.includes(status)) return;
  const { supabase } = await requireUser();
  const { error } = await supabase.from("goals").update({ status }).eq("id", goalId);
  fail(error);
  revalidatePath(childPath(childId), "layout");
}

export async function deleteGoal(childId: string, goalId: string) {
  const { supabase } = await requireUser();
  const { error } = await supabase.from("goals").delete().eq("id", goalId);
  fail(error);
  revalidatePath(childPath(childId), "layout");
}

// ---------------------------------------------------------------- exercise library

export async function addExercise(form: FormData) {
  const { supabase } = await requireUser();
  const title = text(form, "title");
  if (!title) return;
  const { error } = await supabase.from("exercises").insert({
    title,
    instructions: text(form, "instructions"),
    words: words(form),
    minutes_per_day: int(form, "minutes_per_day", 5, 1, 120),
    days_per_week: int(form, "days_per_week", 5, 1, 7),
    media_url: text(form, "media_url") || null,
  });
  fail(error);
  revalidatePath("/library");
}

export async function deleteExercise(exerciseId: string) {
  const { supabase } = await requireUser();
  const { error } = await supabase.from("exercises").delete().eq("id", exerciseId);
  fail(error);
  revalidatePath("/library");
}

// ---------------------------------------------------------------- weekly plan

/** Returns the plan for that week, creating an empty draft if there is none. */
async function ensurePlan(supabase: SupabaseClient, childId: string, week: string) {
  if (!isMonday(week)) throw new Error("A week must start on a Monday.");
  const existing = await supabase
    .from("weekly_plans")
    .select("id, status")
    .eq("child_id", childId)
    .eq("week_start", week)
    .maybeSingle();
  fail(existing.error);
  if (existing.data) return existing.data;
  const created = await supabase
    .from("weekly_plans")
    .insert({ child_id: childId, week_start: week })
    .select("id, status")
    .single();
  fail(created.error);
  return created.data!;
}

async function nextSort(supabase: SupabaseClient, planId: string): Promise<number> {
  const { data } = await supabase
    .from("tasks")
    .select("sort")
    .eq("plan_id", planId)
    .order("sort", { ascending: false })
    .limit(1);
  return (data?.[0]?.sort ?? -1) + 1;
}

export async function addTask(childId: string, week: string, form: FormData) {
  const { supabase } = await requireUser();
  const title = text(form, "title");
  if (!title) return;
  const plan = await ensurePlan(supabase, childId, week);
  const { error } = await supabase.from("tasks").insert({
    plan_id: plan.id,
    child_id: childId,
    title,
    instructions: text(form, "instructions"),
    words: words(form),
    minutes_per_day: int(form, "minutes_per_day", 5, 1, 120),
    days_per_week: int(form, "days_per_week", 5, 1, 7),
    goal_id: text(form, "goal_id") || null,
    media_url: text(form, "media_url") || null,
    sort: await nextSort(supabase, plan.id),
  });
  fail(error);
  revalidatePath(weekPath(childId, week));
}

export async function addTaskFromExercise(childId: string, week: string, form: FormData) {
  const { supabase } = await requireUser();
  const exerciseId = text(form, "exercise_id");
  if (!exerciseId) return;
  const { data: exercise, error: readError } = await supabase
    .from("exercises")
    .select("title, instructions, words, minutes_per_day, days_per_week, media_url")
    .eq("id", exerciseId)
    .maybeSingle();
  fail(readError);
  if (!exercise) return;
  const plan = await ensurePlan(supabase, childId, week);
  const { error } = await supabase.from("tasks").insert({
    ...exercise,
    plan_id: plan.id,
    child_id: childId,
    sort: await nextSort(supabase, plan.id),
  });
  fail(error);
  revalidatePath(weekPath(childId, week));
}

export async function updateTask(childId: string, week: string, taskId: string, form: FormData) {
  const { supabase } = await requireUser();
  const title = text(form, "title");
  if (!title) return;
  const { error } = await supabase
    .from("tasks")
    .update({
      title,
      instructions: text(form, "instructions"),
      words: words(form),
      minutes_per_day: int(form, "minutes_per_day", 5, 1, 120),
      days_per_week: int(form, "days_per_week", 5, 1, 7),
      goal_id: text(form, "goal_id") || null,
      media_url: text(form, "media_url") || null,
    })
    .eq("id", taskId);
  fail(error);
  revalidatePath(weekPath(childId, week));
}

export async function deleteTask(childId: string, week: string, taskId: string) {
  const { supabase } = await requireUser();
  const { error } = await supabase.from("tasks").delete().eq("id", taskId);
  fail(error);
  revalidatePath(weekPath(childId, week));
}

export async function savePlanNote(childId: string, week: string, form: FormData) {
  const { supabase } = await requireUser();
  const plan = await ensurePlan(supabase, childId, week);
  const { error } = await supabase
    .from("weekly_plans")
    .update({ note: text(form, "note") })
    .eq("id", plan.id);
  fail(error);
  revalidatePath(weekPath(childId, week));
}

export async function setPlanPublished(childId: string, week: string, published: boolean) {
  const { supabase } = await requireUser();
  const plan = await ensurePlan(supabase, childId, week);
  const { error } = await supabase
    .from("weekly_plans")
    .update({ status: published ? "published" : "draft" })
    .eq("id", plan.id);
  fail(error);
  revalidatePath(childPath(childId), "layout");
}

export async function shareParentSummary(childId: string, week: string, form: FormData) {
  const { supabase } = await requireUser();
  const plan = await ensurePlan(supabase, childId, week);
  const { error } = await supabase
    .from("weekly_plans")
    .update({ parent_summary: text(form, "parent_summary") })
    .eq("id", plan.id);
  fail(error);
  revalidatePath(weekPath(childId, week));
}

// ---------------------------------------------------------------- AI

/**
 * Drafts tasks for `week` from the child's goals and earlier weeks, and adds
 * them to the (unpublished) plan. Refuses to add to a published plan so
 * nothing AI-written reaches a parent unreviewed.
 */
export async function draftWeekWithAi(
  childId: string,
  week: string,
): Promise<ActionState> {
  const { supabase } = await requireUser();
  try {
    const plan = await ensurePlan(supabase, childId, week);
    if (plan.status === "published") {
      return { error: "Unpublish this week first, so parents don't see unreviewed tasks." };
    }
    // History is everything before this week; this week is what we're drafting.
    const context = await buildAiContext(supabase, childId, addDays(week, -7));
    if (!context) return { error: "Child not found." };
    if (!context.goals.some((g) => g.status === "active")) {
      return { error: "Add at least one active goal first, so the draft has something to aim at." };
    }

    const draft = await draftPlan(context, week);
    if (draft.tasks.length === 0) return { error: "The AI returned no tasks. Try again." };

    const start = await nextSort(supabase, plan.id);
    const { error } = await supabase.from("tasks").insert(
      draft.tasks.map((t, i) => ({
        ...t,
        plan_id: plan.id,
        child_id: childId,
        source: "ai",
        sort: start + i,
      })),
    );
    fail(error);

    // Only fill the note if the therapist hasn't written one.
    const { data: current } = await supabase
      .from("weekly_plans")
      .select("note")
      .eq("id", plan.id)
      .single();
    if (!current?.note && draft.note_to_parents) {
      await supabase.from("weekly_plans").update({ note: draft.note_to_parents }).eq("id", plan.id);
    }

    revalidatePath(weekPath(childId, week));
    return { ok: `Added ${draft.tasks.length} draft tasks. Review and edit before publishing.` };
  } catch (error) {
    if (error instanceof AiError) return { error: error.message };
    throw error;
  }
}

/**
 * Writes the therapist-only review of a week, a draft parent summary, and any
 * suggested next goals (as "suggested", hidden from parents until accepted).
 */
export async function reviewWeekWithAi(
  childId: string,
  week: string,
): Promise<ActionState> {
  const { supabase } = await requireUser();
  try {
    const { data: plan } = await supabase
      .from("weekly_plans")
      .select("id")
      .eq("child_id", childId)
      .eq("week_start", week)
      .maybeSingle();
    if (!plan) return { error: "There is no plan for this week to review." };

    const context = await buildAiContext(supabase, childId, week);
    if (!context) return { error: "Child not found." };

    const review = await reviewWeek(context, week);

    const goalTitle = new Map(context.goals.map((g) => [g.id, g.title]));
    const label = {
      keep_going: "keep going",
      ready_to_mark_achieved: "looks ready to mark achieved",
      consider_easing: "consider easing",
    } as const;
    const goalLines = review.goal_reviews.map(
      (r) => `• ${goalTitle.get(r.goal_id)}: ${label[r.recommendation]}. ${r.reason}`,
    );
    const summary = [review.therapist_summary, ...(goalLines.length ? ["", ...goalLines] : [])].join(
      "\n",
    );

    const saved = await supabase.from("plan_insights").upsert({
      plan_id: plan.id,
      child_id: childId,
      summary,
      parent_summary_draft: review.parent_summary,
      generated_at: new Date().toISOString(),
    });
    fail(saved.error);

    if (review.suggested_goals.length) {
      // Skip ones already suggested by an earlier review.
      const { data: existing } = await supabase
        .from("goals")
        .select("title")
        .eq("child_id", childId);
      const have = new Set((existing ?? []).map((g) => g.title.trim().toLowerCase()));
      const fresh = review.suggested_goals.filter((g) => !have.has(g.title.toLowerCase()));
      if (fresh.length) {
        const added = await supabase
          .from("goals")
          .insert(fresh.map((g) => ({ ...g, child_id: childId, status: "suggested", source: "ai" })));
        fail(added.error);
      }
    }

    revalidatePath(childPath(childId), "layout");
    return { ok: "Review ready." };
  } catch (error) {
    if (error instanceof AiError) return { error: error.message };
    throw error;
  }
}
