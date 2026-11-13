import Link from "next/link";
import { requireUser } from "@/lib/supabase/server";
import { signOut } from "./actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { user } = await requireUser();

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-6 px-6 py-3">
          <Link href="/" className="font-semibold text-brand-dark">
            Home Practice
          </Link>
          <nav className="flex gap-4 text-sm">
            <Link href="/" className="hover:text-brand">
              Children
            </Link>
            <Link href="/library" className="hover:text-brand">
              Exercise library
            </Link>
          </nav>
          <form action={signOut} className="ml-auto flex items-center gap-3 text-sm text-muted">
            <span className="hidden sm:inline">{user.email}</span>
            <button className="btn btn-quiet">Sign out</button>
          </form>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-8">{children}</main>
    </div>
  );
}
