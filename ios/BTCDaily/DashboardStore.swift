import Foundation

/// Downloads the dashboard page from the Mac that builds it, and keeps the last good copy on the
/// phone so the app still opens (with yesterday's numbers) when the Mac can't be reached.
@MainActor
final class DashboardStore: ObservableObject {
    enum Status: Equatable {
        case loading
        case live            // fresh copy from the Mac
        case offline(String) // showing the saved copy; reason
        case empty(String)   // nothing saved yet; reason
    }

    nonisolated static let defaultServer = "http://Rezas-MacBook-Air.local:8765/"

    @Published private(set) var html: String?
    @Published private(set) var lastUpdated: Date?
    @Published private(set) var status: Status = .loading
    @Published var serverAddress: String {
        didSet { UserDefaults.standard.set(serverAddress, forKey: "serverAddress") }
    }

    private let cacheFile: URL = {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("dashboard.html")
    }()

    private var isRefreshing = false

    init() {
        serverAddress = UserDefaults.standard.string(forKey: "serverAddress") ?? Self.defaultServer
        if let saved = try? String(contentsOf: cacheFile, encoding: .utf8) {
            html = saved
            lastUpdated = UserDefaults.standard.object(forKey: "lastUpdated") as? Date
            status = .offline("Checking for a newer copy…")
        }
    }

    /// Base URL for the web view, so in-page links such as #record resolve.
    var baseURL: URL? { URL(string: normalizedServer) }

    private var normalizedServer: String {
        var s = serverAddress.trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.lowercased().hasPrefix("http://") && !s.lowercased().hasPrefix("https://") { s = "http://" + s }
        if !s.hasSuffix("/") { s += "/" }
        return s
    }

    func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        if html == nil { status = .loading }

        guard let url = URL(string: normalizedServer) else {
            fail("The server address isn't a valid web address.")
            return
        }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 8)
        request.setValue("BTCDaily-iOS", forHTTPHeaderField: "User-Agent")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200,
                  let page = String(data: data, encoding: .utf8), page.contains("Bitcoin Daily") else {
                fail("The Mac answered, but not with the dashboard.")
                return
            }
            html = page
            lastUpdated = Date()
            status = .live
            try? page.write(to: cacheFile, atomically: true, encoding: .utf8)
            _ = await NotificationManager.fetchSummary(server: url)
            UserDefaults.standard.set(lastUpdated, forKey: "lastUpdated")
        } catch {
            fail("Can't reach your Mac. Connect to the same Wi-Fi and make sure the Mac is awake.")
        }
    }

    private func fail(_ reason: String) {
        status = html == nil ? .empty(reason) : .offline(reason)
    }
}
