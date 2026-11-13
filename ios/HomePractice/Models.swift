import SwiftUI

struct Child: Codable, Identifiable, Hashable {
    let id: UUID
    let firstName: String

    enum CodingKeys: String, CodingKey {
        case id
        case firstName = "first_name"
    }
}

struct Goal: Codable, Identifiable, Hashable {
    let id: UUID
    let title: String
    let detail: String
    /// "active", "next" or "achieved". Parents never receive "suggested" goals.
    let status: String
}

struct Plan: Codable, Identifiable, Hashable {
    let id: UUID
    let weekStart: String
    let note: String
    let parentSummary: String

    enum CodingKeys: String, CodingKey {
        case id, note
        case weekStart = "week_start"
        case parentSummary = "parent_summary"
    }
}

struct PracticeTask: Codable, Identifiable, Hashable {
    let id: UUID
    let goalID: UUID?
    let title: String
    let instructions: String
    let words: [String]
    let minutesPerDay: Int
    let daysPerWeek: Int
    let mediaURL: String?

    enum CodingKeys: String, CodingKey {
        case id, title, instructions, words
        case goalID = "goal_id"
        case minutesPerDay = "minutes_per_day"
        case daysPerWeek = "days_per_week"
        case mediaURL = "media_url"
    }
}

enum Rating: String, Codable, CaseIterable, Identifiable {
    case easy, ok, hard

    var id: String { rawValue }

    var label: String {
        switch self {
        case .easy: "Easy"
        case .ok: "OK"
        case .hard: "Hard"
        }
    }

    var symbol: String {
        switch self {
        case .easy: "face.smiling"
        case .ok: "hand.thumbsup"
        case .hard: "cloud.rain"
        }
    }

    var color: Color {
        switch self {
        case .easy: .green
        case .ok: .orange
        case .hard: .red
        }
    }
}

struct PracticeLog: Codable, Identifiable, Hashable {
    let id: UUID
    let taskID: UUID
    /// "yyyy-MM-dd"
    let practicedOn: String
    let rating: Rating
    let note: String

    enum CodingKeys: String, CodingKey {
        case id, rating, note
        case taskID = "task_id"
        case practicedOn = "practiced_on"
    }
}

/// What the app sends when a parent logs a practice day.
struct NewPracticeLog: Encodable {
    let taskID: UUID
    let childID: UUID
    let practicedOn: String
    let rating: Rating
    let note: String

    enum CodingKeys: String, CodingKey {
        case rating, note
        case taskID = "task_id"
        case childID = "child_id"
        case practicedOn = "practiced_on"
    }
}
