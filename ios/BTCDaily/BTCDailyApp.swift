import SwiftUI
import UserNotifications

@main
struct BTCDailyApp: App {
    @StateObject private var store = DashboardStore()
    @StateObject private var notifications = NotificationManager.shared
    private let presenter = ForegroundPresenter()

    init() {
        NotificationManager.registerBackgroundRefresh()
        UNUserNotificationCenter.current().delegate = presenter
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .environmentObject(notifications)
                .preferredColorScheme(.dark)
        }
    }
}

/// Shows the notification banner even when the app is open.
final class ForegroundPresenter: NSObject, UNUserNotificationCenterDelegate {
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async
        -> UNNotificationPresentationOptions { [.banner, .sound, .list] }
}
