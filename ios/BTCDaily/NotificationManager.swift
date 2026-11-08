import BackgroundTasks
import Foundation
import UserNotifications

/// Schedules the Bitcoin Daily reminder (daily or weekly, at a chosen time) as a local notification.
///
/// iOS fires local notifications on schedule even when the app is closed, but their text is fixed when scheduled.
/// So the text is refreshed with the latest summary from the Mac (`summary.json`) every time the app loads new data,
/// and a background refresh is requested shortly before each notification to do the same while the app is closed.
@MainActor
final class NotificationManager: ObservableObject {
    static let shared = NotificationManager()
    nonisolated static let requestID = "btc-daily-summary"
    nonisolated static let refreshTaskID = "com.rezaawardhana.btcdaily.refresh"

    enum Frequency: String, CaseIterable, Identifiable {
        case daily, weekly
        var id: String { rawValue }
        var label: String { self == .daily ? "Daily" : "Weekly" }
    }

    private let defaults = UserDefaults.standard

    @Published var enabled: Bool { didSet { defaults.set(enabled, forKey: "notif.enabled"); reschedule() } }
    @Published var frequency: Frequency { didSet { defaults.set(frequency.rawValue, forKey: "notif.frequency"); reschedule() } }
    /// 1 = Sunday … 7 = Saturday (Calendar weekday numbering)
    @Published var weekday: Int { didSet { defaults.set(weekday, forKey: "notif.weekday"); reschedule() } }
    /// time of day, stored as minutes after midnight
    @Published var minutes: Int { didSet { defaults.set(minutes, forKey: "notif.minutes"); reschedule() } }
    @Published private(set) var permissionDenied = false

    private init() {
        enabled = defaults.bool(forKey: "notif.enabled")
        frequency = Frequency(rawValue: defaults.string(forKey: "notif.frequency") ?? "") ?? .daily
        weekday = defaults.object(forKey: "notif.weekday") as? Int ?? 2  // Monday
        minutes = defaults.object(forKey: "notif.minutes") as? Int ?? (7 * 60 + 30)
    }

    /// Time as a Date (today), for the DatePicker.
    var time: Date {
        get { Calendar.current.date(bySettingHour: minutes / 60, minute: minutes % 60, second: 0, of: Date()) ?? Date() }
        set {
            let c = Calendar.current.dateComponents([.hour, .minute], from: newValue)
            minutes = (c.hour ?? 7) * 60 + (c.minute ?? 30)
        }
    }

    var scheduleDescription: String {
        let t = time.formatted(date: .omitted, time: .shortened)
        if frequency == .daily { return "Every day at \(t)" }
        let day = Calendar.current.weekdaySymbols[(weekday - 1) % 7]
        return "Every \(day) at \(t)"
    }

    // MARK: permission + scheduling

    /// Called when the user turns notifications on.
    func enable() async {
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        permissionDenied = !granted
        enabled = granted
    }

    func reschedule() {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: [Self.requestID])
        guard enabled else { return }

        let summary = Self.savedSummary()
        let content = UNMutableNotificationContent()
        content.title = summary?.title ?? "Bitcoin Daily"
        content.body = summary?.message ?? "Your Bitcoin brief is ready: cycle score, mood, flows and the chart."
        content.sound = .default
        content.threadIdentifier = "btc-daily"
        if summary?.priority ?? 3 >= 5 { content.interruptionLevel = .timeSensitive }

        var when = DateComponents()
        when.hour = minutes / 60
        when.minute = minutes % 60
        if frequency == .weekly { when.weekday = weekday }
        let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: true)
        center.add(UNNotificationRequest(identifier: Self.requestID, content: content, trigger: trigger))
        scheduleBackgroundRefresh(before: trigger.nextTriggerDate())
    }

    /// Fires the notification in 5 seconds so you can see what it looks like.
    func sendTest() async {
        if !enabled { await enable() }
        guard enabled else { return }
        let summary = Self.savedSummary()
        let content = UNMutableNotificationContent()
        content.title = summary?.title ?? "Bitcoin Daily"
        content.body = summary?.message ?? "Your Bitcoin brief is ready."
        content.sound = .default
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 5, repeats: false)
        try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "btc-daily-test", content: content, trigger: trigger))
    }

    // MARK: summary text (from the Mac)

    struct Summary: Codable {
        let title: String
        let message: String
        let priority: Int?
    }

    static func savedSummary() -> Summary? {
        guard let data = UserDefaults.standard.data(forKey: "notif.summary") else { return nil }
        return try? JSONDecoder().decode(Summary.self, from: data)
    }

    /// Downloads summary.json from the Mac and refreshes the scheduled notification's text.
    static func fetchSummary(server: URL) async -> Bool {
        var req = URLRequest(url: server.appendingPathComponent("summary.json"), cachePolicy: .reloadIgnoringLocalCacheData,
                             timeoutInterval: 8)
        req.setValue("BTCDaily-iOS", forHTTPHeaderField: "User-Agent")
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              (try? JSONDecoder().decode(Summary.self, from: data)) != nil else { return false }
        UserDefaults.standard.set(data, forKey: "notif.summary")
        await MainActor.run { NotificationManager.shared.reschedule() }
        return true
    }

    // MARK: background refresh

    private func scheduleBackgroundRefresh(before fire: Date?) {
        guard let fire else { return }
        let req = BGAppRefreshTaskRequest(identifier: Self.refreshTaskID)
        req.earliestBeginDate = max(Date().addingTimeInterval(15 * 60), fire.addingTimeInterval(-45 * 60))
        try? BGTaskScheduler.shared.submit(req)
    }

    /// Register once at launch. iOS decides when (and whether) to run it; when it runs, it refreshes the text.
    nonisolated static func registerBackgroundRefresh() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: refreshTaskID, using: nil) { task in
            let server = URL(string: UserDefaults.standard.string(forKey: "serverAddress") ?? DashboardStore.defaultServer)
            let work = Task {
                let ok = server != nil ? await fetchSummary(server: server!) : false
                task.setTaskCompleted(success: ok)
            }
            task.expirationHandler = { work.cancel() }
        }
    }
}
