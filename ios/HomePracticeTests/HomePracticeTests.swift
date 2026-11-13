import XCTest
@testable import HomePractice

final class WeekTests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!

    private func date(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    func testMondayOfEachWeekday() {
        // 2026-11-09 is a Monday.
        XCTAssertEqual(Week.monday(of: date("2026-11-09T12:00:00Z"), in: utc), "2026-11-09")
        XCTAssertEqual(Week.monday(of: date("2026-11-13T12:00:00Z"), in: utc), "2026-11-09")
        XCTAssertEqual(Week.monday(of: date("2026-11-15T23:59:00Z"), in: utc), "2026-11-09")
        XCTAssertEqual(Week.monday(of: date("2026-11-16T00:00:00Z"), in: utc), "2026-11-16")
    }

    func testMondayCrossesMonthAndYear() {
        // Thursday 1 Jan 2026 belongs to the week of Monday 29 Dec 2025.
        XCTAssertEqual(Week.monday(of: date("2026-01-01T12:00:00Z"), in: utc), "2025-12-29")
    }

    func testDayUsesTheGivenTimeZone() {
        // 03:00 UTC on Monday is still Sunday evening in Toronto.
        let instant = date("2026-11-16T03:00:00Z")
        let toronto = TimeZone(identifier: "America/Toronto")!
        XCTAssertEqual(Week.day(instant, in: utc), "2026-11-16")
        XCTAssertEqual(Week.day(instant, in: toronto), "2026-11-15")
        XCTAssertEqual(Week.monday(of: instant, in: toronto), "2026-11-09")
    }

    func testDaysOfWeek() {
        let days = Week.days(from: "2026-11-09")
        XCTAssertEqual(days.count, 7)
        XCTAssertEqual(days.first, "2026-11-09")
        XCTAssertEqual(days.last, "2026-11-15")
        XCTAssertEqual(Week.letter(for: "2026-11-09"), "M")
        XCTAssertEqual(Week.letter(for: "2026-11-15"), "S")
    }

    func testDaysAcrossDaylightSavingChange() {
        // US clocks change on 2026-03-08; the dates must still be consecutive.
        XCTAssertEqual(
            Week.days(from: "2026-03-02"),
            ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-07", "2026-03-08"]
        )
    }
}

final class ModelDecodingTests: XCTestCase {
    func testDecodesTaskFromDatabaseJSON() throws {
        let json = """
        [{
          "id": "00000000-0000-0000-0000-00000000e001",
          "goal_id": null,
          "title": "Snake sounds",
          "instructions": "Say each word slowly.",
          "words": ["sun", "sock"],
          "minutes_per_day": 5,
          "days_per_week": 4,
          "media_url": null
        }]
        """
        let tasks = try JSONDecoder().decode([PracticeTask].self, from: Data(json.utf8))
        XCTAssertEqual(tasks.first?.title, "Snake sounds")
        XCTAssertEqual(tasks.first?.words, ["sun", "sock"])
        XCTAssertEqual(tasks.first?.daysPerWeek, 4)
        XCTAssertNil(tasks.first?.goalID)
    }

    func testDecodesLogAndEncodesNewLog() throws {
        let json = """
        {
          "id": "00000000-0000-0000-0000-00000000aa01",
          "task_id": "00000000-0000-0000-0000-00000000e001",
          "practiced_on": "2026-11-10",
          "rating": "hard",
          "note": "tired today"
        }
        """
        let log = try JSONDecoder().decode(PracticeLog.self, from: Data(json.utf8))
        XCTAssertEqual(log.rating, .hard)
        XCTAssertEqual(log.practicedOn, "2026-11-10")

        let new = NewPracticeLog(
            taskID: log.taskID,
            childID: UUID(uuidString: "00000000-0000-0000-0000-00000000c001")!,
            practicedOn: "2026-11-11",
            rating: .easy,
            note: ""
        )
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(new)) as? [String: Any]
        XCTAssertEqual(encoded?["practiced_on"] as? String, "2026-11-11")
        XCTAssertEqual(encoded?["rating"] as? String, "easy")
        XCTAssertNotNil(encoded?["task_id"])
        XCTAssertNotNil(encoded?["child_id"])
    }
}
