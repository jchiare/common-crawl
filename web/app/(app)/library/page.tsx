import { ConfirmButton, SubmitButton } from "@/components/buttons";
import { TaskFields } from "@/components/task-fields";
import { requireUser } from "@/lib/supabase/server";
import type { Exercise } from "@/lib/types";
import { addExercise, deleteExercise } from "../actions";

export default async function LibraryPage() {
  const { supabase } = await requireUser();
  const { data, error } = await supabase
    .from("exercises")
    .select("id, title, instructions, words, minutes_per_day, days_per_week, media_url")
    .order("title");
  if (error) throw new Error(error.message);
  const exercises = data as Exercise[];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Exercise library</h1>
        <p className="mt-1 text-sm text-muted">
          Your reusable exercises. Add them to any child&apos;s week in one click; AI drafts follow
          their style.
        </p>
      </div>

      {exercises.length > 0 && (
        <ul className="space-y-3">
          {exercises.map((exercise) => (
            <li key={exercise.id} className="card">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{exercise.title}</div>
                  <div className="text-xs text-muted">
                    {exercise.minutes_per_day} min a day · {exercise.days_per_week} days a week
                  </div>
                </div>
                <form action={deleteExercise.bind(null, exercise.id)}>
                  <ConfirmButton message={`Delete "${exercise.title}" from your library?`}>
                    Delete
                  </ConfirmButton>
                </form>
              </div>
              {exercise.instructions && (
                <p className="mt-2 text-sm whitespace-pre-line">{exercise.instructions}</p>
              )}
              {exercise.words.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {exercise.words.map((word) => (
                    <span key={word} className="chip">
                      {word}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <form action={addExercise} className="card space-y-4">
        <h2 className="font-medium">New exercise</h2>
        <TaskFields idPrefix="new-exercise" />
        <SubmitButton className="btn btn-primary" pending="Saving…">
          Save to library
        </SubmitButton>
      </form>
    </div>
  );
}
