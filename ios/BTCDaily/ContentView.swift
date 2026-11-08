import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: DashboardStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var showSettings = false
    @State private var showSplash = true
    @State private var pageLoaded = false
    @State private var minSplashDone = false

    var body: some View {
        ZStack(alignment: .bottom) {
            BTCBackground(intensity: store.html == nil ? 1.0 : 0.8)

            if let html = store.html {
                DashboardWebView(html: html, baseURL: store.baseURL, onRefresh: { await store.refresh() },
                                 onLoaded: { pageLoaded = true; hideSplashIfReady() })
                    .ignoresSafeArea(edges: .bottom)
            } else {
                EmptyStateView(showSettings: $showSettings)
            }

            StatusPill(showSettings: $showSettings)
                .padding(.bottom, 8)

            if showSplash {
                SplashView().transition(.opacity).zIndex(1)
            }
        }
        .task {
            async let load: Void = store.refresh()
            try? await Task.sleep(for: .seconds(1.2))
            minSplashDone = true
            hideSplashIfReady()
            _ = await load
            hideSplashIfReady()
            try? await Task.sleep(for: .seconds(5))  // never keep the splash longer than ~6 s
            withAnimation(.easeOut(duration: 0.45)) { showSplash = false }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await store.refresh() } }
        }
        .sheet(isPresented: $showSettings) { SettingsView() }
    }

    /// Hide the splash once it has shown briefly AND there is something to show (page drawn, or nothing to load).
    private func hideSplashIfReady() {
        guard showSplash, minSplashDone else { return }
        let nothingToLoad: Bool = { if case .empty = store.status { return true }; return false }()
        if pageLoaded || nothingToLoad {
            withAnimation(.easeOut(duration: 0.45)) { showSplash = false }
        }
    }
}

/// Small floating pill: when the data is from, whether it's live, and a settings button.
private struct StatusPill: View {
    @EnvironmentObject private var store: DashboardStore
    @Binding var showSettings: Bool
    @State private var collapsed = false

    var body: some View {
        Group {
            if collapsed {
                // after a few seconds of live data, shrink to a small corner button so it doesn't cover the page
                Button { showSettings = true } label: {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "bitcoinsign").font(.body.weight(.bold)).foregroundStyle(.orange)
                            .frame(width: 44, height: 44)
                        Circle().fill(dotColor).frame(width: 9, height: 9).offset(x: -8, y: 8)
                    }
                }
                .accessibilityLabel("Settings. Status: \(label)")
                .background(.ultraThinMaterial, in: Circle())
                .overlay(Circle().strokeBorder(.orange.opacity(0.5)))
            } else {
                HStack(spacing: 10) {
                    Circle().fill(dotColor).frame(width: 8, height: 8)
                    Text(label).font(.footnote.weight(.medium)).lineLimit(1)
                    if case .offline = store.status {
                        Button { Task { await store.refresh() } } label: {
                            Image(systemName: "arrow.clockwise").font(.footnote.weight(.semibold))
                        }
                        .accessibilityLabel("Try again")
                    }
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape").font(.footnote.weight(.semibold))
                    }
                    .accessibilityLabel("Settings")
                }
                .padding(.horizontal, 14).padding(.vertical, 8)
                .background(.ultraThinMaterial, in: Capsule())
                .overlay(Capsule().strokeBorder(LinearGradient(colors: [.orange.opacity(0.55), .white.opacity(0.10)],
                                                               startPoint: .leading, endPoint: .trailing)))
            }
        }
        .foregroundStyle(.white)
        .shadow(color: .black.opacity(0.35), radius: 10, y: 4)
        .frame(maxWidth: .infinity, alignment: collapsed ? .trailing : .center)
        .padding(.horizontal, 18)
        .task(id: "\(store.status)-\(collapsed)") {
            guard !collapsed else { return }
            try? await Task.sleep(for: .seconds(3.5))
            if case .live = store.status, !Task.isCancelled {
                withAnimation(.spring(response: 0.45)) { collapsed = true }
            }
        }
    }

    private var dotColor: Color {
        switch store.status {
        case .live: return .green
        case .loading: return .gray
        case .offline: return .orange
        case .empty: return .red
        }
    }

    private var label: String {
        let time = store.lastUpdated.map { $0.formatted(.relative(presentation: .named)) } ?? ""
        switch store.status {
        case .loading: return "Loading…"
        case .live: return "Live · updated \(time)"
        case .offline: return time.isEmpty ? "Offline copy" : "Offline copy · \(time)"
        case .empty: return "Not connected"
        }
    }
}

