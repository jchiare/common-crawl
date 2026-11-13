import SwiftUI

/// Email, then the code we emailed. No passwords.
struct SignInView: View {
    @Environment(AppModel.self) private var model

    @State private var email = ""
    @State private var code = ""
    @State private var codeSent = false
    @State private var isWorking = false
    @State private var errorMessage: String?
    @FocusState private var focus: Field?

    private enum Field { case email, code }

    var body: some View {
        NavigationStack {
            Form {
                if !Config.isConfigured {
                    Section {
                        Label(
                            "This build isn't connected to a backend yet. Set the Supabase URL and key in Config.swift.",
                            systemImage: "exclamationmark.triangle"
                        )
                        .font(.footnote)
                    }
                }

                if codeSent {
                    Section {
                        TextField("Code", text: $code)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .focused($focus, equals: .code)
                    } header: {
                        Text("Enter the code")
                    } footer: {
                        Text("We emailed a sign-in code to \(email).")
                    }
                } else {
                    Section {
                        TextField("Email", text: $email)
                            .keyboardType(.emailAddress)
                            .textContentType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .focused($focus, equals: .email)
                    } header: {
                        Text("Your email")
                    } footer: {
                        Text("Use the address your therapist invited.")
                    }
                }

                if let errorMessage {
                    Section {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            Text(codeSent ? "Sign in" : "Email me a code")
                            if isWorking {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(isWorking || !canSubmit)

                    if codeSent {
                        Button("Use a different email") {
                            codeSent = false
                            code = ""
                            errorMessage = nil
                            focus = .email
                        }
                        .disabled(isWorking)
                    }
                }
            }
            .navigationTitle("Home Practice")
            .onAppear { focus = .email }
        }
    }

    private var trimmedEmail: String {
        email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private var canSubmit: Bool {
        guard Config.isConfigured else { return false }
        return codeSent ? code.count >= 6 : trimmedEmail.contains("@")
    }

    private func submit() {
        isWorking = true
        errorMessage = nil
        Task {
            defer { isWorking = false }
            do {
                if codeSent {
                    try await model.verify(email: trimmedEmail, code: code)
                    // AppModel notices the new session and moves on.
                } else {
                    try await model.sendCode(to: trimmedEmail)
                    email = trimmedEmail
                    codeSent = true
                    focus = .code
                }
            } catch {
                errorMessage = codeSent
                    ? "That code didn't work. Check it and try again."
                    : "Couldn't send the code. \(error.localizedDescription)"
            }
        }
    }
}
