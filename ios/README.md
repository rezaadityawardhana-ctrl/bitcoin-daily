# BTC Daily: iPhone app

A native SwiftUI app that shows the Bitcoin Daily dashboard your Mac builds every morning.

- Loads the dashboard from the Mac over your Wi-Fi (`http://Rezas-MacBook-Air.local:8765/`).
- Keeps the last copy on the phone, so it still opens away from home and shows when that copy is from.
- Pull down to refresh. It also refreshes each time you open the app.
- News links open in Safari. The server address can be changed under the ⚙︎ button.

The Mac side must be installed and running (`btc-daily/install_schedule.sh`).

## Notifications
Tap the ₿ button (bottom-right) to open **Settings**, then turn on **Summary notification**:
- **Daily** or **Weekly** (pick the day), at the **time** you choose.
- Shows the latest price, cycle score, mood, ETF flows and exit-signal status. Tapping it opens the app.
- **Send a test notification** fires one in 5 seconds.

iOS shows local notifications on schedule even when the app is closed, but their text is set in advance. The app updates
the text every time it gets fresh data from your Mac, and asks iOS for a background refresh shortly before each
notification. iOS decides whether that runs, so the text is as fresh as the app's last update.

## Requirements
- Xcode 16 or newer (free, Mac App Store). Open it once after installing so it finishes setup.
- iPhone on iOS 17 or newer.

## Run it in the Simulator
1. Open `ios/BTCDaily.xcodeproj` in Xcode.
2. Pick an iPhone simulator at the top, then press ▶ (Run).

## Install it on your iPhone (free Apple ID)
1. **Xcode → Settings → Accounts → +** and sign in with your Apple ID.
2. In the project, select the **BTCDaily** target → **Signing & Capabilities** → **Team**: choose your Apple ID
   (shown as "Personal Team"). If Xcode says the bundle ID is taken, change `com.rezaawardhana.btcdaily` to something unique.
3. Connect the iPhone with a cable and unlock it. Tap **Trust** on the phone.
4. On the iPhone, turn on **Settings → Privacy & Security → Developer Mode** (it restarts the phone).
5. Pick your iPhone at the top of Xcode and press ▶.
6. The first time, on the iPhone go to **Settings → General → VPN & Device Management**, tap your Apple ID and **Trust**.
7. Open BTC Daily. When it asks to find devices on your **local network**, tap **Allow**. Otherwise it can't reach the Mac.

**Free Apple ID limit:** the app stops opening after 7 days. Reconnect the phone and press ▶ in Xcode again to renew it.
A paid Apple Developer Program membership ($99/year) makes it last a year.

## Away from home
The app shows the last copy it downloaded. To get live data away from home, install Tailscale on the Mac and iPhone, then
set the server address in the app's ⚙︎ settings to the Mac's Tailscale IP, e.g. `http://100.x.y.z:8765/`.
Tailscale IP addresses are allowed by the app's local-network setting.

## Files
- `BTCDaily/` holds the SwiftUI source and the app icon (`Assets.xcassets`).
- `BTCDaily-Info.plist` allows plain-http access to the Mac on the local network.
- `tools/make_icon.swift` regenerates the icon:
  `swift ios/tools/make_icon.swift ios/BTCDaily/Assets.xcassets/AppIcon.appiconset/AppIcon.png`
