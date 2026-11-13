import Foundation

/// Plain calendar dates as "yyyy-MM-dd" strings, the way the database stores
/// them. A week is identified by the date of its Monday.
enum Week {
    private static func calendar(_ timeZone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return calendar
    }

    private static func formatter(_ timeZone: TimeZone) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }

    /// The calendar date of `date` as seen in `timeZone`.
    static func day(_ date: Date = Date(), in timeZone: TimeZone = .current) -> String {
        formatter(timeZone).string(from: date)
    }

    /// The Monday on or before `date`, in `timeZone`.
    static func monday(of date: Date = Date(), in timeZone: TimeZone = .current) -> String {
        let calendar = calendar(timeZone)
        // Gregorian weekday: 1 = Sunday ... 7 = Saturday.
        let weekday = calendar.component(.weekday, from: date)
        let daysSinceMonday = (weekday + 5) % 7
        let monday = calendar.date(byAdding: .day, value: -daysSinceMonday, to: date) ?? date
        return day(monday, in: timeZone)
    }

    /// The seven dates of the week starting on `monday`.
    static func days(from monday: String) -> [String] {
        let utc = TimeZone(identifier: "UTC")!
        guard let start = formatter(utc).date(from: monday) else { return [] }
        let calendar = calendar(utc)
        return (0..<7).compactMap { offset in
            calendar.date(byAdding: .day, value: offset, to: start).map { day($0, in: utc) }
        }
    }

    /// "M", "T", "W"... for a "yyyy-MM-dd" date.
    static func letter(for day: String) -> String {
        let utc = TimeZone(identifier: "UTC")!
        guard let date = formatter(utc).date(from: day) else { return "" }
        let symbols = calendar(utc).veryShortWeekdaySymbols
        return symbols[calendar(utc).component(.weekday, from: date) - 1]
    }
}
