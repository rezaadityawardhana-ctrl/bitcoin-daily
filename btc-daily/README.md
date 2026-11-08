# Bitcoin Daily

A daily, low-noise Bitcoin dashboard and email for long-term holders:

- **Cycle score (0–100)**: average of six cycle indicators (MVRV Z-score, Mayer Multiple, price ÷ 200-week MA,
  Pi Cycle ratio, Puell Multiple, weekly RSI). It maps to zones: Strong accumulation / Accumulate / Hold /
  Scale out / Overheated, each with a playbook line.
- **Track record**: forward 1-year returns by score band since 2014, plus the score at past cycle tops and bottoms.
- **Today's brief**: news from tiered sources (official → research → outlets), with noise removed and duplicates
  merged. With an Anthropic key, Claude writes a neutral, cited summary: what happened, why it matters,
  and a bull and a bear reading.
- **Macro & network**: Fed funds rate (New York Fed), 10-year yield (US Treasury), dollar index (ECB rates) and hashrate. No API keys needed.

Only Python 3.10+ is required. Everything except the AI brief uses the standard library.

## Quick start

```bash
cd btc-daily
cp .env.example .env              # then fill in what you want (all optional)
python3 run_daily.py --no-email --open
```

## Open it anywhere from your phone (GitHub Pages web app)

GitHub's servers build the dashboard every morning (~06:45 CET) and evening (~17:45 CET) and publish it at
`https://<your-username>.github.io/bitcoin-daily/`. Your Mac can be off.

On the iPhone, open that link in **Safari → Share → Add to Home Screen**. It then opens like the app: ₿ icon, full screen,
dark animated bitcoin background, splash, live price on every open, and the last copy when you have no signal.
Add `?app=1` to the address to preview app mode in a desktop browser.

The page is public to anyone with the link (market data only) and asks search engines not to index it.

## Daily iPhone notification + dashboard link (runs on this Mac)

Every day at 07:00 the Mac builds the dashboard and pushes a notification to your iPhone. Tapping it opens
the dashboard, served by a small always-on web server on this Mac.

**1. iPhone:** install **ntfy** from the App Store, allow notifications, tap **+** and subscribe to the topic in
`.env` (`NTFY_TOPIC`). Keep the default server, ntfy.sh.

**2. Mac:**
```bash
./install_schedule.sh            # daily run at 07:00 + dashboard server on port 8765
./install_schedule.sh --remove   # undo both
launchctl kickstart gui/$(id -u)/com.btcdaily.dashboard   # run it right now
```
The installer sets `DASHBOARD_URL` in `.env` to `http://<your-mac-name>.local:8765/`. Logs are in `~/Library/Logs/BitcoinDaily/`.

**3. Make it feel like an app.** Open the link in Safari on the iPhone → Share → **Add to Home Screen**.

**What to know**
- The link opens when your iPhone is on the **same Wi-Fi as the Mac** and the Mac is **awake**. The notification
  text itself (score, zone, action, top news) arrives anywhere.
- To open the link away from home, install **Tailscale** (free) on the Mac and iPhone, then set `DASHBOARD_URL`
  in `.env` to `http://<mac-tailscale-name>:8765/`.
- If the Mac is asleep at 07:00, the run happens when it wakes (it waits up to 5 minutes for Wi-Fi). To have it ready
  on time, schedule a wake in System Settings → Battery → Options, or run `sudo pmset repeat wake MTWRFSU 06:55:00`.
- The first time, macOS may ask whether Python may accept incoming network connections. Choose **Allow**, or the
  iPhone can't reach the page.

## Turn on the extras

| Feature | What to put in `.env` |
|---|---|
| AI-analysed brief | `ANTHROPIC_API_KEY=…` and `pip3 install anthropic` (about a cent per day) |
| Phone notification | `NTFY_TOPIC=…` (`DASHBOARD_URL` is set by the installer) |
| Daily email (optional) | `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` (see below) |

### Email via Gmail (optional)
1. Turn on 2-Step Verification for your Google account.
2. Create an **App Password** at https://myaccount.google.com/apppasswords (name it "BTC Daily").
3. Put your Gmail address in `SMTP_USER` and `EMAIL_TO`, and the 16-character app password in `SMTP_PASSWORD`.
4. Test it with `python3 run_daily.py`.

The email is a lightweight summary that renders in Gmail, Outlook and Apple Mail. The full interactive
dashboard is attached as `dashboard.html`.

## Alternative: run it in the cloud (GitHub)

`.github/workflows/daily.yml` (in the parent folder) builds the dashboard in GitHub's cloud each morning, publishes
it with GitHub Pages and sends the notification, so the link works anywhere even with the Mac off. To use it:
create a public GitHub repo, push this folder, set **Settings → Pages → Source: GitHub Actions**, and add
`NTFY_TOPIC` (plus optional `ANTHROPIC_API_KEY`) under **Settings → Secrets and variables → Actions**.
Then remove the Mac schedule with `./install_schedule.sh --remove` so you don't get two notifications.

## Tuning
- `indicators.py` → `SCORE_MAPS` holds the breakpoints for each indicator, and `ZONES` holds the zone cut-offs and playbook text.
- `news.py` → `FEEDS` lists the sources and tiers, `NOISE` lists the headline patterns that get dropped, and `CATEGORIES` sets topic weights.

## Limits
- Exit signals are the weak side. The 2021 and 2025 tops scored only about 60 and 48 because each cycle's
  peak has been less extreme, so use the score as a guide alongside a pre-planned scale-out schedule.
- On-chain data is daily (yesterday's close). The price card uses the live Coinbase spot price.
- Glassnode's research feed blocks scripted readers, so it isn't included.
- Rule-based signals from public data, not financial advice.
