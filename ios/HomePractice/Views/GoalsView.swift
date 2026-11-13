import SwiftUI

/// What the child is working towards, plus the therapist's latest summary.
struct GoalsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            Group {
                if !model.hasLoaded {
                    ProgressView()
                } else if model.goals.isEmpty && model.latestSummary == nil {
                    EmptyState(
                        symbol: "flag",
                        title: "No goals yet",
                        message: "Goals your therapist sets will show up here."
                    )
                } else {
                    List {
                        if let summary = model.latestSummary {
                            Section("From your therapist") {
                                Text(summary.parentSummary)
                            }
                        }
                        goalSection("Working on now", status: "active", symbol: "target")
                        goalSection("Up next", status: "next", symbol: "arrow.right.circle")
                        goalSection("Achieved", status: "achieved", symbol: "star.fill")
                    }
                }
            }
            .navigationTitle("Goals")
            .toolbar {
                if model.children.count > 1 {
                    ToolbarItem(placement: .topBarTrailing) { ChildPicker() }
                }
            }
            .refreshable { await model.refresh() }
        }
    }

    @ViewBuilder
    private func goalSection(_ title: String, status: String, symbol: String) -> some View {
        let goals = model.goals.filter { $0.status == status }
        if !goals.isEmpty {
            Section(title) {
                ForEach(goals) { goal in
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(goal.title)
                            if !goal.detail.isEmpty {
                                Text(goal.detail)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    } icon: {
                        Image(systemName: symbol)
                    }
                }
            }
        }
    }
}
