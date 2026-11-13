import Foundation

/// Where the app's backend lives. Fill these in from your Supabase project
/// (Project Settings > API). The anon key is designed to ship inside apps;
/// row-level security in the database is what protects the data.
enum Config {
    static let supabaseURL = URL(string: "https://YOUR-PROJECT.supabase.co")!
    static let supabaseAnonKey = "YOUR-ANON-KEY"

    static var isConfigured: Bool {
        supabaseURL.host != "YOUR-PROJECT.supabase.co" && supabaseAnonKey != "YOUR-ANON-KEY"
    }
}
