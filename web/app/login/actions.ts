"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type LoginState = { step: "email" | "code"; email: string; error?: string };

export async function login(prev: LoginState, form: FormData): Promise<LoginState> {
  const supabase = await createClient();

  if (form.get("intent") === "restart") return { step: "email", email: "" };

  if (prev.step === "email") {
    const email = String(form.get("email") ?? "")
      .trim()
      .toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return { step: "email", email, error: "Enter a valid email address." };
    }
    const origin = (await headers()).get("origin") ?? "";
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${origin}/auth/callback` },
    });
    if (error) return { step: "email", email, error: error.message };
    return { step: "code", email };
  }

  const token = String(form.get("code") ?? "").replace(/\s/g, "");
  const { error } = await supabase.auth.verifyOtp({ email: prev.email, token, type: "email" });
  if (error) {
    return { step: "code", email: prev.email, error: "That code didn't work. Check it and try again." };
  }
  redirect("/");
}
