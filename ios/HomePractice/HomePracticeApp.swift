import SwiftUI

@main
struct HomePracticeApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task { await model.start() }
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            switch model.phase {
            case .loading:
                ProgressView()
            case .signedOut:
                SignInView()
            case .signedIn:
                MainView()
            }
        }
        .onChange(of: scenePhase) { _, phase in
            // Coming back to the app (possibly on a new day or week): reload.
            if phase == .active, model.phase == .signedIn, model.hasLoaded {
                Task { await model.refresh() }
            }
        }
    }
}

struct MainView: View {
    var body: some View {
        TabView {
            WeekView()
                .tabItem { Label("This week", systemImage: "checklist") }
            GoalsView()
                .tabItem { Label("Goals", systemImage: "flag") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
    }
}
