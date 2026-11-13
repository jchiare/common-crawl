#!/usr/bin/env bash
# Applies the migrations to a throwaway database on a local Postgres and runs
# the RLS tests. Usage: PGUSER=postgres supabase/tests/run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
db="speech_rls_test"

psql -v ON_ERROR_STOP=1 -q -d postgres -c "drop database if exists $db" -c "create database $db"
psql -v ON_ERROR_STOP=1 -q -d "$db" -f "$here/supabase_stub.sql"
for f in "$here"/../migrations/*.sql; do
  psql -v ON_ERROR_STOP=1 -q -d "$db" -f "$f"
done
psql -v ON_ERROR_STOP=1 -q -d "$db" -f "$here/rls_test.sql"
psql -q -d postgres -c "drop database $db"
