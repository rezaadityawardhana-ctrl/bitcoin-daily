# Bitcoin Daily

A daily, low-noise Bitcoin dashboard and email for long-term holders:

- **Cycle score (0–100)**: average of six cycle indicators (MVRV Z-score, Mayer Multiple, price ÷ 200-week MA,
  Pi Cycle ratio, Puell Multiple, weekly RSI). It maps to zones: Strong accumulation / Accumulate / Hold /
  Scale out / Overheated, each with a playbook line.
- **Track record**: forward 1-year returns by score band since 2014, plus the score at past cycle tops and bottoms.
- **Today's brief**: news from tiered sources (official → research → outlets), with noise removed and duplicates
  merged. With an Anthropic key, Claude writes a neutral, cited summary: what happened, why it matters,
  and a bull and a bear reading.
- **Macro & network**: Fed funds rate, 10-year yield, dollar index (FRED) and hashrate.

Only Python 3.10+ is required. Everything except the AI brief uses the standard library.

## Quick start

```bash
cd btc-daily
cp .env.example .env              # then fill in what you want (all optional)
python3 run_daily.py --no-email --open
```

## Daily iPhone notification + dashboard link (recommended)

Every morning GitHub's cloud builds the dashboard, publishes it to a web page
(GitHub Pages), and pushes a notification to your iPhone. Tap it to open the dashboard. Your Mac can be off.

**1. iPhone (2 minutes)**
- Install **ntfy** from the App Store, allow notifications, tap **+** and subscribe to the topic in your
  `.env` (`NTFY_TOPIC`). Keep the default server, ntfy.sh.

**2. GitHub (one time)**
1. Sign in at github.com and create a new **public** repository, e.g. `bitcoin-daily`. GitHub Pages is
   free for public repos. Your keys never go into the repo: they live in Secrets, and `.env` is git-ignored.
2. Push this folder (`Documents/bitcoin-daily`, the one containing `.github/`):
   ```bash
   cd ~/Documents/bitcoin-daily
   git commit -m "Bitcoin Daily"
   git remote add origin https://github.com/<your-username>/bitcoin-daily.git
   git push -u origin main
   ```
3. Repo → **Settings → Pages** → Source: **GitHub Actions**.
4. Repo → **Settings → Secrets and variables → Actions** → add `NTFY_TOPIC` (same value as `.env`),
   plus optionally `ANTHROPIC_API_KEY` and `FRED_API_KEY`.
5. Repo → **Actions → Bitcoin Daily → Run workflow** to test it now. After that it runs daily at about 06:45 CET.

**3. Make it feel like an app.** Open the dashboard link in Safari → Share → **Add to Home Screen**.

The page address is `https://<your-username>.github.io/bitcoin-daily/`. Anyone with the link can view it (it holds only
public market data and news); search engines are asked not to index it.

## Turn on the extras

| Feature | What to put in `.env` (and in GitHub Secrets for the cloud run) |
|---|---|
| AI-analysed brief | `ANTHROPIC_API_KEY=…` and `pip3 install anthropic` (about a cent per day) |
| Macro tiles | `FRED_API_KEY=…` (free: https://fred.stlouisfed.org/docs/api/api_key.html) |
| Phone notification | `NTFY_TOPIC=…` (and `DASHBOARD_URL=…` for local runs) |
| Daily email (optional) | `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` (see below) |

### Email via Gmail (optional)
1. Turn on 2-Step Verification for your Google account.
2. Create an **App Password** at https://myaccount.google.com/apppasswords (name it "BTC Daily").
3. Put your Gmail address in `SMTP_USER` and `EMAIL_TO`, and the 16-character app password in `SMTP_PASSWORD`.
4. Test it with `python3 run_daily.py`.

The email is a lightweight summary that renders in Gmail, Outlook and Apple Mail. The full interactive
dashboard is attached as `dashboard.html`.

## Alternative: run it on this Mac instead of GitHub

```bash
./install_schedule.sh            # daily at 07:00 via macOS launchd
./install_schedule.sh --remove   # undo
```

The Mac must be on: if it's asleep at 07:00, the job runs when it wakes. A local run can still notify
your phone, but the dashboard link only works on the iPhone if the page is hosted (the GitHub setup above).

## Tuning
- `indicators.py` → `SCORE_MAPS` holds the breakpoints for each indicator, and `ZONES` holds the zone cut-offs and playbook text.
- `news.py` → `FEEDS` lists the sources and tiers, `NOISE` lists the headline patterns that get dropped, and `CATEGORIES` sets topic weights.

## Limits
- Exit signals are the weak side. The 2021 and 2025 tops scored only about 60 and 48 because each cycle's
  peak has been less extreme, so use the score as a guide alongside a pre-planned scale-out schedule.
- On-chain data is daily (yesterday's close). The price card uses the live Coinbase spot price.
- Glassnode's research feed blocks scripted readers, so it isn't included.
- Rule-based signals from public data, not financial advice.
