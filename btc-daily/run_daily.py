"""Build today's Bitcoin dashboard and (optionally) email it.

    python3 run_daily.py              # build dashboard + email preview, send if SMTP is configured
    python3 run_daily.py --no-email   # build only
    python3 run_daily.py --open       # build and open the dashboard in your browser
"""
import argparse
import json
import os
import webbrowser
from datetime import datetime

import indicators
import market
import flows as flows_mod
import news as news_mod
import sentiment
import ta
import render
from common import OUTPUT_DIR, load_env, wait_for_network


def plain_text(cycle, news, brief, spot) -> str:
    lines = [
        f"Bitcoin Daily — data as of {cycle['as_of']}",
        f"Cycle score: {cycle['score']:.0f}/100 — {cycle['zone']['label']}",
        cycle["zone"]["playbook"], "",
        f"Price: ${cycle['price_close']:,.0f}  ({cycle['change_30d'] * 100:+.1f}% over 30 days)",
        f"From all-time high: {cycle['ath']['drawdown'] * 100:.0f}%", "",
    ]
    summ = render.brief_summary(cycle, news, brief, spot)
    lines += ["TODAY IN 30 SECONDS"] + [f"* {p}" for p in summ["news"]] + [""]
    overview, items, _ = render.news_items(cycle, news, brief)
    if overview:
        lines += [overview, ""]
    for it in items:
        lines += [f"- {it['headline']}", f"  {it['what_happened']}"]
        if it.get("why_it_matters"):
            lines.append(f"  Why it matters: {it['why_it_matters']}")
    lines += ["", "The full dashboard is attached. Rule-based signals, not financial advice."]
    return "\n".join(lines)


def notification_summary(cycle, news, brief, spot, market=None) -> dict:
    """Short text for the phone notification (also saved as output/summary.json)."""
    from indicators import zone_for
    summ = render.brief_summary(cycle, news, brief, spot)
    price = spot or cycle["price_close"]
    hist = cycle["history"]
    prev_zone = zone_for(hist[-2]["s"]) if len(hist) > 1 else cycle["zone"]
    zone_changed = prev_zone["key"] != cycle["zone"]["key"]
    ex = cycle["exit"]
    lines = []
    if ex["fired_recently"]:
        lines.append(f"EXIT SIGNAL: {ex['detail']}")
    elif ex["new_high_today"]:
        lines.append("New all-time high in the exit window: scale-out step.")
    if zone_changed:
        lines.append(f"Zone changed: {prev_zone['label']} → {cycle['zone']['label']}")
    lines.append(f"{render.pct(cycle['change_1d'])} 24h · {render.pct(cycle['change_30d'])} 30d · "
                 f"{abs(cycle['ath']['drawdown']) * 100:.0f}% below ATH")
    lines.append(render.playbook_action(cycle["zone"]))
    if market and market["mood"].get("value") is not None:
        etf = market["flows"].get("etf", {})
        flow = f' · ETFs {render.money(etf["sum_7d"])} 7d' if "sum_7d" in etf else ""
        lines.append(f'Mood: {market["mood"]["label"]} ({market["mood"]["value"]:.0f}/100){flow}')
    if not (ex["fired_recently"] or ex["new_high_today"]):
        lines.append(f"Exit signal: {ex['label']}")
    lines += [f"• {p}" for p in summ["news"]]
    priority = 5 if ex["fired_recently"] else 4 if (ex["new_high_today"] or zone_changed) else 3
    title_prefix = "EXIT SIGNAL · " if ex["fired_recently"] else "New ATH · " if ex["new_high_today"] else ""
    return {
        "date": cycle["as_of"], "zone_key": cycle["zone"]["key"], "zone_changed": zone_changed,
        "priority": priority, "exit_status": ex["status"],
        "title": f"{title_prefix}BTC {render.usd(price)} · Score {cycle['score']:.0f} · {cycle['zone']['label']}",
        "message": "\n".join(lines),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true", help="don't send the email even if SMTP is configured")
    ap.add_argument("--no-notify", action="store_true", help="don't send the phone notification")
    ap.add_argument("--open", action="store_true", help="open the dashboard in your browser")
    args = ap.parse_args()

    load_env()
    print(f"=== {datetime.now():%Y-%m-%d %H:%M} ===")
    if not wait_for_network():
        raise SystemExit("No internet connection after 5 minutes; giving up for today.")
    print("Fetching market data…")
    rows = market.fetch_coinmetrics()
    spot = market.fetch_spot()
    macro = market.fetch_macro()
    cycle = indicators.compute(rows)
    print(f"Cycle score {cycle['score']:.1f} ({cycle['zone']['label']})")

    print("Gathering news, flows and sentiment…")
    news = news_mod.gather()
    flows = flows_mod.gather()
    for st in news["top"]:
        st["tone"], st["tone_score"] = sentiment.story_tone(f'{st["title"]} {st["summary"]}')
        st["flags"] = sentiment.agenda_flags(st, flows)
    mood = sentiment.market_mood(news["top"], flows)
    brief = news_mod.summarize(news, cycle, flows, mood)
    market_view = {
        "mood": mood, "flows": flows,
        "interpretation": (brief.get("interpretation") if brief and brief.get("interpretation")
                           else sentiment.interpret(mood, cycle, flows, news["top"])),
        "interp_ai": bool(brief and brief.get("interpretation")),
        "chf": market.fetch_chf(),
        "ta": ta.build({"cycle_score": round(cycle["score"], 1), "cycle_zone": cycle["zone"]["label"],
                        "exit_signal": cycle["exit"]["label"], "market_mood": mood.get("label"),
                        "halving_months": round(cycle["halving"]["months_since"], 1)}),
    }
    if mood.get("value") is not None:
        print(f"Market mood {mood['value']:.0f} ({mood['label']})")
    print(f"{len(news['top'])} stories, {len(news['research'])} research items, AI brief: {'yes' if brief else 'no'}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    generated = datetime.now().strftime("%-d %b %Y %H:%M")
    dash = OUTPUT_DIR / "dashboard.html"
    dash.write_text(render.dashboard(cycle, news, brief, macro, spot, generated, market_view))
    mail_html = render.email_html(cycle, news, brief, spot, market_view)
    (OUTPUT_DIR / "email_preview.html").write_text(mail_html)
    # dated archive copy
    archive = OUTPUT_DIR / "archive"
    archive.mkdir(exist_ok=True)
    (archive / f"dashboard-{cycle['as_of']}.html").write_text(dash.read_text())
    (OUTPUT_DIR / "index.html").write_text(dash.read_text())  # what gets hosted
    import shutil
    for f in (OUTPUT_DIR.parent / "webapp").iterdir():  # manifest, icons, offline service worker
        shutil.copy(f, OUTPUT_DIR / f.name)
    summary = notification_summary(cycle, news, brief, spot, market_view)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Dashboard: {dash}")

    if not args.no_notify and os.environ.get("NTFY_TOPIC"):
        import notify
        notify.send(summary)
        print("Phone notification sent.")

    if not args.no_email and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        import mailer
        subject = f"BTC Daily · score {cycle['score']:.0f} · {cycle['zone']['label']} · {cycle['as_of']}"
        mailer.send(subject, mail_html, plain_text(cycle, news, brief, spot), dash)
        print(f"Email sent to {os.environ.get('EMAIL_TO', os.environ['SMTP_USER'])}")

    if args.open:
        webbrowser.open(dash.as_uri())


if __name__ == "__main__":
    main()
