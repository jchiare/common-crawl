export type GoalStatus = "suggested" | "next" | "active" | "achieved";
export type Rating = "easy" | "ok" | "hard";

export type Child = {
  id: string;
  first_name: string;
  birth_year: number | null;
  notes: string;
};

export type Goal = {
  id: string;
  child_id: string;
  title: string;
  detail: string;
  status: GoalStatus;
  source: "therapist" | "ai";
};

export type Invite = {
  id: string;
  email: string;
  accepted_at: string | null;
};

export type Exercise = {
  id: string;
  title: string;
  instructions: string;
  words: string[];
  minutes_per_day: number;
  days_per_week: number;
  media_url: string | null;
};

export type Plan = {
  id: string;
  child_id: string;
  week_start: string;
  status: "draft" | "published";
  note: string;
  parent_summary: string;
};

export type Task = {
  id: string;
  plan_id: string;
  goal_id: string | null;
  title: string;
  instructions: string;
  words: string[];
  minutes_per_day: number;
  days_per_week: number;
  media_url: string | null;
  source: "therapist" | "ai";
  sort: number;
};

export type PracticeLog = {
  id: string;
  task_id: string;
  practiced_on: string;
  rating: Rating;
  note: string;
};

export type Insight = {
  plan_id: string;
  summary: string;
  parent_summary_draft: string;
  generated_at: string;
};
