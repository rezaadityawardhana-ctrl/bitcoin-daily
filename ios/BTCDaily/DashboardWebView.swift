import SwiftUI
import WebKit

/// Shows the dashboard HTML. Pull down to refresh; news links open in Safari.
struct DashboardWebView: UIViewRepresentable {
    let html: String
    let baseURL: URL?
    let onRefresh: () async -> Void
    var onLoaded: () -> Void = {}

    func makeCoordinator() -> Coordinator { Coordinator(onRefresh: onRefresh) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        // Let the animated bitcoin background show through the page behind the cards.
        let css = "html,body{background:transparent!important;background-image:none!important}"
        let js = "var s=document.createElement('style');s.textContent='\(css)';document.documentElement.appendChild(s);" +
                 "document.documentElement.classList.add('in-app');"
        config.userContentController.addUserScript(WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.contentInsetAdjustmentBehavior = .always

        let refresh = UIRefreshControl()
        refresh.tintColor = UIColor(red: 0.97, green: 0.58, blue: 0.10, alpha: 1)
        refresh.addTarget(context.coordinator, action: #selector(Coordinator.pulled(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refresh
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.onRefresh = onRefresh
        context.coordinator.onLoaded = onLoaded
        guard context.coordinator.loadedHTML != html else { return }
        context.coordinator.loadedHTML = html
        webView.loadHTMLString(html, baseURL: baseURL)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var onRefresh: () async -> Void
        var onLoaded: () -> Void = {}
        var loadedHTML: String?

        var userScrolled = false  // set once the user pulls to refresh, so their position is kept afterwards

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            // On launch the saved copy loads first, then the fresh one: always start at the top unless the user is
            // refreshing in place.
            if !userScrolled {
                let sv = webView.scrollView
                sv.setContentOffset(CGPoint(x: 0, y: -sv.adjustedContentInset.top), animated: false)
            }
            // give WebKit a moment to paint the first frame before revealing it
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [onLoaded] in onLoaded() }
        }

        init(onRefresh: @escaping () async -> Void) { self.onRefresh = onRefresh }

        @objc func pulled(_ control: UIRefreshControl) {
            userScrolled = true
            Task { @MainActor in
                await onRefresh()
                control.endRefreshing()
            }
        }

        // Links that leave the page (news sources) open in Safari; in-page anchors stay here.
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if action.navigationType == .linkActivated, let url = action.request.url,
               url.fragment == nil || url.host != webView.url?.host {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        // target="_blank" links
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url { UIApplication.shared.open(url) }
            return nil
        }
    }
}
