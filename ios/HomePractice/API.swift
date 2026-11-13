import Foundation
import Supabase

/// Every call the parent app makes to the backend. All of them run as the
/// signed-in parent, and the database only returns rows for their children.
struct API {
    let client: SupabaseClient

    init() {
        client = SupabaseClient(supabaseURL: Config.supabaseURL, supabaseKey: Config.supabaseAnonKey)
    }

    // MARK: Sign-in

    func sendCode(to email: String) async throws {
        try await client.auth.signInWithOTP(email: email, shouldCreateUser: true)
    }

    func verify(email: String, code: String) async throws {
        try await client.auth.verifyOTP(email: email, token: code, type: .email)
    }

    func signOut() async throws {
        try await client.auth.signOut()
    }

    /// Links this parent to every child they were invited to.
    func claimInvites() async throws {
        try await client.rpc("claim_invites").execute()
    }

    // MARK: Reading

    func children() async throws -> [Child] {
        try await client.from("children")
            .select("id, first_name")
            .order("first_name")
            .execute()
            .value
    }

    func plan(childID: UUID, weekStart: String) async throws -> Plan? {
        let plans: [Plan] = try await client.from("weekly_plans")
            .select("id, week_start, note, parent_summary")
            .eq("child_id", value: childID.uuidString)
            .eq("week_start", value: weekStart)
            .limit(1)
            .execute()
            .value
        return plans.first
    }

    func tasks(planID: UUID) async throws -> [PracticeTask] {
        try await client.from("tasks")
            .select("id, goal_id, title, instructions, words, minutes_per_day, days_per_week, media_url")
            .eq("plan_id", value: planID.uuidString)
            .order("sort")
            .execute()
            .value
    }

    func logs(childID: UUID, from firstDay: String, through lastDay: String) async throws -> [PracticeLog] {
        try await client.from("practice_logs")
            .select("id, task_id, practiced_on, rating, note")
            .eq("child_id", value: childID.uuidString)
            .gte("practiced_on", value: firstDay)
            .lte("practiced_on", value: lastDay)
            .execute()
            .value
    }

    func goals(childID: UUID) async throws -> [Goal] {
        try await client.from("goals")
            .select("id, title, detail, status")
            .eq("child_id", value: childID.uuidString)
            .order("sort")
            .execute()
            .value
    }

    /// The most recent summary the therapist has shared, if any.
    func latestSummary(childID: UUID) async throws -> Plan? {
        let plans: [Plan] = try await client.from("weekly_plans")
            .select("id, week_start, note, parent_summary")
            .eq("child_id", value: childID.uuidString)
            .neq("parent_summary", value: "")
            .order("week_start", ascending: false)
            .limit(1)
            .execute()
            .value
        return plans.first
    }

    // MARK: Writing

    /// Saves (or replaces) the log for one task on one day.
    func save(_ log: NewPracticeLog) async throws {
        try await client.from("practice_logs")
            .upsert(log, onConflict: "task_id,practiced_on")
            .execute()
    }

    func deleteLog(id: UUID) async throws {
        try await client.from("practice_logs")
            .delete()
            .eq("id", value: id.uuidString)
            .execute()
    }
}
