"use client";

import { useActionState } from "react";
import { SubmitButton } from "@/components/buttons";
import { login, type LoginState } from "./actions";

const initial: LoginState = { step: "email", email: "" };

export default function LoginPage() {
  const [state, action] = useActionState(login, initial);

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-2xl font-semibold">Home Practice</h1>
      <p className="mt-1 mb-6 text-sm text-muted">Therapist sign-in</p>

      <form action={action} className="card space-y-4">
        {state.step === "email" ? (
          <div>
            <label className="label" htmlFor="email">
              Work email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              autoFocus
              defaultValue={state.email}
              className="input"
            />
          </div>
        ) : (
          <div>
            <p className="mb-3 text-sm">
              We emailed a sign-in code to <strong>{state.email}</strong>. Enter it here, or open the
              link in that email.
            </p>
            <label className="label" htmlFor="code">
              Code
            </label>
            <input
              id="code"
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              autoFocus
              className="input tracking-widest"
            />
          </div>
        )}

        {state.error && (
          <p role="alert" className="text-sm text-hard">
            {state.error}
          </p>
        )}

        <SubmitButton className="btn btn-primary w-full" pending="One moment…">
          {state.step === "email" ? "Email me a code" : "Sign in"}
        </SubmitButton>

        {state.step === "code" && (
          <button name="intent" value="restart" formNoValidate className="btn btn-quiet w-full">
            Use a different email
          </button>
        )}
      </form>
    </main>
  );
}