private struct EmptyStateView: View {
    @EnvironmentObject private var store: DashboardStore
    @Binding var showSettings: Bool

    var body: some View {
        VStack(spacing: 16) {
            Text("₿")
                .font(.system(size: 44, weight: .heavy))
                .foregroundStyle(Color(red: 0.10, green: 0.07, blue: 0.02))
                .frame(width: 84, height: 84)
                .background(LinearGradient(colors: [Color(red: 1, green: 0.71, blue: 0.29), Color(red: 0.97, green: 0.58, blue: 0.10)],
                                           startPoint: .topLeading, endPoint: .bottomTrailing),
                            in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            Text("Bitcoin Daily").font(.title2.bold()).foregroundStyle(.white)
            if case .loading = store.status {
                ProgressView().tint(.white)
            } else {
                Text(reason)
                    .font(.subheadline).foregroundStyle(.white.opacity(0.7))
                    .multilineTextAlignment(.center).padding(.horizontal, 32)
                HStack {
                    Button("Try again") { Task { await store.refresh() } }.buttonStyle(.borderedProminent).tint(.orange)
                    Button("Server address") { showSettings = true }.buttonStyle(.bordered).tint(.white)
                }
            }
        }
    }

    private var reason: String {
        if case .empty(let r) = store.status { return r + "\n\nAfter the first load, the app keeps a copy for when you're away." }
        return ""
    }
}

private struct SettingsView: View {
    @EnvironmentObject private var store: DashboardStore
    @EnvironmentObject private var notif: NotificationManager
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Summary notification", isOn: Binding(
                        get: { notif.enabled },
                        set: { on in if on { Task { await notif.enable() } } else { notif.enabled = false } }))
                        .tint(.orange)
                    if notif.enabled {
                        Picker("Frequency", selection: $notif.frequency) {
                            ForEach(NotificationManager.Frequency.allCases) { Text($0.label).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        if notif.frequency == .weekly {
                            Picker("Day", selection: $notif.weekday) {
                                ForEach(1...7, id: \.self) { d in
                                    Text(Calendar.current.weekdaySymbols[d - 1]).tag(d)
                                }
                            }
                        }
                        DatePicker("Time", selection: Binding(get: { notif.time }, set: { notif.time = $0 }),
                                   displayedComponents: .hourAndMinute)
                        Button("Send a test notification") { Task { await notif.sendTest() } }
                    }
                } header: {
                    Text("Notifications")
                } footer: {
                    if notif.permissionDenied {
                        Text("Notifications are blocked for BTC Daily. Allow them in iPhone Settings › Notifications › BTC Daily.")
                    } else if notif.enabled {
                        Text("\(notif.scheduleDescription). Shows the latest price, cycle score, mood and action. The text updates each time the app gets new data from your Mac, so it's as fresh as the last update.")
                    } else {
                        Text("Get the summary on your lock screen, daily or weekly, at a time you choose.")
                    }
                }

                Section {
                    TextField("http://your-mac.local:8765/", text: $draft)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                } header: {
                    Text("Dashboard server")
                } footer: {
                    Text("The Mac that builds the dashboard serves it on your Wi-Fi. Default: \(DashboardStore.defaultServer)")
                }
                Section {
                    LabeledContent("Status", value: statusText)
                    if let d = store.lastUpdated {
                        LabeledContent("Saved copy from", value: d.formatted(date: .abbreviated, time: .shortened))
                    }
                }
                Section {
                    Button("Reset to default") { draft = DashboardStore.defaultServer }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        store.serverAddress = draft
                        dismiss()
                        Task { await store.refresh() }
                    }
                }
            }
            .onAppear { draft = store.serverAddress }
        }
    }

    private var statusText: String {
        switch store.status {
        case .live: return "Connected"
        case .loading: return "Loading"
        case .offline: return "Offline (saved copy)"
        case .empty: return "Not connected"
        }
    }
}
