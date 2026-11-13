# Home Practice

Weekly home-practice plans for speech therapy. A therapist sets goals and assigns a short weekly
plan per child; parents follow it in an iPhone app and log how each day went; the therapist sees
the results. AI drafts plans, weekly reviews and next goals, and the therapist approves everything
before a parent sees it.

| Folder      | What it is                                                                 |
| ----------- | -------------------------------------------------------------------------- |
| `supabase/` | Database schema, access rules (row-level security) and their tests         |
| `web/`      | Therapist web app (Next.js). Also holds the server-side AI calls           |
| `ios/`      | Parent iPhone app (SwiftUI)                                                |

## How it fits together

- **Backend:** Supabase (Postgres, sign-in, API). Both apps talk to it directly, and the database
  decides who can see what: a therapist sees only their own children; a parent sees only children
  they were invited to, and only published plans.
- **Sign-in:** email plus a one-time code, no passwords. A therapist invites a parent by email; the
  parent signs in to the app with that address and is linked automatically.
- **AI:** runs only on the web server (`web/lib/ai.ts`). The child's name is never sent. AI output
  is always a draft: plan tasks go into an unpublished plan, summaries wait for "Share with
  parents", and goals arrive as suggestions.

## Setup

### 1. Supabase

1. Create a project at supabase.com. Choose the region with your privacy obligations in mind,
   since this stores children's health-related data.
2. Run `supabase/migrations/20261113000000_init.sql` in the SQL editor (or `supabase db push`).
3. Authentication > Email Templates: paste `supabase/templates/sign_in_code.html` into both
   **Magic Link** and **Confirm signup** (a first-time sign-in uses the second one). This puts
   the one-time code in the email, which is what parents type into the app.
4. Authentication > URL Configuration: add the web app's address plus `/auth/callback` to the
   redirect URLs (for local work: `http://localhost:3000/auth/callback`).
5. Copy the project URL and anon key from Project Settings > API.

### 2. Web app (therapist)

```bash
cd web
cp .env.example .env.local   # fill in Supabase URL + key, and ANTHROPIC_API_KEY
npm install
npm run dev                  # http://localhost:3000
```

Anyone who signs in on the web gets their own empty therapist workspace.

### 3. iPhone app (parent)

On a Mac with Xcode 16 or newer:

```bash
brew install xcodegen
cd ios
xcodegen generate
open HomePractice.xcodeproj
```

Put the Supabase URL and anon key in `ios/HomePractice/Config.swift`, set your own bundle
identifier and team in the target's Signing settings, and run.

### Running the backend locally instead

With Docker and the Supabase CLI installed, `supabase start` from the repo root runs the whole
backend on your machine with the schema and email template applied. It prints the local URL and
anon key to use in `web/.env.local`; sign-in emails land in the local inbox at
`http://127.0.0.1:54324`.

## Checks

- `supabase/tests/run.sh` applies the migrations to a throwaway local Postgres and tests the
  access rules (`PGUSER=postgres supabase/tests/run.sh`).
- `cd web && npm run lint && npm run build`
- GitHub Actions runs both of those, and builds and unit-tests the iOS app on a Mac runner
  whenever `ios/` changes.

## Not built yet

Scheduling and appointment notifications for therapists, server-sent push notifications, audio or
video recording, in-app messaging, and App Store / TestFlight distribution.
