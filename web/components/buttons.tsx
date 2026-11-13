"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import type { ActionState } from "@/app/(app)/actions";

/** Submit button that disables itself and shows `pending` text while its form runs. */
export function SubmitButton({
  children,
  pending,
  className = "btn",
}: {
  children: React.ReactNode;
  pending?: string;
  className?: string;
}) {
  const status = useFormStatus();
  return (
    <button type="submit" className={className} disabled={status.pending}>
      {status.pending && pending ? pending : children}
    </button>
  );
}

/** Submit button for destructive actions: asks before submitting. */
export function ConfirmButton({
  children,
  message,
  className = "btn btn-quiet",
}: {
  children: React.ReactNode;
  message: string;
  className?: string;
}) {
  return (
    <button
      type="submit"
      className={className}
      onClick={(event) => {
        if (!window.confirm(message)) event.preventDefault();
      }}
    >
      {children}
    </button>
  );
}

/** One-button form for a slow AI action, with its result shown inline. */
export function AiAction({
  action,
  label,
  pending,
  className = "btn",
}: {
  action: (prev: ActionState, form: FormData) => Promise<ActionState>;
  label: string;
  pending: string;
  className?: string;
}) {
  const [state, formAction] = useActionState(action, null);
  return (
    <form action={formAction} className="flex flex-wrap items-center gap-3">
      <SubmitButton className={className} pending={pending}>
        ✦ {label}
      </SubmitButton>
      {state?.error && (
        <p role="alert" className="text-sm text-hard">
          {state.error}
        </p>
      )}
      {state?.ok && (
        <p role="status" className="text-sm text-brand-dark">
          {state.ok}
        </p>
      )}
    </form>
  );
}
