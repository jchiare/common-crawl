import type { Goal } from "@/lib/types";

type Values = {
  title?: string;
  instructions?: string;
  words?: string[];
  minutes_per_day?: number;
  days_per_week?: number;
  goal_id?: string | null;
  media_url?: string | null;
};

/** Form fields shared by tasks and library exercises. `goals` adds the goal picker. */
export function TaskFields({
  idPrefix,
  values = {},
  goals,
}: {
  idPrefix: string;
  values?: Values;
  goals?: Goal[];
}) {
  const id = (name: string) => `${idPrefix}-${name}`;
  return (
    <div className="space-y-3">
      <div>
        <label className="label" htmlFor={id("title")}>
          Title
        </label>
        <input
          id={id("title")}
          name="title"
          required
          defaultValue={values.title}
          placeholder="e.g. Snake sounds with picture cards"
          className="input"
        />
      </div>
      <div>
        <label className="label" htmlFor={id("instructions")}>
          Instructions for the parent
        </label>
        <textarea
          id={id("instructions")}
          name="instructions"
          rows={3}
          defaultValue={values.instructions}
          className="input"
        />
      </div>
      <div>
        <label className="label" htmlFor={id("words")}>
          Practice words (comma separated, optional)
        </label>
        <input
          id={id("words")}
          name="words"
          defaultValue={values.words?.join(", ")}
          placeholder="sun, sock, soap"
          className="input"
        />
      </div>
      <div className="flex flex-wrap gap-3">
        <div className="w-28">
          <label className="label" htmlFor={id("minutes")}>
            Minutes a day
          </label>
          <input
            id={id("minutes")}
            name="minutes_per_day"
            type="number"
            min={1}
            max={120}
            defaultValue={values.minutes_per_day ?? 5}
            className="input"
          />
        </div>
        <div className="w-28">
          <label className="label" htmlFor={id("days")}>
            Days a week
          </label>
          <input
            id={id("days")}
            name="days_per_week"
            type="number"
            min={1}
            max={7}
            defaultValue={values.days_per_week ?? 5}
            className="input"
          />
        </div>
        {goals && (
          <div className="min-w-40 flex-1">
            <label className="label" htmlFor={id("goal")}>
              Goal
            </label>
            <select
              id={id("goal")}
              name="goal_id"
              defaultValue={values.goal_id ?? ""}
              className="input"
            >
              <option value="">None</option>
              {goals.map((goal) => (
                <option key={goal.id} value={goal.id}>
                  {goal.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div>
        <label className="label" htmlFor={id("media")}>
          Demo video or audio link (optional)
        </label>
        <input
          id={id("media")}
          name="media_url"
          type="url"
          defaultValue={values.media_url ?? ""}
          placeholder="https://…"
          className="input"
        />
      </div>
    </div>
  );
}
