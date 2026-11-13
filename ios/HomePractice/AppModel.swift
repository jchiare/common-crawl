import Foundation
import Observation
import Supabase

/// The app's state: who is signed in, which child is selected, and that
/// child's current week.
@MainActor
@Observable
final class AppModel {
    enum Phase {
        case loading, signedOut, signedIn
    }

    private(set) var phase: Phase = .loading
    private(set) var email: String?

    private(set) var children: [Child] = []
    private(set) var selectedChildID: UUID?

    private(set) var weekStart = Week.monday()
    private(set) var plan: Plan?
    private(set) var tasks: [PracticeTask] = []
    private(set) var logs: [PracticeLog] = []
    private(set) var goals: [Goal] = []
    private(set) var latestSummary: Plan?

    private(set) var hasLoaded = false
    var errorMessage: String?

    private let api = API()
    private static let selectedChildKey = "selectedChildID"

    var selectedChild: Child? {
        children.first { $0.id == selectedChildID }
    }

    var today: String { Week.day() }

    // MARK: Session

    /// Follows sign-in state for the life of the app.
    func start() async {
        guard Config.isConfigured else {
            phase = .signedOut
            return
        }
        for await (event, session) in api.client.auth.authStateChanges {
            switch event {
            case .initialSession, .signedIn:
                if let session {
                    email = session.user.email
                    if phase != .signedIn {
                        phase = .signedIn
                        await refresh(claimInvites: true)
                    }
                } else {
                    phase = .signedOut
                }
            case .signedOut:
                reset()
                phase = .signedOut
            default:
                break
            }
        }
    }

    func sendCode(to email: String) async throws {
        try await api.sendCode(to: email)
    }

    func verify(email: String, code: String) async throws {
        try await api.verify(email: email, code: code)
    }

    func signOut() async {
        do {
            try await api.signOut()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func setSelectedChild(_ id: UUID?) {
        selectedChildID = id
        UserDefaults.standard.set(id?.uuidString, forKey: Self.selectedChildKey)
    }

    private func reset() {
        email = nil
        children = []
        plan = nil
        tasks = []
        logs = []
        goals = []
        latestSummary = nil
        hasLoaded = false
    }

    // MARK: Loading

    func refresh(claimInvites: Bool = false) async {
        do {
            if claimInvites || children.isEmpty {
                // Picks up any invitation sent to this email since last time.
                try await api.claimInvites()
            }
            children = try await api.children()
            if selectedChild == nil {
                let saved = UserDefaults.standard.string(forKey: Self.selectedChildKey).flatMap(UUID.init)
                setSelectedChild(children.first { $0.id == saved }?.id ?? children.first?.id)
            }
            try await loadSelectedChild()
            errorMessage = nil
        } catch is CancellationError {
            // A newer refresh replaced this one.
        } catch let error as URLError where error.code == .cancelled {
            // Same, surfaced by the network layer.
        } catch {
            errorMessage = error.localizedDescription
        }
        hasLoaded = true
    }

    func select(_ child: Child) async {
        guard child.id != selectedChildID else { return }
        setSelectedChild(child.id)
        plan = nil
        tasks = []
        logs = []
        goals = []
        latestSummary = nil
        await refresh()
    }

    private func loadSelectedChild() async throws {
        weekStart = Week.monday()
        guard let childID = selectedChildID else {
            plan = nil
            tasks = []
            logs = []
            goals = []
            latestSummary = nil
            return
        }
        let days = Week.days(from: weekStart)

        async let pendingLogs = api.logs(childID: childID, from: days.first ?? weekStart, through: days.last ?? weekStart)
        async let pendingGoals = api.goals(childID: childID)
        async let pendingSummary = api.latestSummary(childID: childID)

        let loadedPlan = try await api.plan(childID: childID, weekStart: weekStart)
        var loadedTasks: [PracticeTask] = []
        if let loadedPlan {
            loadedTasks = try await api.tasks(planID: loadedPlan.id)
        }
        let loadedLogs = try await pendingLogs
        let loadedGoals = try await pendingGoals
        let loadedSummary = try await pendingSummary

        // Ignore the result if the parent switched child while this was loading.
        guard childID == selectedChildID else { return }
        self.plan = loadedPlan
        self.tasks = loadedTasks
        self.logs = loadedLogs
        self.goals = loadedGoals
        self.latestSummary = loadedSummary
    }

    // MARK: Practice

    func logs(for task: PracticeTask) -> [PracticeLog] {
        logs.filter { $0.taskID == task.id }
    }

    func todaysLog(for task: PracticeTask) -> PracticeLog? {
        logs.first { $0.taskID == task.id && $0.practicedOn == today }
    }

    func logToday(_ task: PracticeTask, rating: Rating, note: String) async throws {
        guard let childID = selectedChildID else { return }
        let log = NewPracticeLog(
            taskID: task.id,
            childID: childID,
            practicedOn: today,
            rating: rating,
            note: note.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        try await api.save(log)
        await refresh()
    }

    func removeTodaysLog(for task: PracticeTask) async throws {
        guard let log = todaysLog(for: task) else { return }
        try await api.deleteLog(id: log.id)
        await refresh()
    }
}
