"""Builds the dashboard page (dashboard.html) and the email body (email_preview.html)."""
import html
import json
import math
from datetime import datetime

from indicators import ZONES

ZONE_COLORS = {  # diverging: blue = cheap/accumulate, gray = neutral, red = expensive/take profit
    "strong-accumulate": "#2f6fd0", "accumulate": "#7fb2f0", "hold": "#a9a8a0",
    "scale-out": "#ee9e9d", "take-profit": "#e34948",
}
LABEL_TEXT = {"fact": "Fact", "report": "Single report", "analysis": "Analysis"}


# ---------------------------------------------------------------- formatting
def e(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def safe_link(url: str) -> str:
    return e(url) if str(url).startswith(("http://", "https://")) else "#"


def usd(v, digits=0) -> str:
    return "–" if v is None else f"${v:,.{digits}f}"


def pct(v, digits=1, sign=True) -> str:
    return "–" if v is None else f"{v * 100:{'+' if sign else ''}.{digits}f}%"


def clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def fmt_date(iso: str) -> str:
    return datetime.fromisoformat(iso[:10]).strftime("%-d %b %Y")


def delta(v, digits=1) -> str:
    if v is None:
        return ""
    up = v >= 0
    return f'<span class="delta {"up" if up else "down"}">{"▲" if up else "▼"} {abs(v) * 100:.{digits}f}%</span>'


def _zone_key(score):
    for upper, key, *_ in ZONES:
        if score < upper:
            return key
    return "take-profit"


def playbook_action(zone) -> str:
    action = zone["playbook"].split("Playbook: ")[-1]
    return action[:1].upper() + action[1:]


# ---------------------------------------------------------------- content
def news_items(cycle, news, brief):
    """Normalised news items: from the AI brief when present, else the filtered headlines."""
    stories = news["top"] + news["research"]
    if brief:
        items = []
        for it in brief["items"]:
            idx = it["story_index"]
            ok = 0 <= idx < len(stories)
            items.append({**it, "category": stories[idx]["category"] if ok else "",
                          "sources": stories[idx]["sources"] if ok else []})
        research = [{"takeaway": r["takeaway"], "story": stories[r["story_index"]]}
                    for r in brief["research_takeaways"] if 0 <= r["story_index"] < len(stories)]
        return brief["overview"], items, research
    items = [{
        "headline": s["title"], "what_happened": clip(s["summary"], 280), "why_it_matters": "",
        "label": "fact" if s["tier"] == 1 or s["corroborated"] else "report",
        "bull_view": "", "bear_view": "", "category": s["category"], "sources": s["sources"],
    } for s in news["top"]]
    research = [{"takeaway": clip(s["summary"], 240), "story": s} for s in news["research"]]
    return None, items, research


def brief_summary(cycle, news, brief, spot) -> dict:
    """'Today in 30 seconds': market + cycle lines (computed) and the news takeaways
    (Claude's key points when available, otherwise the lead story per top theme)."""
    price = spot or cycle["price_close"]
    market = (f'BTC is at {usd(price)}: {pct(cycle["change_30d"])} over 30 days and '
              f'{abs(cycle["ath"]["drawdown"]) * 100:.0f}% below its all-time high.')
    d30 = cycle["score"] - cycle["score_30d_ago"] if cycle["score_30d_ago"] is not None else None
    trend = "" if d30 is None else (" (flat over the month)" if abs(d30) < 1 else
                                    f' ({"up" if d30 > 0 else "down"} {abs(d30):.0f} points in a month)')
    score_line = (f'Cycle score {cycle["score"]:.0f}/100, {cycle["zone"]["label"]}{trend}. '
                  f'{playbook_action(cycle["zone"])}')

    if brief and brief.get("key_points"):
        news_points = brief["key_points"][:3]
    else:
        themes = {}
        for s in news["top"]:
            themes.setdefault(s["category"], []).append(s)
        news_points = []
        for cat, ss in list(themes.items())[:3]:
            more = f" (+{len(ss) - 1} more)" if len(ss) > 1 else ""
            news_points.append(f"{cat}: {ss[0]['title']}{more}")
    if not news_points:
        news_points = ["A quiet news day: nothing material passed the filters."]
    return {"market": market, "score": score_line, "news": news_points}


# ---------------------------------------------------------------- dashboard parts
def gauge_svg(score: float) -> str:
    w, r, stroke = 260, 104, 14
    cx, cy = w / 2, r + 14
    parts, lo = [], 0
    gap = math.radians(1.2)
    for upper, key, label, _ in ZONES:
        hi = min(upper, 100)
        a0 = math.pi * (1 - lo / 100) - (gap if lo > 0 else 0)
        a1 = math.pi * (1 - hi / 100) + (gap if hi < 100 else 0)
        x0, y0 = cx + r * math.cos(a0), cy - r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
        parts.append(f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 1 {x1:.1f} {y1:.1f}" stroke="{ZONE_COLORS[key]}" '
                     f'stroke-width="{stroke}" fill="none"><title>{e(label)} ({lo}–{hi})</title></path>')
        lo = hi
    a = math.pi * (1 - score / 100)
    mx, my = cx + r * math.cos(a), cy - r * math.sin(a)
    parts.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="10" fill="#f3f2ee" stroke="#101113" stroke-width="4"/>')
    parts.append(f'<text x="{cx}" y="{cy - 14}" text-anchor="middle" class="g-num">{score:.0f}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 8}" text-anchor="middle" class="g-of">out of 100</text>')
    parts.append(f'<text x="{cx - r}" y="{cy + 22}" text-anchor="middle" class="g-end">0</text>'
                 f'<text x="{cx + r}" y="{cy + 22}" text-anchor="middle" class="g-end">100</text>')
    return (f'<svg viewBox="0 0 {w} {cy + 28}" class="gauge" role="img" '
            f'aria-label="Cycle score {score:.0f} of 100">{"".join(parts)}</svg>')


def sources_html(sources):
    seen, parts = set(), []
    for s in sources:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        parts.append(f'<a href="{safe_link(s["link"])}" target="_blank" rel="noopener">{e(s["name"])}</a>'
                     f'<span class="tier" title="Source tier">T{s["tier"]}</span>')
    return "".join(f'<span class="src">{p}</span>' for p in parts)


def stories_html(items) -> str:
    if not items:
        return '<p class="note">Nothing material passed the filters today. A quiet day is a good day.</p>'
    out = []
    for it in items:
        views = ""
        if it.get("bull_view") or it.get("bear_view"):
            views = (f'<div class="views"><div class="bull"><span class="vlabel">▲ Bull reading</span>{e(it["bull_view"])}</div>'
                     f'<div class="bear"><span class="vlabel">▼ Bear reading</span>{e(it["bear_view"])}</div></div>')
        why = f'<p class="why"><span>Why it matters</span>{e(it["why_it_matters"])}</p>' if it.get("why_it_matters") else ""
        out.append(f'''<article class="story">
  <div class="meta"><span class="badge b-{e(it["label"])}">{e(LABEL_TEXT.get(it["label"], it["label"]))}</span>
  <span class="cat">{e(it.get("category", ""))}</span></div>
  <h3>{e(it["headline"])}</h3>
  <p class="body">{e(it["what_happened"])}</p>{why}{views}
  <div class="sources">{sources_html(it["sources"])}</div>
</article>''')
    return "\n".join(out)


def research_html(research) -> str:
    if not research:
        return '<p class="note">No new research reports this week.</p>'
    return "".join(
        f'<a class="research" href="{safe_link(r["story"]["sources"][0]["link"])}" target="_blank" rel="noopener">'
        f'<span class="r-src">{e(r["story"]["sources"][0]["name"])}</span>'
        f'<span class="r-title">{e(r["story"]["title"])}</span>'
        f'<span class="r-text">{e(r["takeaway"])}</span></a>'
        for r in research)


def indicator_cards(cycle) -> str:
    cards = []
    for i in cycle["indicators"]:
        s = i["subscore"] or 0
        k = _zone_key(s)
        val = f'{i["value"]:.1f}' if i["key"] == "rsi_w" else f'{i["value"]:.2f}'
        cards.append(f'''<div class="ind-card">
  <div class="ind-top"><span class="ind-name">{e(i["name"])}</span><span class="ind-val">{val}</span></div>
  <div class="ind-desc">{e(i["desc"])}</div>
  <div class="meter" role="img" aria-label="Sub-score {s:.0f} of 100"><span style="width:{max(s, 2):.0f}%;background:{ZONE_COLORS[k]}"></span></div>
  <div class="ind-sub"><strong>{s:.0f}</strong><span>/100 sub-score</span></div>
  <div class="ind-guide">{e(i["guide"])}</div>
</div>''')
    return "\n".join(cards)


def backtest_rows(cycle) -> str:
    rows = []
    for b in cycle["backtest"]:
        key = _zone_key(float(b["band"].split("–")[0]))
        rows.append(f'<tr><td><span class="swatch" style="background:{ZONE_COLORS[key]}"></span>{e(b["band"])} · {e(b["label"])}</td>'
                    f'<td class="num">{b["days"]:,}</td><td class="num">{pct(b["median"], 0)}</td>'
                    f'<td class="num">{pct(b["pct_positive"], 0, sign=False)}</td></tr>')
    return "\n".join(rows)


def past_turns(cycle) -> str:
    h = {x["d"]: x for x in cycle["history"]}
    turns = [("2015-01-14", "Cycle bottom"), ("2017-12-17", "Cycle top"), ("2018-12-15", "Cycle bottom"),
             ("2021-04-14", "First 2021 top"), ("2021-11-10", "Cycle top"), ("2022-11-21", "Cycle bottom"),
             ("2024-03-14", "Pre-halving high"), ("2025-10-06", "Cycle top (ATH)")]
    rows = []
    for d, label in turns:
        if d in h:
            k = _zone_key(h[d]["s"])
            rows.append(f'<tr><td>{fmt_date(d)}</td><td>{e(label)}</td><td class="num">{usd(h[d]["p"])}</td>'
                        f'<td class="num"><span class="swatch" style="background:{ZONE_COLORS[k]}"></span>{h[d]["s"]:.0f}</td></tr>')
    return "\n".join(rows)


def macro_tiles(macro) -> str:
    if not macro:
        return ('<p class="note">Add a free <code>FRED_API_KEY</code> in <code>.env</code> to show the Fed funds rate, '
                'the 10-year Treasury yield and the dollar index here.</p>')
    tiles = []
    for m in macro:
        if "error" in m:
            tiles.append(f'<div class="mrow"><span>{e(m["label"])}</span><span class="muted">unavailable</span></div>')
            continue
        unit = "%" if m["id"] in ("DFF", "DGS10") else ""
        ch = m["change_30d"]
        chs = "" if ch is None else (f'{ch * 100:+.0f} bp' if unit else f'{ch:+.2f}')
        tiles.append(f'<div class="mrow"><span>{e(m["label"])}</span><span><strong>{m["value"]:.2f}{unit}</strong>'
                     f' <span class="muted small">{chs} · 1M</span></span></div>')
    return "".join(tiles)


# ---------------------------------------------------------------- dashboard
def dashboard(cycle, news, brief, macro, spot, generated_at: str) -> str:
    overview, items, research = news_items(cycle, news, brief)
    summ = brief_summary(cycle, news, brief, spot)
    z = cycle["zone"]
    price = spot or cycle["price_close"]
    as_of = datetime.fromisoformat(cycle["as_of"])
    today_long = datetime.now().strftime("%A, %-d %B %Y")
    hist = [[x["d"], x["p"], x["s"], x["w"], x["r"]] for x in cycle["history"]]
    data_json = json.dumps({"h": hist, "zones": [[u, ZONE_COLORS[k], l] for u, k, l, _ in ZONES]}).replace("</", "<\\/")
    ai_note = f'Analysed by {e(brief["model"])}' if brief else "Filtered headlines · add an Anthropic key for analysis"
    failures = "".join(f"<li>{e(f)}</li>" for f in news["failures"])
    above_wma = price / cycle["wma200"] - 1
    above_rp = price / cycle["realized_price"] - 1
    news_bullets = "".join(f"<li>{e(p)}</li>" for p in summ["news"])

    body = f'''
<section class="hero">
  <div class="mast">
    <div class="brand"><span class="mark">₿</span><div><div class="brand-name">Bitcoin Daily</div>
      <div class="brand-date">{today_long}</div></div></div>
    <div class="chip">Rule-based signals · not financial advice</div>
  </div>
  <div class="hero-grid">
    <div class="h-price">
      <div class="eyebrow">BTC / USD</div>
      <div class="price">{usd(price)}</div>
      <div class="deltas">{delta(cycle["change_1d"])}<span class="dl">24h</span>{delta(cycle["change_30d"])}<span class="dl">30d</span></div>
      <div class="h-facts">
        <div><span>All-time high</span><strong>{usd(cycle["ath"]["price"])}</strong><em>{pct(cycle["ath"]["drawdown"], 0)}</em></div>
        <div><span>200-week MA</span><strong>{usd(cycle["wma200"])}</strong><em>{pct(above_wma, 0)}</em></div>
        <div><span>Realized price</span><strong>{usd(cycle["realized_price"])}</strong><em>{pct(above_rp, 0)}</em></div>
      </div>
      <div class="h-note">{"Live spot via Coinbase" if spot else "Daily close"} · on-chain data to {as_of:%-d %b}</div>
    </div>
    <div class="h-gauge">
      <div class="eyebrow">Cycle score</div>
      {gauge_svg(cycle["score"])}
      <div class="zone-pill" style="--zc:{ZONE_COLORS[z["key"]]}"><span></span>{e(z["label"])}</div>
      <div class="h-action">{e(playbook_action(z))}</div>
    </div>
    <div class="h-summary">
      <div class="eyebrow">Today in 30 seconds</div>
      <ul class="tldr">
        <li><span class="ico">◆</span>{e(summ["market"])}</li>
        <li><span class="ico">◆</span>{e(summ["score"])}</li>
      </ul>
      <div class="tldr-sub">In the news</div>
      <ul class="tldr news">{news_bullets}</ul>
    </div>
  </div>
</section>

<nav class="tabs"><a href="#brief">Brief</a><a href="#indicators">Indicators</a><a href="#history">History</a><a href="#record">Track record</a></nav>

<section class="kpis">
  <div class="kpi"><span class="eyebrow dark">Halving cycle</span><strong>{cycle["halving"]["months_since"]:.0f} months</strong>
    <p>{e(cycle["halving"]["phase"])}</p><em>Next ≈ {fmt_date(cycle["halving"]["next_est"])} · {cycle["halving"]["days_to_next"]} days</em></div>
  <div class="kpi"><span class="eyebrow dark">Drawdown context</span><strong>{pct(cycle["ath"]["drawdown"], 0)}</strong>
    <p>The last three bear markets bottomed roughly 77–86% below their highs, each shallower than the one before.</p>
    <em>Peak {usd(cycle["ath"]["price"])} · {fmt_date(cycle["ath"]["date"])}</em></div>
  <div class="kpi"><span class="eyebrow dark">Network security</span><strong>{pct(cycle["hashrate_change_30d"])}</strong>
    <p>Hashrate change over 30 days. Rising hashrate means miners keep investing in the network.</p><em>Source: Coin Metrics</em></div>
</section>

<div class="cols" id="brief">
  <section class="panel">
    <div class="phead"><h2>Today's brief</h2><span class="meta-note">{ai_note}</span></div>
    {f'<p class="overview">{e(overview)}</p>' if overview else ''}
    {stories_html(items)}
  </section>
  <aside class="side">
    <section class="panel">
      <div class="phead"><h2>Research this week</h2></div>
      <p class="note small">Institutional research (Tier 2)</p>
      {research_html(research)}
    </section>
    <section class="panel">
      <div class="phead"><h2>Macro</h2></div>
      {macro_tiles(macro)}
    </section>
    <section class="panel legend-panel">
      <div class="phead"><h2>How sources are ranked</h2></div>
      <div class="mrow"><span><b class="tier">T1</b> Official &amp; primary</span><span class="muted small">Fed, SEC, Optech</span></div>
      <div class="mrow"><span><b class="tier">T2</b> Institutional research</span><span class="muted small">Coin Metrics</span></div>
      <div class="mrow"><span><b class="tier">T3</b> News outlets</span><span class="muted small">Reuters, Bloomberg…</span></div>
    </section>
  </aside>
</div>

<section class="panel" id="indicators">
  <div class="phead"><h2>Cycle indicators</h2><span class="meta-note">Each maps to 0–100; the cycle score is their average</span></div>
  <div class="ind-grid">{indicator_cards(cycle)}</div>
</section>

<section class="panel" id="history">
  <div class="phead"><h2>History</h2>
    <div class="ranges" role="group" aria-label="Time range">
      <button data-r="all">Since 2014</button><button data-r="4y" class="on">4 years</button><button data-r="1y">1 year</button>
    </div></div>
  <h3 class="chart-title">Cycle score</h3>
  <div class="chart" id="c-score"></div>
  <div class="chart-head"><h3 class="chart-title">Price vs long-run anchors <span class="meta-note">log scale</span></h3>
    <div class="legend" id="lg-price"></div></div>
  <div class="chart" id="c-price"></div>
</section>

<section class="panel" id="record">
  <div class="phead"><h2>Track record</h2><span class="meta-note">How much to trust the score</span></div>
  <div class="cols even">
    <div>
      <h3>Price one year later, by score band <span class="meta-note">2014–{cycle["as_of"][:4]}</span></h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Score band</th><th class="num">Days</th><th class="num">Median 1-yr</th><th class="num">% positive</th></tr></thead>
        <tbody>{backtest_rows(cycle)}</tbody>
      </table></div>
    </div>
    <div>
      <h3>Score at past turning points</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Event</th><th class="num">Price</th><th class="num">Score</th></tr></thead>
        <tbody>{past_turns(cycle)}</tbody>
      </table></div>
    </div>
  </div>
  <div class="callout"><strong>Honest read.</strong> The score has reliably flagged cycle <em>bottoms</em> (all three scored below 5).
  It flagged the 2017 top clearly, but the 2021 and 2025 tops were less extreme on these metrics, so the score stayed
  neutral. Treat the exit side as a guide, not a trigger, and pair it with a scale-out plan you set in advance.
  Only about three full cycles of data exist, and the windows overlap.</div>
</section>

<footer>
  <p><strong>Sources.</strong> Coin Metrics Community API (price, market cap, MVRV, miner issuance, hashrate) · Coinbase (spot) ·
  FRED (macro) · Federal Reserve, SEC, Bitcoin Optech (T1) · Coin Metrics research (T2) · Reuters, Bloomberg, FT, WSJ, CNBC, AP,
  CoinDesk, The Block, Decrypt (T3).</p>
  <p><strong>Noise filter.</strong> Price predictions, altcoins, sponsored content and topic pages are removed; duplicate stories are
  merged; items are ranked by source tier, topic and corroboration. {news["scanned"]} items passed the first filter today.</p>
  {f"<p>Feeds unavailable today:</p><ul>{failures}</ul>" if failures else ""}
  <p>Generated {e(generated_at)}. This page applies fixed, published rules to public data. It is not personalised financial advice.</p>
</footer>
'''
    return PAGE.replace("{{BODY}}", body).replace("{{DATA}}", data_json)


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bitcoin Daily</title>
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="BTC Daily"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0e0f11"><meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light;--page:#f4f3ef;--surface:#ffffff;--surface2:#faf9f6;--ink:#0d0d0e;--ink2:#4e4d49;--muted:#8b8982;
--grid:#ebe9e3;--axis:#cfcdc5;--ring:rgba(13,13,14,.08);--shadow:0 1px 2px rgba(16,17,19,.04),0 10px 30px -12px rgba(16,17,19,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--wash:rgba(13,13,14,.035);--bandop:.16;--up:#0b7a2e;--down:#c23b3b;--btc:#f7931a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0a0a0b;--surface:#151517;--surface2:#1b1b1e;--ink:#f2f1ed;
--ink2:#c3c2b9;--muted:#8d8b84;--grid:#26262a;--axis:#36363b;--ring:rgba(255,255,255,.08);--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px -12px rgba(0,0,0,.5);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--wash:rgba(255,255,255,.045);--bandop:.22;--up:#2fbf5b;--down:#ec6b6b}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0a0a0b;--surface:#151517;--surface2:#1b1b1e;--ink:#f2f1ed;--ink2:#c3c2b9;--muted:#8d8b84;
--grid:#26262a;--axis:#36363b;--ring:rgba(255,255,255,.08);--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px -12px rgba(0,0,0,.5);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--wash:rgba(255,255,255,.045);--bandop:.22;--up:#2fbf5b;--down:#ec6b6b}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;
-webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01";padding:20px 16px 56px}
main{max-width:1200px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
h2{font-size:18px;font-weight:700;letter-spacing:-.01em;margin:0}h3{font-size:15px;font-weight:600;margin:14px 0 8px}
a{color:var(--s1);text-decoration:none}a:hover{text-decoration:underline}
p{margin:6px 0}.muted{color:var(--muted)}.small{font-size:13px}code{font-size:12px;background:var(--wash);padding:1px 5px;border-radius:4px}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:#9c9a92}
.eyebrow.dark{color:var(--muted)}

/* hero: always dark, like a terminal report */
.hero{background:radial-gradient(900px 380px at 88% -20%,rgba(247,147,26,.20),transparent 60%),
 radial-gradient(700px 300px at 0% 120%,rgba(57,135,229,.16),transparent 60%),linear-gradient(180deg,#16171a,#0e0f11);
 color:#f3f2ee;border-radius:22px;padding:22px 26px 26px;box-shadow:0 20px 50px -24px rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.06)}
.mast{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding-bottom:18px;border-bottom:1px solid rgba(255,255,255,.08)}
.brand{display:flex;align-items:center;gap:12px}
.mark{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;font-weight:800;font-size:20px;color:#1a1206;
 background:linear-gradient(145deg,#ffb54a,#f7931a 60%,#d97706);box-shadow:inset 0 1px 0 rgba(255,255,255,.4)}
.brand-name{font-size:19px;font-weight:700;letter-spacing:-.01em}.brand-date{font-size:13px;color:#9c9a92}
.chip{font-size:12px;color:#c9c7bf;border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:5px 12px;background:rgba(255,255,255,.04)}
.hero-grid{display:grid;grid-template-columns:1.05fr 0.95fr 1.35fr;gap:28px;padding-top:22px;align-items:start}
.hero-grid>div{min-width:0}
.price{font-size:54px;font-weight:700;letter-spacing:-.03em;line-height:1.05;margin:6px 0 10px;font-variant-numeric:tabular-nums}
.deltas{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.dl{font-size:12px;color:#9c9a92;margin-right:10px}
.delta{font-size:13px;font-weight:600;border-radius:999px;padding:3px 9px;font-variant-numeric:tabular-nums}
.hero .delta.up{color:#4ade80;background:rgba(74,222,128,.12)}.hero .delta.down{color:#f87171;background:rgba(248,113,113,.12)}
.delta.up{color:var(--up);background:var(--wash)}.delta.down{color:var(--down);background:var(--wash)}
.h-facts{margin-top:18px;display:flex;flex-direction:column}
.h-facts>div{display:grid;grid-template-columns:1fr auto 52px;gap:10px;padding:8px 0;border-top:1px solid rgba(255,255,255,.07);font-size:14px;align-items:baseline}
.h-facts span{color:#a9a79f}.h-facts strong{font-weight:600;font-variant-numeric:tabular-nums}.h-facts em{font-style:normal;color:#9c9a92;font-size:12px;text-align:right;font-variant-numeric:tabular-nums}
.h-note{font-size:12px;color:#7d7b74;margin-top:10px}
.h-gauge{text-align:center;display:flex;flex-direction:column;align-items:center}
.gauge{width:100%;max-width:280px;margin-top:6px}.gauge .g-num{font-size:54px;font-weight:700;fill:#f3f2ee;letter-spacing:-.03em}
.gauge .g-of{font-size:12px;fill:#9c9a92}.gauge .g-end{font-size:11px;fill:#6f6d66}
.zone-pill{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:15px;padding:6px 14px;border-radius:999px;
 background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.10);margin-top:4px}
.zone-pill span{width:10px;height:10px;border-radius:50%;background:var(--zc);box-shadow:0 0 0 3px rgba(255,255,255,.06)}
.h-action{font-size:13px;color:#b9b7af;margin-top:10px;max-width:250px}
.h-summary{background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:16px 18px}
.tldr{list-style:none;margin:10px 0 0;padding:0;display:flex;flex-direction:column;gap:9px}
.tldr li{font-size:14px;line-height:1.5;color:#e6e4de;display:flex;gap:10px}
.tldr .ico{color:var(--btc);font-size:9px;line-height:22px;flex:none}
.tldr-sub{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:#7d7b74;margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,.07)}
.tldr.news li{color:#cfcdc6}.tldr.news li::before{content:"";flex:none;width:5px;height:5px;border-radius:50%;background:#6f6d66;margin-top:9px}

.tabs{display:flex;gap:6px;flex-wrap:wrap;position:sticky;top:8px;z-index:5;align-self:center;
 background:color-mix(in srgb,var(--surface) 82%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
 border:1px solid var(--ring);border-radius:999px;padding:5px;box-shadow:var(--shadow)}
.tabs a{font-size:13px;font-weight:500;color:var(--ink2);padding:6px 14px;border-radius:999px}.tabs a:hover{background:var(--wash);text-decoration:none;color:var(--ink)}

.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:18px;padding:18px 20px;box-shadow:var(--shadow);display:flex;flex-direction:column}
.kpi strong{font-size:28px;font-weight:700;letter-spacing:-.02em;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.kpi p{font-size:13.5px;color:var(--ink2);flex:1}.kpi em{font-style:normal;font-size:12px;color:var(--muted)}

.panel{background:var(--surface);border:1px solid var(--ring);border-radius:18px;padding:22px 24px;box-shadow:var(--shadow);scroll-margin-top:64px}
.phead{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.meta-note{font-size:12.5px;color:var(--muted);font-weight:400}
.cols{display:grid;grid-template-columns:1.65fr 1fr;gap:18px;align-items:start;scroll-margin-top:64px}.cols.even{grid-template-columns:1fr 1fr}
.side{display:flex;flex-direction:column;gap:18px}
.overview{font-size:16px;line-height:1.6;padding:12px 16px;border-radius:12px;background:var(--surface2);border:1px solid var(--ring);margin:4px 0 8px}
.note{color:var(--ink2);font-size:14px}
.story{padding:16px 0;border-top:1px solid var(--grid)}.story:first-of-type{border-top:0}
.story h3{font-size:17px;line-height:1.35;letter-spacing:-.01em;margin:6px 0}
.story .body{color:var(--ink2)}
.meta{display:flex;gap:10px;align-items:center}.cat{font-size:12px;color:var(--muted);font-weight:500}
.badge{font-size:11px;font-weight:600;letter-spacing:.02em;border-radius:6px;padding:2px 8px;color:var(--ink2);background:var(--wash);border:1px solid var(--ring)}
.b-fact{color:var(--ink)}.b-analysis{border-style:dashed}
.why{margin:10px 0;font-size:14.5px}.why span{display:block;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:2px}
.views{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0;font-size:14px;color:var(--ink2)}
.views>div{background:var(--surface2);border:1px solid var(--ring);border-radius:10px;padding:10px 12px}
.vlabel{display:block;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:3px}
.bull .vlabel{color:var(--up)}.bear .vlabel{color:var(--down)}
.sources{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.src{font-size:12px;border:1px solid var(--ring);border-radius:999px;padding:2px 9px;background:var(--surface2)}
.tier{font-size:10px;font-weight:700;margin-left:5px;color:var(--muted)}
b.tier{margin:0 6px 0 0;padding:1px 6px;border-radius:5px;background:var(--wash);color:var(--ink2)}
.research{display:flex;flex-direction:column;gap:2px;padding:12px 0;border-top:1px solid var(--grid);color:inherit}
.research:hover{text-decoration:none}.research:hover .r-title{color:var(--s1)}
.r-src{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.r-title{font-weight:600;line-height:1.35}.r-text{font-size:13px;color:var(--ink2)}
.mrow{display:flex;justify-content:space-between;align-items:baseline;gap:10px;padding:9px 0;border-top:1px solid var(--grid);font-size:14px}
.mrow:first-of-type{border-top:0}
.ind-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.ind-card{border:1px solid var(--ring);border-radius:14px;padding:16px;background:var(--surface2)}
.ind-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.ind-name{font-weight:600}.ind-val{font-size:22px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.ind-desc{font-size:12.5px;color:var(--muted);min-height:38px}
.meter{height:6px;background:var(--wash);border-radius:4px;margin:10px 0 6px;overflow:hidden}.meter span{display:block;height:100%;border-radius:4px}
.ind-sub{font-size:13px}.ind-sub strong{font-size:15px}.ind-sub span{color:var(--muted);margin-left:2px}
.ind-guide{font-size:12.5px;color:var(--ink2);margin-top:8px;padding-top:8px;border-top:1px solid var(--grid)}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;border-bottom:1px solid var(--axis);padding:8px}
td{border-bottom:1px solid var(--grid);padding:10px 8px;vertical-align:top}tbody tr:hover{background:var(--wash)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.swatch{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px;vertical-align:-1px}
.callout{margin-top:16px;padding:14px 16px;border-radius:12px;background:var(--surface2);border:1px solid var(--ring);border-left:3px solid var(--btc);font-size:14px;color:var(--ink2)}
.callout strong{color:var(--ink)}
.ranges{display:flex;gap:2px;background:var(--wash);border-radius:10px;padding:3px}
.ranges button{font:inherit;font-size:13px;font-weight:500;border:0;background:transparent;color:var(--ink2);border-radius:8px;padding:5px 12px;cursor:pointer}
.ranges button.on{background:var(--surface);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.chart-title{margin:18px 0 6px}.chart-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.chart{position:relative;height:270px}.chart svg{display:block;overflow:visible}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--ink2)}.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:3px}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:8px 11px;font-size:12px;
 box-shadow:0 8px 24px rgba(0,0,0,.16);white-space:nowrap;display:none;z-index:2}.tip b{font-weight:600}.tip .r{display:flex;justify-content:space-between;gap:16px}
footer{padding:4px 6px;font-size:12.5px;color:var(--muted)}footer p{margin:6px 0}footer strong{color:var(--ink2)}
@media (max-width:1020px){.hero-grid{grid-template-columns:1fr 1fr}.h-summary{grid-column:1/-1}.ind-grid{grid-template-columns:1fr 1fr}}
@media (max-width:860px){.cols,.cols.even{grid-template-columns:1fr}.kpis{grid-template-columns:1fr}}
@media (max-width:600px){.hero{padding:18px}.hero-grid{grid-template-columns:1fr;gap:22px}.price{font-size:44px}
 .views{grid-template-columns:1fr}.ind-grid{grid-template-columns:1fr}.panel{padding:18px}.chip{display:none}}
</style></head><body><main>
{{BODY}}
</main>
<script>
const D={{DATA}};
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const rows=D.h.map(r=>({t:Date.parse(r[0]),d:r[0],p:r[1],s:r[2],w:r[3],r:r[4]}));
const fmtUsd=v=>v==null?'–':'$'+Math.round(v).toLocaleString('en-US');
const fmtDate=t=>new Date(t).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const NS='http://www.w3.org/2000/svg';
let range='4y';
function el(tag,attrs,parent){const n=document.createElementNS(NS,tag);for(const k in attrs)n.setAttribute(k,attrs[k]);if(parent)parent.appendChild(n);return n}
function zoneOf(s){for(const z of D.zones)if(s<z[0])return z;return D.zones[D.zones.length-1]}

function chart(id,cfg){
  const box=document.getElementById(id);box.innerHTML='';
  const W=box.clientWidth,H=box.clientHeight,gutter=cfg.bands&&W>=560,m={l:58,r:gutter?132:12,t:10,b:26};
  const last=rows[rows.length-1].t, span={all:Infinity,'4y':4*365.25*864e5,'1y':365.25*864e5}[range];
  const data=rows.filter(r=>last-r.t<=span);
  const x0=data[0].t,x1=last,X=t=>m.l+(t-x0)/(x1-x0)*(W-m.l-m.r);
  let lo,hi;
  if(cfg.log){lo=Infinity;hi=0;for(const r of data)for(const s of cfg.series){const v=r[s.k];if(v){lo=Math.min(lo,v);hi=Math.max(hi,v)}}lo=Math.log10(lo*0.9);hi=Math.log10(hi*1.1)}
  else{lo=0;hi=100}
  const Y=v=>{const u=cfg.log?Math.log10(v):v;return m.t+(1-(u-lo)/(hi-lo))*(H-m.t-m.b)};
  const svg=el('svg',{width:W,height:H,role:'img','aria-label':cfg.aria},box);
  if(cfg.bands){let b=0;for(const z of D.zones){const top=Math.min(z[0],100);
    el('rect',{x:m.l,y:Y(top),width:W-m.l-m.r,height:Y(b)-Y(top),fill:z[1],'fill-opacity':css('--bandop')},svg);
    if(gutter){const t=el('text',{x:W-m.r+10,y:(Y(b)+Y(top))/2+4,'font-size':11,fill:css('--ink2')},svg);t.textContent=z[2]}b=top}}
  let ticks=[];
  if(cfg.log){for(let e=Math.floor(lo);e<=Math.ceil(hi);e++)for(const k of [1,2,5]){const v=k*10**e;const u=Math.log10(v);if(u>=lo&&u<=hi)ticks.push(v)}
    if(ticks.length>8)ticks=ticks.filter(v=>String(v)[0]==='1')}
  else ticks=[0,20,40,70,85,100];
  for(const v of ticks){const y=Y(v);if(!cfg.bands)el('line',{x1:m.l,x2:W-m.r,y1:y,y2:y,stroke:css('--grid')},svg);
    const t=el('text',{x:m.l-8,y:y+4,'text-anchor':'end','font-size':11,fill:css('--muted'),'font-variant-numeric':'tabular-nums'},svg);
    t.textContent=cfg.log?(v>=1000?'$'+(v/1000)+'k':'$'+v):v}
  const yrs=new Date(x0).getUTCFullYear(),yre=new Date(x1).getUTCFullYear();
  const xt=[];if(range==='1y'){const d=new Date(x0);d.setUTCDate(1);while(d.getTime()<=x1){d.setUTCMonth(d.getUTCMonth()+1);if(d.getUTCMonth()%3===0&&d.getTime()<=x1)xt.push([d.getTime(),d.toLocaleDateString('en-GB',{month:'short',year:'2-digit',timeZone:'UTC'})])}}
  else{const step=range==='all'?2:1;for(let y=yrs+1;y<=yre;y+=step)xt.push([Date.UTC(y,0,1),String(y)])}
  for(const [t,l] of xt){const tx=el('text',{x:X(t),y:H-6,'text-anchor':'middle','font-size':11,fill:css('--muted')},svg);tx.textContent=l}
  el('line',{x1:m.l,x2:W-m.r,y1:H-m.b,y2:H-m.b,stroke:css('--axis')},svg);
  for(const s of cfg.series){let d='',pen=false;for(const r of data){const v=r[s.k];if(v==null){pen=false;continue}d+=(pen?'L':'M')+X(r.t).toFixed(1)+' '+Y(v).toFixed(1);pen=true}
    el('path',{d,fill:'none',stroke:css(s.c),'stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'},svg)}
  const vline=el('line',{y1:m.t,y2:H-m.b,stroke:css('--muted'),'stroke-dasharray':'3 3',visibility:'hidden'},svg);
  const dots=cfg.series.map(s=>el('circle',{r:4,fill:css(s.c),stroke:css('--surface'),'stroke-width':2,visibility:'hidden'},svg));
  const tip=document.createElement('div');tip.className='tip';box.appendChild(tip);
  const hit=el('rect',{x:m.l,y:0,width:W-m.l-m.r,height:H,fill:'transparent'},svg);
  function move(ev){const rect=svg.getBoundingClientRect();const px=(ev.touches?ev.touches[0].clientX:ev.clientX)-rect.left;
    const t=x0+(px-m.l)/(W-m.l-m.r)*(x1-x0);let a=0,b=data.length-1;while(b-a>1){const mid=(a+b)>>1;if(data[mid].t<t)a=mid;else b=mid}
    const r=Math.abs(data[a].t-t)<Math.abs(data[b].t-t)?data[a]:data[b];const x=X(r.t);
    vline.setAttribute('x1',x);vline.setAttribute('x2',x);vline.setAttribute('visibility','visible');
    let h='<b>'+fmtDate(r.t)+'</b>';
    cfg.series.forEach((s,i)=>{const v=r[s.k];if(v==null){dots[i].setAttribute('visibility','hidden');return}
      dots[i].setAttribute('cx',x);dots[i].setAttribute('cy',Y(v));dots[i].setAttribute('visibility','visible');
      h+='<div class="r"><span>'+s.label+'</span><b>'+s.f(v)+'</b></div>'});
    if(cfg.bands)h+='<div class="r"><span>Zone</span><b>'+zoneOf(r.s)[2]+'</b></div>';
    if(cfg.extra)h+=cfg.extra(r);
    tip.innerHTML=h;tip.style.display='block';const tw=tip.offsetWidth;tip.style.left=(x+12+tw>W?x-12-tw:x+12)+'px';tip.style.top='8px'}
  function leave(){vline.setAttribute('visibility','hidden');dots.forEach(d=>d.setAttribute('visibility','hidden'));tip.style.display='none'}
  hit.addEventListener('mousemove',move);hit.addEventListener('touchmove',move,{passive:true});hit.addEventListener('mouseleave',leave);
}
const priceSeries=[{k:'p',label:'BTC price',c:'--s1',f:fmtUsd},{k:'w',label:'200-week MA',c:'--s2',f:fmtUsd},{k:'r',label:'Realized price',c:'--s3',f:fmtUsd}];
function legend(){document.getElementById('lg-price').innerHTML=priceSeries.map(s=>'<span><i style="background:'+css(s.c)+'"></i>'+s.label+'</span>').join('')}
function draw(){
  chart('c-score',{series:[{k:'s',label:'Cycle score',c:'--ink',f:v=>v.toFixed(0)}],bands:true,aria:'Cycle score over time with zone bands',extra:r=>'<div class="r"><span>BTC price</span><b>'+fmtUsd(r.p)+'</b></div>'});
  chart('c-price',{series:priceSeries,log:true,aria:'BTC price, 200-week moving average and realized price, log scale'});
  legend();
}
document.querySelectorAll('.ranges button').forEach(b=>b.addEventListener('click',()=>{range=b.dataset.r;
  document.querySelectorAll('.ranges button').forEach(x=>x.classList.toggle('on',x===b));draw()}));
let rt;addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120)});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
document.fonts&&document.fonts.ready.then(draw);
draw();
</script></body></html>'''


# ---------------------------------------------------------------- email
def email_html(cycle, news, brief, spot) -> str:
    """Table-based, inline-styled HTML that renders in Gmail/Outlook/Apple Mail (no scripts, no SVG)."""
    overview, items, research = news_items(cycle, news, brief)
    summ = brief_summary(cycle, news, brief, spot)
    z = cycle["zone"]
    zc = ZONE_COLORS[z["key"]]
    price = spot or cycle["price_close"]
    font = "-apple-system,'SF Pro Text','Segoe UI',Inter,Helvetica,Arial,sans-serif"

    def chg(v):
        if v is None:
            return ""
        c = "#4ade80" if v >= 0 else "#f87171"
        return f'<span style="color:{c};font-weight:600">{"▲" if v >= 0 else "▼"} {abs(v) * 100:.1f}%</span>'

    bullet = lambda t, c="#f7931a": (f'<tr><td width="18" valign="top" style="color:{c};font-size:9px;padding-top:6px">◆</td>'
                                     f'<td style="font-size:14px;line-height:1.5;color:#2b2a27;padding-bottom:8px">{e(t)}</td></tr>')
    tldr = bullet(summ["market"]) + bullet(summ["score"]) + "".join(bullet(p, "#a9a8a0") for p in summ["news"])

    stories = ""
    for it in items:
        srcs = " · ".join(dict.fromkeys(
            f'<a href="{safe_link(s["link"])}" style="color:#2a78d6;text-decoration:none">{e(s["name"])}</a>' for s in it["sources"]))
        why = (f'<p style="margin:8px 0 0;font-size:14px;color:#2b2a27"><b style="font-size:11px;letter-spacing:.08em;color:#8b8982">WHY IT MATTERS</b><br>'
               f'{e(it["why_it_matters"])}</p>') if it.get("why_it_matters") else ""
        views = (f'<p style="margin:8px 0 0;font-size:13px;color:#4e4d49"><b style="color:#0b7a2e">▲ Bull:</b> {e(it["bull_view"])}<br>'
                 f'<b style="color:#c23b3b">▼ Bear:</b> {e(it["bear_view"])}</p>') if it.get("bull_view") else ""
        stories += (f'<tr><td style="padding:16px 0;border-top:1px solid #ebe9e3">'
                    f'<div style="font-size:11px;font-weight:600;letter-spacing:.06em;color:#8b8982;text-transform:uppercase">'
                    f'{e(LABEL_TEXT.get(it["label"], it["label"]))} · {e(it.get("category", ""))}</div>'
                    f'<div style="font-size:17px;font-weight:700;line-height:1.35;margin:4px 0;color:#0d0d0e">{e(it["headline"])}</div>'
                    f'<p style="margin:4px 0;font-size:14px;color:#4e4d49;line-height:1.55">{e(it["what_happened"])}</p>{why}{views}'
                    f'<div style="font-size:12px;color:#8b8982;margin-top:8px">Sources: {srcs}</div></td></tr>')
    if not stories:
        stories = '<tr><td style="padding:12px 0;color:#4e4d49">Nothing material passed the filters today.</td></tr>'
    res = "".join(f'<tr><td style="padding:10px 0;border-top:1px solid #ebe9e3;font-size:14px">'
                  f'<a href="{safe_link(r["story"]["sources"][0]["link"])}" style="color:#0d0d0e;font-weight:600;text-decoration:none">{e(r["story"]["title"])}</a>'
                  f'<div style="color:#4e4d49;font-size:13px">{e(r["takeaway"])}</div></td></tr>' for r in research)
    ind = "".join(
        f'<tr><td style="padding:8px 0;border-top:1px solid #ebe9e3;font-size:14px">{e(i["name"])}</td>'
        f'<td align="right" style="padding:8px 0;border-top:1px solid #ebe9e3;font-size:14px">{i["value"]:.2f}</td>'
        f'<td align="right" width="70" style="padding:8px 0;border-top:1px solid #ebe9e3;font-size:14px">'
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{ZONE_COLORS[_zone_key(i["subscore"] or 0)]}"></span> '
        f'<b>{(i["subscore"] or 0):.0f}</b></td></tr>' for i in cycle["indicators"])
    fact = lambda k, v: (f'<td style="padding:10px 0 0;font-size:12px;color:#9c9a92">{e(k)}<br>'
                         f'<span style="font-size:15px;color:#f3f2ee;font-weight:600">{e(v)}</span></td>')
    section = lambda t: f'<div style="font-size:11px;font-weight:700;letter-spacing:.12em;color:#8b8982;text-transform:uppercase;margin-bottom:6px">{t}</div>'

    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f3ef;font-family:{font};color:#0d0d0e">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f3ef"><tr><td align="center" style="padding:24px 12px">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px">

<tr><td style="background:#121316;border-radius:18px;padding:24px 26px;color:#f3f2ee">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td><table cellpadding="0" cellspacing="0"><tr>
      <td style="width:34px;height:34px;background:#f7931a;border-radius:10px;text-align:center;font-weight:800;font-size:18px;color:#1a1206">₿</td>
      <td style="padding-left:10px"><div style="font-size:17px;font-weight:700">Bitcoin Daily</div>
        <div style="font-size:12px;color:#9c9a92">{datetime.now():%A, %-d %B %Y}</div></td></tr></table></td>
  </tr></table>
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px"><tr>
    <td valign="top">
      <div style="font-size:11px;letter-spacing:.12em;color:#9c9a92">BTC / USD</div>
      <div style="font-size:38px;font-weight:700;letter-spacing:-.02em;line-height:1.15">{usd(price)}</div>
      <div style="font-size:13px">{chg(cycle["change_1d"])} <span style="color:#9c9a92">24h</span> &nbsp; {chg(cycle["change_30d"])} <span style="color:#9c9a92">30d</span></div>
    </td>
    <td valign="top" align="right">
      <div style="font-size:11px;letter-spacing:.12em;color:#9c9a92">CYCLE SCORE</div>
      <div style="font-size:38px;font-weight:700;line-height:1.15">{cycle["score"]:.0f}<span style="font-size:14px;color:#9c9a92">/100</span></div>
      <div style="display:inline-block;font-size:13px;font-weight:600;padding:4px 10px;border-radius:999px;background:#24252a">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{zc}"></span> {e(z["label"])}</div>
    </td></tr></table>
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;border-top:1px solid #2a2b30"><tr>
    {fact("From ATH", pct(cycle["ath"]["drawdown"], 0))}{fact("200-week MA", usd(cycle["wma200"]))}
    {fact("Realized price", usd(cycle["realized_price"]))}{fact("Since halving", f'{cycle["halving"]["months_since"]:.0f} mo')}
  </tr></table>
</td></tr>

<tr><td style="height:14px"></td></tr>
<tr><td style="background:#ffffff;border-radius:16px;padding:20px 24px;border:1px solid #ebe9e3">
  {section("Today in 30 seconds")}
  <table width="100%" cellpadding="0" cellspacing="0">{tldr}</table>
</td></tr>

<tr><td style="height:14px"></td></tr>
<tr><td style="background:#ffffff;border-radius:16px;padding:20px 24px 6px;border:1px solid #ebe9e3">
  {section("Today's brief")}
  {f'<p style="margin:4px 0 12px;font-size:15px;line-height:1.6">{e(overview)}</p>' if overview else ''}
  <table width="100%" cellpadding="0" cellspacing="0">{stories}</table>
</td></tr>

{f"""<tr><td style="height:14px"></td></tr><tr><td style="background:#ffffff;border-radius:16px;padding:20px 24px 8px;border:1px solid #ebe9e3">
  {section("Research this week")}<table width="100%" cellpadding="0" cellspacing="0">{res}</table></td></tr>""" if res else ""}

<tr><td style="height:14px"></td></tr>
<tr><td style="background:#ffffff;border-radius:16px;padding:20px 24px 12px;border:1px solid #ebe9e3">
  {section("Cycle indicators")}
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td style="font-size:11px;color:#8b8982;padding-bottom:4px">Indicator</td><td align="right" style="font-size:11px;color:#8b8982">Value</td><td align="right" style="font-size:11px;color:#8b8982">Sub-score</td></tr>{ind}</table>
</td></tr>

<tr><td style="padding:16px 8px;font-size:12px;color:#8b8982;line-height:1.5">The full interactive dashboard is attached. Rule-based signals from public
data (Coin Metrics, Coinbase, FRED and the listed news sources), not personalised financial advice.</td></tr>
</table></td></tr></table></body></html>'''
