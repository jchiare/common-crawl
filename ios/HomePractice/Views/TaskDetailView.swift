import SwiftUI

/// One task: what to do, the practice words, and logging how today went.
struct TaskDetailView: View {
    @Environment(AppModel.self) private var model
    let task: PracticeTask

    @State private var rating: Rating?
    @State private var note = ""
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        let todaysLog = model.todaysLog(for: task)

        List {
            Section {
                if !task.instructions.isEmpty {
                    Text(task.instructions)
                }
                Label("\(task.minutesPerDay) minutes, \(task.daysPerWeek) days a week", systemImage: "clock")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                if let link = task.mediaURL.flatMap(URL.init(string:)) {
                    Link(destination: link) {
                        Label("Watch the demo", systemImage: "play.circle")
                    }
                }
            }

            if !task.words.isEmpty {
                Section("Practice words") {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 10)], spacing: 10) {
                        ForEach(task.words, id: \.self) { word in
                            Text(word)
                                .font(.title3.weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 64)
                                .padding(.horizontal, 6)
                                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                        }
                    }
                    .padding(.vertical, 4)
                }
            }

            Section {
                HStack(spacing: 10) {
                    ForEach(Rating.allCases) { option in
                        RatingButton(option: option, isSelected: rating == option) {
                            rating = option
                        }
                    }
                }
                .padding(.vertical, 4)

                TextField("Anything to tell your therapist? (optional)", text: $note, axis: .vertical)
                    .lineLimit(2...5)

                Button(action: save) {
                    HStack {
                        Text(todaysLog == nil ? "Save today's practice" : "Update today's practice")
                        if isSaving {
                            Spacer()
                            ProgressView()
                        }
                    }
                }
                .disabled(rating == nil || isSaving)

                if todaysLog != nil {
                    Button("Undo today's practice", role: .destructive, action: undo)
                        .disabled(isSaving)
                }
            } header: {
                Text("How did it go today?")
            } footer: {
                if let errorMessage {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }

            Section("This week") {
                WeekDots(weekStart: model.weekStart, logs: model.logs(for: task))
                    .padding(.vertical, 4)
            }
        }
        .navigationTitle(task.title)
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            rating = todaysLog?.rating
            note = todaysLog?.note ?? ""
        }
    }

    private func save() {
        guard let rating else { return }
        run { try await model.logToday(task, rating: rating, note: note) }
    }

    private func undo() {
        run {
            try await model.removeTodaysLog(for: task)
            rating = nil
            note = ""
        }
    }

    private func run(_ work: @escaping () async throws -> Void) {
        isSaving = true
        errorMessage = nil
        Task {
            defer { isSaving = false }
            do {
                try await work()
            } catch {
                errorMessage = "Couldn't save. \(error.localizedDescription)"
            }
        }
    }
}

private struct RatingButton: View {
    let option: Rating
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: option.symbol)
                    .font(.title2)
                Text(option.label)
                    .font(.subheadline.weight(.medium))
            }
            .frame(maxWidth: .infinity, minHeight: 64)
            .foregroundStyle(isSelected ? Color.white : option.color)
            .background(
                isSelected ? option.color : option.color.opacity(0.12),
                in: RoundedRectangle(cornerRadius: 12)
            )
        }
        // Plain style so each button in the row is tappable on its own inside a List.
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}
