import Foundation
import UserNotifications

/// A daily practice reminder, scheduled on the phone itself (no server).
enum Reminders {
    private static let identifier = "daily-practice"

    /// Schedules the reminder. Returns false if the parent declined notifications.
    static func enable(hour: Int, minute: Int) async throws -> Bool {
        let center = UNUserNotificationCenter.current()
        guard try await center.requestAuthorization(options: [.alert, .sound]) else {
            return false
        }

        let content = UNMutableNotificationContent()
        content.title = "Practice time"
        content.body = "A few minutes of speech practice today?"
        content.sound = .default

        var time = DateComponents()
        time.hour = hour
        time.minute = minute
        let trigger = UNCalendarNotificationTrigger(dateMatching: time, repeats: true)

        center.removePendingNotificationRequests(withIdentifiers: [identifier])
        try await center.add(UNNotificationRequest(identifier: identifier, content: content, trigger: trigger))
        return true
    }

    static func disable() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [identifier])
    }
}
