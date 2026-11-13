import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model

    @AppStorage("reminderEnabled") private var reminderEnabled = false
    /// Minutes after midnight; default 6:00 pm.
    @AppStorage("reminderMinutes") private var reminderMinutes = 18 * 60
    @State private var reminderDenied = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Daily reminder", isOn: $reminderEnabled)
                    if reminderEnabled {
                        DatePicker("Time", selection: reminderTime, displayedComponents: .hourAndMinute)
                    }
                } header: {
                    Text("Practice reminder")
                } footer: {
                    if reminderDenied {
                        Text("Notifications are turned off for this app. Turn them on in the Settings app to get reminders.")
                    }
                }

                Section("Account") {
                    if let email = model.email {
                        LabeledContent("Signed in as", value: email)
                    }
                    Button("Sign out", role: .destructive) {
                        Reminders.disable()
                        reminderEnabled = false
                        Task { await model.signOut() }
                    }
                }
            }
            .navigationTitle("Settings")
            .onChange(of: reminderEnabled) { _, _ in applyReminder() }
            .onChange(of: reminderMinutes) { _, _ in applyReminder() }
        }
    }

    private var reminderTime: Binding<Date> {
        Binding {
            Calendar.current.date(
                bySettingHour: reminderMinutes / 60,
                minute: reminderMinutes % 60,
                second: 0,
                of: Date()
            ) ?? Date()
        } set: { date in
            let parts = Calendar.current.dateComponents([.hour, .minute], from: date)
            reminderMinutes = (parts.hour ?? 18) * 60 + (parts.minute ?? 0)
        }
    }

    private func applyReminder() {
        guard reminderEnabled else {
            Reminders.disable()
            return
        }
        reminderDenied = false
        Task {
            let allowed = (try? await Reminders.enable(hour: reminderMinutes / 60, minute: reminderMinutes % 60)) ?? false
            if !allowed {
                reminderDenied = true
                reminderEnabled = false
            }
        }
    }
}
