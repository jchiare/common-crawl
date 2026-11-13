import SwiftUI

/// This week's tasks for the selected child.
struct WeekView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            content
                .navigationTitle(model.selectedChild.map { "\($0.firstName)'s week" } ?? "This week")
                .navigationDestination(for: PracticeTask.self) { task in
                    TaskDetailView(task: task)
                }
                .toolbar {
                    if model.children.count > 1 {
                        ToolbarItem(placement: .topBarTrailing) { ChildPicker() }
                    }
                }
                .refreshable { await model.refresh() }
        }
    }

    @ViewBuilder
    private var content: some View {
        if !model.hasLoaded {
            ProgressView()
        } else if model.children.isEmpty {
            EmptyState(
                symbol: "envelope.open",
                title: "No invitation found yet",
                message: "Ask your therapist to invite \(model.email ?? "your email address"), then pull down to refresh."
            )
        } else if model.plan == nil || model.tasks.isEmpty {
            EmptyState(
                symbol: "calendar",
                title: "No plan yet this week",
                message: "Your therapist hasn't shared this week's practice yet. Pull down to check again."
            )
        } else {
            List {
                if let message = model.errorMessage {
                    Section {
                        Label(message, systemImage: "wifi.exclamationmark")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                if let note = model.plan?.note, !note.isEmpty {
                    Section("From your therapist") {
                        Text(note)
                    }
                }

                Section {
                    ForEach(model.tasks) { task in
                        NavigationLink(value: task) {
                            TaskRow(task: task)
                        }
                    }
                } header: {
                    Text("Today")
                } footer: {
                    Text(todayFooter)
                }
            }
        }
    }

    private var todayFooter: String {
        let done = model.tasks.filter { model.todaysLog(for: $0) != nil }.count
        if done == model.tasks.count { return "All done for today. Nice work!" }
        return "\(done) of \(model.tasks.count) done today"
    }
}

private struct TaskRow: View {
    @Environment(AppModel.self) private var model
    let task: PracticeTask

    var body: some View {
        let logs = model.logs(for: task)
        let doneToday = model.todaysLog(for: task) != nil

        HStack(spacing: 12) {
            Image(systemName: doneToday ? "checkmark.circle.fill" : "circle")
                .font(.title2)
                .foregroundStyle(doneToday ? Color.accentColor : Color.secondary)
                .accessibilityLabel(doneToday ? "Done today" : "Not done today")

            VStack(alignment: .leading, spacing: 6) {
                Text(task.title)
                    .font(.headline)
                Text("\(task.minutesPerDay) min · \(logs.count) of \(task.daysPerWeek) days this week")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                WeekDots(weekStart: model.weekStart, logs: logs)
            }
        }
        .padding(.vertical, 4)
    }
}

/// Seven dots, Monday to Sunday, coloured by how each day's practice went.
struct WeekDots: View {
    let weekStart: String
    let logs: [PracticeLog]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(Week.days(from: weekStart), id: \.self) { day in
                let log = logs.first { $0.practicedOn == day }
                VStack(spacing: 2) {
                    Text(Week.letter(for: day))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Circle()
                        .fill(log?.rating.color ?? Color(.systemGray5))
                        .frame(width: 12, height: 12)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Practised \(logs.count) days this week")
    }
}

struct ChildPicker: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Menu {
            ForEach(model.children) { child in
                Button {
                    Task { await model.select(child) }
                } label: {
                    if child.id == model.selectedChildID {
                        Label(child.firstName, systemImage: "checkmark")
                    } else {
                        Text(child.firstName)
                    }
                }
            }
        } label: {
            Label("Switch child", systemImage: "person.2")
        }
    }
}

struct EmptyState: View {
    let symbol: String
    let title: String
    let message: String

    var body: some View {
        // In a ScrollView so pull-to-refresh works on the empty screen too.
        ScrollView {
            ContentUnavailableView(title, systemImage: symbol, description: Text(message))
                .padding(.top, 80)
        }
    }
}
