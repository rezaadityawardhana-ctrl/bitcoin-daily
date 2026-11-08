"""Builds the dashboard page (dashboard.html) and the email body (email_preview.html)."""
import html
import json
import math
from datetime import datetime

import chart_view
import webapp_view
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
            flags = list(stories[idx].get("flags", [])) if ok else []
            if it.get("agenda_note"):
                flags.insert(0, it["agenda_note"])
            items.append({**it, "category": stories[idx]["category"] if ok else "",
                          "sources": stories[idx]["sources"] if ok else [],
                          "tone": it.get("sentiment", "neutral"), "flags": flags})
        research = [{"takeaway": r["takeaway"], "story": stories[r["story_index"]]}
                    for r in brief["research_takeaways"] if 0 <= r["story_index"] < len(stories)]
        return brief["overview"], items, research
    items = [{
        "headline": s["title"], "what_happened": clip(s["summary"], 280), "why_it_matters": "",
        "label": "fact" if s["tier"] == 1 or s["corroborated"] else "report",
        "bull_view": "", "bear_view": "", "category": s["category"], "sources": s["sources"],
        "tone": s.get("tone", "neutral"), "flags": s.get("flags", []),
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


# ---------------------------------------------------------------- mood & flows
TONE = {"bullish": ("▲", "Bullish", "t-bull"), "bearish": ("▼", "Bearish", "t-bear"), "neutral": ("●", "Neutral", "t-neu")}
MOOD_BANDS = [(20, "Extreme fear", "#2f6fd0"), (40, "Fear", "#7fb2f0"), (60, "Neutral", "#a9a8a0"),
              (80, "Greed", "#ee9e9d"), (100, "Euphoria", "#e34948")]
ETF_ISSUER = {"IBIT": "BlackRock", "FBTC": "Fidelity", "GBTC": "Grayscale", "BTC": "Grayscale Mini", "ARKB": "ARK 21Shares",
              "BITB": "Bitwise", "HODL": "VanEck", "BTCO": "Invesco", "EZBC": "Franklin", "BRRR": "CoinShares",
              "BTCW": "WisdomTree", "MSBT": "Morgan Stanley"}


def mood_color(v: float) -> str:
    return next(c for upper, _, c in MOOD_BANDS if v < upper or upper == 100)


def money(v: float, unit="m") -> str:
    return f'{"+" if v >= 0 else "−"}${abs(v):,.0f}{unit}'


def mood_scale(v: float) -> str:
    lo, segs, labels = 0, [], []
    for upper, label, color in MOOD_BANDS:
        segs.append(f'<span style="flex:{upper - lo};background:{color}"></span>')
        labels.append(f'<span style="flex:{upper - lo}">{label}</span>')
        lo = upper
    return (f'<div class="mscale">{"".join(segs)}<i style="left:{v:.1f}%"></i></div>'
            f'<div class="mscale-labels">{"".join(labels)}</div>')


def etf_card(etf: dict) -> str:
    if "error" in etf or not etf.get("days"):
        return '<div class="fcard"><span class="eyebrow dark">Spot ETF flows</span><p class="note">Unavailable today.</p></div>'
    days = etf["days"][-15:]
    peak = max(abs(d["total"]) for d in days) or 1
    cols = []
    for i, d in enumerate(days):
        h = abs(d["total"]) / peak * 100
        top = max(((f, v) for f, v in d["funds"].items() if v), key=lambda x: abs(x[1]), default=None)
        tip = f'{fmt_date(d["date"])}: {money(d["total"])} net' + (f' · biggest: {top[0]} {money(top[1])}' if top else "")
        bar = (f'<span class="ec-bar {"in" if d["total"] >= 0 else "out"}" style="height:{max(h, 1.5):.1f}%"></span>')
        lab = datetime.fromisoformat(d["date"]).strftime("%-d %b") if i in (0, len(days) // 2, len(days) - 1) else ""
        cols.append(f'<div class="ec" data-tip="{e(tip)}" tabindex="0"><div class="ec-up">{bar if d["total"] >= 0 else ""}</div>'
                    f'<div class="ec-dn">{bar if d["total"] < 0 else ""}</div><div class="ec-lab">{lab}</div></div>')
    movers = "".join(
        f'<div class="mover"><span><b>{e(f)}</b> <span class="muted small">{e(ETF_ISSUER.get(f, ""))}</span></span>'
        f'<span class="{"pos" if v >= 0 else "neg"}">{money(v)}</span></div>' for f, v in etf["movers_7d"][:4])
    streak = etf["streak"]
    streak_txt = (f'{abs(streak)} {"inflow" if streak > 0 else "outflow"} day{"s" if abs(streak) != 1 else ""} in a row'
                  if streak else "")
    return f'''<div class="fcard">
  <span class="eyebrow dark">US spot ETF flows</span>
  <div class="fbig"><strong class="{"pos" if etf["sum_7d"] >= 0 else "neg"}">{money(etf["sum_7d"])}</strong><span>last 7 days</span></div>
  <div class="etf-cols" role="img" aria-label="Daily net ETF flows, last {len(days)} trading days">{"".join(cols)}</div>
  <div class="ec-key"><span class="k in"></span>inflow <span class="k out"></span>outflow · hover a day</div>
  <div class="movers"><div class="muted small">Biggest fund moves, 7 days</div>{movers}</div>
  <em>{e(streak_txt)} · Source: Farside Investors</em>
</div>'''


def exchange_card(ex: dict) -> str:
    if "error" in ex or not ex.get("series"):
        return '<div class="fcard"><span class="eyebrow dark">Coins on exchanges</span><p class="note">Unavailable today.</p></div>'
    vals = [v for _, v in ex["series"]]
    lo, hi = min(vals), max(vals)
    pts = " ".join(f'{i / (len(vals) - 1) * 100:.2f},{(1 - (v - lo) / ((hi - lo) or 1)) * 36 + 2:.2f}' for i, v in enumerate(vals))
    c7 = ex["change_7d"]
    reading = ("More coins are sitting where they can be sold quickly." if c7 and c7 > 0
               else "Coins are leaving exchanges, usually into long-term storage.")
    return f'''<div class="fcard">
  <span class="eyebrow dark">Coins on exchanges</span>
  <div class="fbig"><strong>{ex["balance"] / 1e6:.2f}M BTC</strong><span>held on exchanges</span></div>
  <svg class="spark" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="Exchange balance, last 60 days">
    <polyline points="{pts}" fill="none" stroke="var(--s1)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>
  <div class="kv2"><span>7 days</span><b class="{"neg" if c7 and c7 > 0 else "pos"}">{"+" if c7 >= 0 else "−"}{abs(c7):,.0f} BTC</b></div>
  <div class="kv2"><span>30 days</span><b>{pct(ex["change_30d_pct"])}</b></div>
  <p class="small">{reading}</p>
  <em>60-day trend · Source: Coin Metrics</em>
</div>'''


def _chg_cell(v) -> str:
    if v is None:
        return "–"
    return f'<span class="{"pos" if v >= 0 else "neg"}">{"+" if v >= 0 else "−"}{abs(v):,.0f}</span>'


def _flag(cc) -> str:
    if not cc or len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in cc.upper())


def treasury_card(tr: dict) -> str:
    """Largest known holders as a click-to-open dropdown: ETFs & funds, companies, governments, disclosed
    individuals and lost/unmoved coins."""
    if "error" in tr or not tr.get("groups"):
        return '<div class="fcard wide"><span class="eyebrow dark">Largest bitcoin holders</span><p class="note">Unavailable today.</p></div>'
    peak = max(h["pct_supply"] for rows in tr["groups"].values() for h in rows)
    body, chips = [], []
    show_first = 12
    for group, rows in tr["groups"].items():
        total = tr["totals"].get(group) or sum(h["btc"] for h in rows)
        is_est = all(h["estimate"] for h in rows)
        short = {"ETFs & funds": "ETFs & funds", "Public companies": "Companies", "Governments": "Governments",
                 "Individuals (publicly disclosed)": "Individuals", "Lost & unmoved (estimates)": "Lost & unmoved"}.get(group, group)
        amount = f"{total / 1e6:.2f}M" if total >= 1e6 else f"{total / 1e3:.0f}k"
        chips.append(f'<span class="hchip"><b>{e(short)}</b> {"~" if is_est else ""}{amount} BTC '
                     f'<span class="muted">{total / 21e6 * 100:.1f}%</span></span>')
        count = f" · {len(rows)} holders" if len(rows) > 2 else ""
        body.append(f'<tr class="grp"><td colspan="5">{e(group)}<span>{total:,.0f} BTC · {total / 21e6 * 100:.1f}% of 21M{count}</span></td></tr>')
        for i, h in enumerate(rows):
            est = (f' <span class="est" data-tip="{e(h["note"])}" tabindex="0">est.</span>' if h["estimate"] else "")
            country = f'{_flag(h["country"])} {e(h["country"])}' if h["country"] else '<span class="muted">–</span>'
            extra = ' class="extra"' if i >= show_first else ""
            body.append(
                f'<tr{extra}><td>{e(h["name"])}{est}</td><td>{country}</td><td class="num">{h["btc"]:,.0f}</td>'
                f'<td class="num"><div class="pctcell"><span class="pbar"><i style="width:{h["pct_supply"] / peak * 100:.1f}%"></i></span>'
                f'{h["pct_supply"]:.2f}%</div></td>'
                f'<td class="num">{_chg_cell(h["chg_7d"]) if not h["estimate"] else "<span class=muted>n/a</span>"}</td></tr>')
        if len(rows) > show_first:
            body.append(f'<tr class="more-row"><td colspan="5"><button type="button" class="more-btn" '
                        f'onclick="this.closest(\'table\').classList.toggle(\'show-all\');'
                        f'this.textContent=this.closest(\'table\').classList.contains(\'show-all\')?\'Show fewer\':\'Show all {len(rows)} {e(short)}\'">'
                        f'Show all {len(rows)} {e(short)}</button></td></tr>')
    note = ("7-day changes fill in after a week of daily snapshots." if tr["history_days"] < 8
            else "7-day changes compare with the snapshot from a week ago.")
    big = tr.get("biggest_7d")
    big_txt = (f'<p class="small">Biggest 7-day move: <b>{e(big["name"])}</b> {"+" if big["chg_7d"] >= 0 else "−"}{abs(big["chg_7d"]):,.0f} BTC.</p>'
               if big else "")
    return f'''<details class="fcard wide holders">
  <summary>
    <div class="h-sum-top"><span class="eyebrow dark">Largest bitcoin holders</span><span class="h-toggle"><span class="t-open">Show table</span><span class="t-close">Hide table</span> ▾</span></div>
    <div class="hchips">{"".join(chips)}</div>
  </summary>
  <div class="table-wrap"><table class="tr-table">
    <thead><tr><th>Holder</th><th>Country</th><th class="num">BTC</th><th class="num">% of 21M</th><th class="num">7 days</th></tr></thead>
    <tbody>{"".join(body)}</tbody></table></div>
  {big_txt}
  <em>{note} ETFs & funds: bitcointreasuries.net. Companies and governments: CoinGecko. Updated daily. Individuals and lost
  coins: published estimates, not live (hover "est." for the source).</em>
</details>'''


def chf_facts(cycle, price_usd, market) -> dict | None:
    """All-time high, 200-week MA and realized price in CHF.
    ATH and 200-week MA come from Kraken BTC/CHF candles; realized price (an on-chain USD cost basis) is converted at
    today's rate."""
    chf, ta_data = market.get("chf"), market.get("ta")
    if not chf or not ta_data:
        return None
    now = chf["btc_chf"]
    d, w = ta_data["candles"]["chf_d"], ta_data["candles"]["chf_w"]
    ath = max(c[4] for c in d)
    wc = [c[4] for c in w]
    wma = sum(wc[-200:]) / 200 if len(wc) >= 200 else None
    rp = cycle["realized_price"] * now / price_usd
    return {"now": now, "ath": ath, "wma200": wma, "realized": rp}


def facts_table(cycle, price, market) -> str:
    c = chf_facts(cycle, price, market)
    cell = lambda v, now, sym: (f'<td><strong>{sym}{v:,.0f}</strong><em>{pct(now / v - 1, 0)}</em></td>' if v else "<td>–</td>")
    rows = [("All-time high", cycle["ath"]["price"], c and c["ath"]),
            ("200-week MA", cycle["wma200"], c and c["wma200"]),
            ("Realized price", cycle["realized_price"], c and c["realized"])]
    body = "".join(f'<tr><th scope="row">{label}</th>{cell(u, price, "$")}{cell(f, c["now"], "CHF ") if c else ""}</tr>'
                   for label, u, f in rows)
    head = '<tr><th></th><th>USD</th>' + ('<th>CHF</th>' if c else "") + "</tr>"
    return (f'<table class="h-facts2" title="% = how far today\'s price is from each level">{head}{body}</table>'
            '<div class="h-note">% = distance of today\'s price from each level. CHF realized price converted at today\'s rate.</div>')


def chf_block(cycle, chf) -> str:
    """BTC price in Swiss francs (tap to open the CHF chart)."""
    if not chf:
        return ""
    fx1 = chf.get("fx_change_1d")
    btc_chf_1d = ((1 + cycle["change_1d"]) * (1 + fx1) - 1) if fx1 is not None else None
    return f'''<div class="chf">
        <div class="chf-price price-btn" data-open-chart="chf" role="button" tabindex="0" aria-label="Open BTC/CHF chart"><span class="cur">CHF</span><span data-live="chf">{chf["btc_chf"]:,.0f}</span>{delta(btc_chf_1d) if btc_chf_1d is not None else ""}<span class="dl">24h</span></div>
      </div>'''


def mood_section(market: dict) -> str:
    mood, flows = market["mood"], market["flows"]
    if mood.get("value") is None:
        head = '<p class="note">Mood data unavailable today.</p>'
    else:
        v = mood["value"]
        parts = "".join(
            f'<div class="mpart"><div class="mp-top"><span>{e(p["name"])} <span class="muted small">{p["weight"]:.0%}</span></span>'
            f'<span class="mp-detail">{e(p["detail"])}</span></div>'
            f'<div class="mp-bar"><span style="left:{p["score"]:.0f}%;background:{mood_color(p["score"])}"></span></div></div>'
            for p in mood["parts"])
        head = f'''<div class="mood-head"><span class="mood-num">{v:.0f}</span>
      <div><div class="mood-label"><span style="background:{mood_color(v)}"></span>{e(mood["label"])}</div>
      <div class="small muted">Blend of the inputs below · 0 = extreme fear, 100 = euphoria</div></div></div>
    {mood_scale(v)}
    <div class="mparts">{parts}</div>'''
    bullets = "".join(f"<li>{e(t)}</li>" for t in market["interpretation"])
    src = "AI analysis (Claude)" if market["interp_ai"] else "Rule-based · add an Anthropic key for AI analysis"
    return f'''<section class="panel" id="mood">
  <div class="phead"><h2>Market mood &amp; money flows</h2><span class="meta-note">What headlines feel vs what money does</span></div>
  <div class="cols even">
    <div>{head}</div>
    <div class="read">
      <div class="read-head"><h3>How to read today</h3><span class="ai-tag">{e(src)}</span></div>
      <ul>{bullets}</ul>
      <p class="small muted">Rule of thumb: headlines describe what already happened. Flows show what money is doing now.
      Extreme fear at low valuations has historically been a better time to buy than to sell.</p>
    </div>
  </div>
  <h3 class="sub">Institutional &amp; whale moves</h3>
  <div class="flow-grid">{etf_card(flows.get("etf", {}))}{exchange_card(flows.get("exchanges", {}))}{treasury_card(flows.get("treasuries", {}))}</div>
</section>'''


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
        icon, tlabel, tcls = TONE.get(it.get("tone", "neutral"), TONE["neutral"])
        flags = "".join(f"<li>{e(f)}</li>" for f in it.get("flags", []))
        flags_html = f'<ul class="agenda"><li class="ag-h">Agenda check</li>{flags}</ul>' if flags else ""
        out.append(f'''<article class="story">
  <div class="meta"><span class="tone {tcls}">{icon} {tlabel}</span><span class="badge b-{e(it["label"])}">{e(LABEL_TEXT.get(it["label"], it["label"]))}</span>
  <span class="cat">{e(it.get("category", ""))}</span></div>
  <h3>{e(it["headline"])}</h3>
  <p class="body">{e(it["what_happened"])}</p>{why}{views}
  {flags_html}
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


EXIT_STYLE = {  # status -> (css class, icon)
    "waiting": ("ex-idle", "○"), "watch": ("ex-watch", "◔"), "armed": ("ex-armed", "◑"),
    "triggered": ("ex-fired", "●"), "closed": ("ex-closed", "◉"),
}


def _k(v) -> str:
    return f"${v / 1000:,.1f}k"


def mining_card(cycle) -> str:
    m = cycle.get("mining")
    if not m:
        return ('<div class="kpi mining-card"><span class="eyebrow dark">Network security &amp; cost to mine 1 BTC</span>'
                '<p class="note">Mining data unavailable today.</p></div>')
    c, a = m["electricity_cost"], m["assumptions"]
    price, all_in = m["price"], m["all_in_cost"]
    lo = min(c["low"], price) * 0.85
    hi = max(c["high"], all_in, price) * 1.08
    x = lambda v: (v - lo) / (hi - lo) * 100
    eff, kwh = a["efficiency_j_per_th"], a["electricity_usd_kwh"]
    zone_cls = {"capitulation": "neg", "squeeze": "warn", "healthy": "pos", "rich": "pos"}[m["zone"]]
    zone_txt = {"capitulation": "Below electricity cost", "squeeze": "Miner squeeze", "healthy": "Miners profitable",
                "rich": "Very high margins"}[m["zone"]]
    return f'''<div class="kpi mining-card" id="network">
  <span class="eyebrow dark">Network security &amp; cost to mine 1 BTC</span>
  <div class="mine-grid">
    <div class="mine-left">
      <div class="mstat"><strong>{m["hashrate_eh"]:,.0f} EH/s</strong><span>hashrate · {pct(m["hashrate_change_30d"])} in 30 days</span></div>
      <p class="small">Hashrate is the computing power securing the network. Rising hashrate means miners keep investing.</p>
      <div class="kv2"><span>Miner revenue (hashprice)</span><b>${m["hashprice_ph_day"]:,.2f} / PH / day</b></div>
      <div class="kv2"><span>Break-even power price, {eff["mid"]:.0f} J/TH machine</span><b>${m["breakeven_kwh"]:.3f} / kWh</b></div>
      <div class="kv2"><span>New BTC mined per day (incl. fees)</span><b>{m["btc_per_day"]:,.0f} BTC</b></div>
    </div>
    <div class="mine-right">
      <div class="mstat"><strong>{_k(c["mid"])}</strong><span>electricity cost per BTC (est.) · all-in {_k(all_in)}</span></div>
      <div class="cost-scale" role="img" aria-label="Price {_k(price)} versus electricity cost {_k(c["mid"])} and all-in cost {_k(all_in)}">
        <span class="cs-range" style="left:{x(c["low"]):.1f}%;width:{x(c["high"]) - x(c["low"]):.1f}%"></span>
        <span class="cs-tick" style="left:{x(c["mid"]):.1f}%"><b>Electricity {_k(c["mid"])}</b></span>
        <span class="cs-tick allin" style="left:{x(all_in):.1f}%"><b>All-in {_k(all_in)}</b></span>
        <span class="cs-price" style="left:{x(price):.1f}%"><b>Price {_k(price)}</b></span>
      </div>
      <div class="cs-legend"><span class="k range"></span>electricity cost range {_k(c["low"])}–{_k(c["high"])}</div>
      <div class="kv2"><span>Price vs electricity cost</span><b>{pct(m["price_vs_electricity"], 0)}</b></div>
      <div class="kv2"><span>Price vs all-in cost</span><b>{pct(m["price_vs_all_in"], 0)}</b></div>
      <p class="small"><span class="zchip {zone_cls}">{zone_txt}</span> {e(m["reading"])}</p>
    </div>
  </div>
  <em>Estimate, not a reported figure. Assumes average machine efficiency {eff["low"]:.0f}–{eff["high"]:.0f} J/TH
  (mid {eff["mid"]:.0f}), power ${kwh["low"]:.3f}–${kwh["high"]:.3f}/kWh (mid ${kwh["mid"]:.3f}), and electricity at
  {a["electricity_share"]:.0%} of all-in cost. 7-day averages. Data: Coin Metrics.</em>
</div>'''


def exit_card(cycle) -> str:
    x = cycle["exit"]
    cls, icon = EXIT_STYLE[x["status"]]
    vs = x["price_vs_exit_ma"]
    steps = ('<li><b>Scale-out steps:</b> each new all-time high inside the window → sell a small slice (e.g. 5–10%).</li>'
             '<li><b>Exit trigger:</b> first weekly close below the 50-day MA after a new high → sell a bigger tranche.</li>')
    return f'''<div class="kpi exit-card {cls}">
  <span class="eyebrow dark">Exit signal · late-cycle sell rule</span>
  <div class="exit-status"><span class="exit-icon">{icon}</span><strong>{e(x["label"])}</strong></div>
  <p>{e(x["detail"])}</p>
  <ul class="exit-rules">{steps}</ul>
  <em>Exit window: 12–24 months after each halving · 50-day MA now {usd(x["exit_ma"])} (price {pct(vs, 0)} vs it)</em>
</div>'''


def zone_return_chart(cycle) -> str:
    """Horizontal bars: median price change one year after each score zone (diverging around 0)."""
    bands = [b for b in cycle["backtest"] if b["median"] is not None]
    lo = min(0.0, min(b["median"] for b in bands)) - 0.05
    hi = max(b["median"] for b in bands) + 0.15
    zero = (0 - lo) / (hi - lo) * 100
    rows = []
    for b in bands:
        key = _zone_key(float(b["band"].split("–")[0]))
        v = b["median"]
        left, width = (zero, v / (hi - lo) * 100) if v >= 0 else (zero + v / (hi - lo) * 100, -v / (hi - lo) * 100)
        lab_pos = f"left:calc({left + width:.2f}% + 6px)" if v >= 0 else f"right:calc({100 - left:.2f}% + 6px)"
        tip = (f'{b["label"]} (score {b["band"]}): median {pct(v, 0)} one year later; '
               f'{pct(b["pct_positive"], 0, sign=False)} of {b["days"]:,} days were higher a year later')
        rows.append(f'''<div class="zr-row" data-tip="{e(tip)}" tabindex="0">
  <div class="zr-label"><span class="swatch" style="background:{ZONE_COLORS[key]}"></span>{e(b["label"])}<span class="zr-band">{e(b["band"])}</span></div>
  <div class="zr-track"><span class="zr-zero" style="left:{zero:.2f}%"></span>
    <span class="zr-bar" style="left:{left:.2f}%;width:{max(width, 0.6):.2f}%;background:{ZONE_COLORS[key]}"></span>
    <span class="zr-val" style="{lab_pos}">{pct(v, 0)}</span></div>
  <div class="zr-sub">{pct(b["pct_positive"], 0, sign=False)} of the time higher</div>
</div>''')
    return "\n".join(rows)


def _cycle_exits(cycle):
    """Group exit triggers by halving cycle: the last one is the exit after the cycle top,
    earlier ones fired before the top (they sold a slice too early)."""
    groups = {}
    for ev in cycle["exit"]["events"]:
        groups.setdefault(ev["halving"], []).append(ev)
    out = []
    for evs in groups.values():
        final, early = evs[-1], evs[:-1]
        for x in early:  # how much higher the price went after this early signal
            x["missed"] = final["high"] / x["price"] - 1
        out.append((final, early))
    return out


def exit_ladder(cycle) -> str:
    """One row per past cycle top: how far below the top the exit signal fired vs how far the bear market fell."""
    h = {x["d"]: x["s"] for x in cycle["history"]}
    scale = 0.9  # track spans 0% (the top) to -90%
    rows = []
    for ev, early in reversed(_cycle_exits(cycle)):
        if ev["later_low"] is None:
            continue
        sig = abs(ev["from_high"]) / scale * 100
        low = abs(ev["later_low"]) / scale * 100
        further = ev["low_price"] / ev["price"] - 1
        st, sb = h.get(ev["high_date"]), h.get(ev["low_date"])
        chip = lambda label, v: ("" if v is None else
                                 f'<span class="chip-s"><span class="swatch" style="background:{ZONE_COLORS[_zone_key(v)]}"></span>{label} {v:.0f}</span>')
        so_far = "" if ev["low_final"] else " so far"
        early_html = "".join(
            f'<div class="lad-early">▲ Early signal {fmt_date(x["date"])} at {usd(x["price"])}: the price then rose '
            f'<strong>{x["missed"] * 100:.0f}%</strong> to the top before the exit above.</div>' for x in early)
        rows.append(f'''<div class="lad-row">
  <div class="lad-head"><strong>{datetime.fromisoformat(ev["high_date"]).year} top</strong>
    <span class="muted">{usd(ev["high"])} · {fmt_date(ev["high_date"])}</span>
    <span class="lad-chips">{chip("Score at top", st)}{chip("at bottom", sb)}</span></div>
  <div class="lad-track" role="img" aria-label="Exit signal {pct(ev["from_high"], 0)} from top; bear-market low {pct(ev["later_low"], 0)}{so_far}">
    <span class="lad-fall" style="width:{low:.2f}%"></span>
    <span class="lad-saved" style="left:{sig:.2f}%;width:{low - sig:.2f}%"></span>
    <span class="lad-mark" style="left:{sig:.2f}%"><i></i><b>Exit {pct(ev["from_high"], 0)}</b></span>
    <span class="lad-low" style="left:{low:.2f}%"><b>Low {pct(ev["later_low"], 0)}{so_far}</b></span>
  </div>
  <div class="lad-foot">Signal on {fmt_date(ev["date"])} at {usd(ev["price"])}. The price then fell another <strong>{abs(further) * 100:.0f}%</strong>{so_far}.</div>
  {early_html}
</div>''')
    return "\n".join(rows)


def record_summary(cycle) -> str:
    exits = _cycle_exits(cycle)
    finals = [abs(f["from_high"]) * 100 for f, _ in exits]
    n_early = sum(len(e) for _, e in exits)
    return (f"Low scores have been the best time to buy: every bottom scored under 12. For selling, the exit signal "
            f"(weekly close below the 50-day MA) got out {min(finals):.0f}–{max(finals):.0f}% below each cycle top and avoided most "
            f"of the bear market that followed. It also fired {n_early} times before a final top; with each signal selling only a slice, "
            f"those early sales cost some upside rather than the whole position. Only four cycles exist to test on.")


def macro_tiles(macro) -> str:
    if not macro:
        return '<p class="note">Macro data unavailable today.</p>'
    rows = []
    for m in macro:
        head = f'<div><div class="m-label">{e(m["label"])}</div><div class="m-src">{e(m["source"])}</div></div>'
        if "error" in m:
            rows.append(f'<div class="mrow">{head}<span class="muted small">unavailable today</span></div>')
            continue
        ch = m["change_30d"]
        if m["unit"] == "%":
            val, chs = f'{m["value"]:.2f}%', ("" if ch is None else f'{ch * 100:+.0f} bp')
        else:
            val, chs = f'{m["value"]:.2f}', ("" if ch is None else f'{ch:+.2f}')
        cls = "flat" if ch is None or abs(ch) < 1e-9 else ("up" if ch > 0 else "down")
        note = f' · {e(m["note"])}' if m.get("note") else ""
        rows.append(f'<div class="mrow">{head}<div class="m-val"><strong>{val}</strong>'
                    f'<span class="m-chg {cls}">{chs or "–"} <em>1M</em></span>'
                    f'<span class="m-src">{fmt_date(m["date"])}{note}</span></div></div>')
    return "".join(rows)


# ---------------------------------------------------------------- dashboard
def dashboard(cycle, news, brief, macro, spot, generated_at: str, market: dict) -> str:
    overview, items, research = news_items(cycle, news, brief)
    summ = brief_summary(cycle, news, brief, spot)
    z = cycle["zone"]
    price = spot or cycle["price_close"]
    as_of = datetime.fromisoformat(cycle["as_of"])
    today_long = datetime.now().strftime("%A, %-d %B %Y")
    hist = [[x["d"], x["p"], x["s"], x["w"], x["r"], x["m"]] for x in cycle["history"]]
    data_json = json.dumps({"h": hist, "zones": [[u, ZONE_COLORS[k], l] for u, k, l, _ in ZONES],
                            "exits": [[f["date"], f["price"], 1] for f, _ in _cycle_exits(cycle)]
                                     + [[x["date"], x["price"], 0] for _, ea in _cycle_exits(cycle) for x in ea]}).replace("</", "<\\/")
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
      <div class="eyebrow">BTC / USD <span class="chart-hint">▤ Tap price for chart</span></div>
      <div class="price price-btn" data-open-chart="usd" role="button" tabindex="0" aria-label="Open BTC/USD chart"><span data-live="usd">{usd(price)}</span></div>
      <div class="deltas">{delta(cycle["change_1d"])}<span class="dl">24h</span>{delta(cycle["change_30d"])}<span class="dl">30d</span></div>
      {chf_block(cycle, market.get("chf"))}
      {facts_table(cycle, price, market)}
      <div class="h-note">{"Live spot via Coinbase" if spot else "Daily close"} · on-chain data to {as_of:%-d %b}</div>
    </div>
    <div class="h-gauge">
      <div class="eyebrow">Cycle score</div>
      {gauge_svg(cycle["score"])}
      <div class="zone-pill" style="--zc:{ZONE_COLORS[z["key"]]}"><span></span>{e(z["label"])}</div>
      <div class="h-action">{e(playbook_action(z))}</div>
      <div class="h-exit">Exit signal: <b>{e(cycle["exit"]["label"])}</b></div>
    </div>
    <div class="h-summary">
      <div class="eyebrow">Today in 30 seconds</div>
      <ul class="tldr">
        <li><span class="ico">◆</span>{e(summ["market"])}</li>
        <li><span class="ico">◆</span>{e(summ["score"])}</li>
        {f'<li><span class="ico">◆</span>Market mood: {e(market["mood"]["label"])} ({market["mood"]["value"]:.0f}/100). {e(market["interpretation"][0]) if market["interpretation"] else ""}</li>' if market["mood"].get("value") is not None else ""}
      </ul>
      <div class="tldr-sub">In the news</div>
      <ul class="tldr news">{news_bullets}</ul>
    </div>
  </div>
</section>

<nav class="tabs"><a href="#chart" onclick="event.preventDefault();window.openChart&&openChart('usd')">Chart</a><a href="#mood">Mood</a><a href="#network">Network</a><a href="#brief">Brief</a><a href="#indicators">Indicators</a><a href="#history">History</a><a href="#record">Track record</a></nav>

{mood_section(market)}

<section class="kpis">
  {exit_card(cycle)}
  <div class="kpi"><span class="eyebrow dark">Halving cycle</span><strong>{cycle["halving"]["months_since"]:.0f} months</strong>
    <p>{e(cycle["halving"]["phase"])}</p><em>Next ≈ {fmt_date(cycle["halving"]["next_est"])} · {cycle["halving"]["days_to_next"]} days</em></div>
  {mining_card(cycle)}
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
  <p class="note small">Both charts share one time axis; hover either to read the same date on both. Dashed lines mark past exit signals (fainter = early signal before the final top).</p>
  <h3 class="chart-title">Cycle score</h3>
  <div class="chart" id="c-score"></div>
  <div class="chart-head"><h3 class="chart-title">Price, exit line and long-run anchors <span class="meta-note">log scale</span></h3>
    <div class="legend" id="lg-price"></div></div>
  <div class="chart" id="c-price"></div>
</section>

<section class="panel" id="record">
  <div class="phead"><h2>Track record</h2><span class="meta-note">Since 2014 · how far to trust each signal</span></div>
  <div class="cols even record">
    <div>
      <h3>Buying: price one year after each score zone</h3>
      <p class="note small">Median change in BTC price 12 months later. Hover a bar for details.</p>
      <div class="zr">{zone_return_chart(cycle)}</div>
    </div>
    <div>
      <h3>Selling: exit signal at past cycle tops</h3>
      <p class="note small">Track runs from the top (0%) to −90%. <span class="key k-saved"></span> drop the exit signal avoided.</p>
      <div class="ladder">{exit_ladder(cycle)}</div>
    </div>
  </div>
  <div class="callout"><strong>In short.</strong> {e(record_summary(cycle))}</div>
</section>

<footer>
  <p><strong>Sources.</strong> Coin Metrics Community API (price, market cap, MVRV, miner issuance, hashrate) · Coinbase (spot) ·
  New York Fed, US Treasury, ECB reference rates (macro) · Federal Reserve, SEC, Bitcoin Optech (T1) · Coin Metrics research (T2) · Reuters, Bloomberg, FT, WSJ, CNBC, AP,
  CoinDesk, The Block, Decrypt (T3).</p>
  <p><strong>Noise filter.</strong> Price predictions, altcoins, sponsored content and topic pages are removed; duplicate stories are
  merged; items are ranked by source tier, topic and corroboration. {news["scanned"]} items passed the first filter today.</p>
  {f"<p>Feeds unavailable today:</p><ul>{failures}</ul>" if failures else ""}
  <p>Generated {e(generated_at)}. This page applies fixed, published rules to public data. It is not personalised financial advice.</p>
</footer>
'''
    css, modal_html, script = chart_view.assets(market.get("ta"))
    w_head, w_css, w_html, w_js = webapp_view.assets(datetime.now().astimezone().isoformat())
    return (PAGE.replace("{{BODY}}", body + modal_html).replace("{{DATA}}", data_json)
            .replace("/*{{CHART_CSS}}*/", css).replace("<!--{{CHART_JS}}-->", script)
            .replace("<!--{{WEBAPP_HEAD}}-->", w_head).replace("/*{{WEBAPP_CSS}}*/", w_css)
            .replace("</main>", "</main>" + w_html, 1).replace("<!--{{WEBAPP_JS}}-->", w_js))


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bitcoin Daily</title>
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="BTC Daily"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0e0f11"><meta name="robots" content="noindex">
<!--{{WEBAPP_HEAD}}-->
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light;--page:#f4f3ef;--surface:#ffffff;--surface2:#faf9f6;--ink:#0d0d0e;--ink2:#4e4d49;--muted:#8b8982;
--grid:#ebe9e3;--axis:#cfcdc5;--ring:rgba(13,13,14,.08);--shadow:0 1px 2px rgba(16,17,19,.04),0 10px 30px -12px rgba(16,17,19,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--wash:rgba(13,13,14,.035);--pattern:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260' viewBox='0 0 260 260'%3E%3Cg fill='none' stroke='%23b8650a' stroke-opacity='0.10' stroke-width='1.3'%3E%3Crect x='16' y='34' width='36' height='26' rx='6'/%3E%3Crect x='84' y='34' width='36' height='26' rx='6'/%3E%3Cpath d='M52 47h32'/%3E%3Cpath d='M120 47h22'/%3E%3Ccircle cx='146' cy='47' r='2.5'/%3E%3Crect x='150' y='176' width='36' height='26' rx='6'/%3E%3Crect x='218' y='176' width='36' height='26' rx='6'/%3E%3Cpath d='M186 189h32'/%3E%3Cpath d='M150 189h-22'/%3E%3Ccircle cx='124' cy='189' r='2.5'/%3E%3C/g%3E%3Cg fill='%23b8650a' fill-opacity='0.07' font-family='Helvetica,Arial,sans-serif' font-weight='700'%3E%3Ctext x='182' y='104' font-size='38' transform='rotate(-12 192 92)'%3E%E2%82%BF%3C/text%3E%3Ctext x='40' y='226' font-size='24' transform='rotate(10 48 218)'%3E%E2%82%BF%3C/text%3E%3C/g%3E%3C/svg%3E");--bandop:.16;--up:#0b7a2e;--down:#c23b3b;--btc:#f7931a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0a0a0b;--surface:#151517;--surface2:#1b1b1e;--ink:#f2f1ed;
--ink2:#c3c2b9;--muted:#8d8b84;--grid:#26262a;--axis:#36363b;--ring:rgba(255,255,255,.08);--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px -12px rgba(0,0,0,.5);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--wash:rgba(255,255,255,.045);--pattern:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260' viewBox='0 0 260 260'%3E%3Cg fill='none' stroke='%23f7931a' stroke-opacity='0.09' stroke-width='1.3'%3E%3Crect x='16' y='34' width='36' height='26' rx='6'/%3E%3Crect x='84' y='34' width='36' height='26' rx='6'/%3E%3Cpath d='M52 47h32'/%3E%3Cpath d='M120 47h22'/%3E%3Ccircle cx='146' cy='47' r='2.5'/%3E%3Crect x='150' y='176' width='36' height='26' rx='6'/%3E%3Crect x='218' y='176' width='36' height='26' rx='6'/%3E%3Cpath d='M186 189h32'/%3E%3Cpath d='M150 189h-22'/%3E%3Ccircle cx='124' cy='189' r='2.5'/%3E%3C/g%3E%3Cg fill='%23f7931a' fill-opacity='0.07' font-family='Helvetica,Arial,sans-serif' font-weight='700'%3E%3Ctext x='182' y='104' font-size='38' transform='rotate(-12 192 92)'%3E%E2%82%BF%3C/text%3E%3Ctext x='40' y='226' font-size='24' transform='rotate(10 48 218)'%3E%E2%82%BF%3C/text%3E%3C/g%3E%3C/svg%3E");--bandop:.22;--up:#2fbf5b;--down:#ec6b6b}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0a0a0b;--surface:#151517;--surface2:#1b1b1e;--ink:#f2f1ed;--ink2:#c3c2b9;--muted:#8d8b84;
--grid:#26262a;--axis:#36363b;--ring:rgba(255,255,255,.08);--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px -12px rgba(0,0,0,.5);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--wash:rgba(255,255,255,.045);--pattern:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260' viewBox='0 0 260 260'%3E%3Cg fill='none' stroke='%23f7931a' stroke-opacity='0.09' stroke-width='1.3'%3E%3Crect x='16' y='34' width='36' height='26' rx='6'/%3E%3Crect x='84' y='34' width='36' height='26' rx='6'/%3E%3Cpath d='M52 47h32'/%3E%3Cpath d='M120 47h22'/%3E%3Ccircle cx='146' cy='47' r='2.5'/%3E%3Crect x='150' y='176' width='36' height='26' rx='6'/%3E%3Crect x='218' y='176' width='36' height='26' rx='6'/%3E%3Cpath d='M186 189h32'/%3E%3Cpath d='M150 189h-22'/%3E%3Ccircle cx='124' cy='189' r='2.5'/%3E%3C/g%3E%3Cg fill='%23f7931a' fill-opacity='0.07' font-family='Helvetica,Arial,sans-serif' font-weight='700'%3E%3Ctext x='182' y='104' font-size='38' transform='rotate(-12 192 92)'%3E%E2%82%BF%3C/text%3E%3Ctext x='40' y='226' font-size='24' transform='rotate(10 48 218)'%3E%E2%82%BF%3C/text%3E%3C/g%3E%3C/svg%3E");--bandop:.22;--up:#2fbf5b;--down:#ec6b6b}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background-color:var(--page);background-image:radial-gradient(1100px 600px at 100% 0%,rgba(247,147,26,.10),transparent 60%),
 radial-gradient(900px 600px at 0% 100%,rgba(57,135,229,.07),transparent 60%),var(--pattern);background-attachment:fixed,fixed,scroll;color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;
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
.hero{position:relative;overflow:hidden}.hero>*{position:relative;z-index:1}
.hero::after{content:"₿";position:absolute;right:-40px;top:-90px;font-size:400px;font-weight:800;line-height:1;color:rgba(247,147,26,.07);
 transform:rotate(-14deg);pointer-events:none;z-index:0}
.hero::before{content:"";position:absolute;left:0;right:0;bottom:0;height:70px;z-index:0;pointer-events:none;opacity:.5;
 background:repeating-linear-gradient(90deg,transparent 0 22px,rgba(247,147,26,.16) 22px 58px,transparent 58px 62px,rgba(247,147,26,.16) 62px 64px,transparent 64px 84px);
 -webkit-mask:linear-gradient(transparent 40%,#000 41%,#000 59%,transparent 60%);mask:linear-gradient(transparent 40%,#000 41%,#000 59%,transparent 60%)}
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
.h-facts2{width:100%;margin-top:14px;border-collapse:collapse;font-size:14px}
.h-facts2 th,.h-facts2 td{padding:8px 0;border-top:1px solid rgba(255,255,255,.07);text-align:right;vertical-align:baseline}
.h-facts2 tr:first-child th{border-top:0;padding:0 0 4px;font-size:11px;font-weight:600;letter-spacing:.1em;color:#7d7b74}
.h-facts2 th{border-bottom:0;text-transform:none}
.h-facts2 th[scope=row]{text-align:left;font-weight:400;color:#a9a79f;padding-right:8px;font-size:14px;letter-spacing:0}
.h-facts2 td{padding-left:14px;white-space:nowrap}
.h-facts2 strong{font-weight:600;font-variant-numeric:tabular-nums}
.h-facts2 em{display:block;font-style:normal;color:#9c9a92;font-size:11.5px;font-variant-numeric:tabular-nums}
.h-facts{margin-top:18px;display:flex;flex-direction:column}
.h-facts>div{display:grid;grid-template-columns:1fr auto 52px;gap:10px;padding:8px 0;border-top:1px solid rgba(255,255,255,.07);font-size:14px;align-items:baseline}
.h-facts span{color:#a9a79f}.h-facts strong{font-weight:600;font-variant-numeric:tabular-nums}.h-facts em{font-style:normal;color:#9c9a92;font-size:12px;text-align:right;font-variant-numeric:tabular-nums}
.chf{margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,255,255,.07)}
.chf-price{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}
.chf-price .cur{font-size:12px;font-weight:600;letter-spacing:.08em;color:#9c9a92}
.fx{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px;color:#b9b7af;margin-top:6px;font-variant-numeric:tabular-nums}
.fx b{color:#f3f2ee;font-weight:600;margin-right:4px}
.fxchg{font-size:12px;font-weight:600;border-radius:999px;padding:2px 8px}
.fxchg.up{color:#4ade80;background:rgba(74,222,128,.12)}.fxchg.down{color:#f87171;background:rgba(248,113,113,.12)}
.fx-note{font-size:11.5px;color:#7d7b74;margin-top:4px}
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

.kpis{display:grid;grid-template-columns:2fr 1fr;gap:18px}
.mining-card{grid-column:1/-1;scroll-margin-top:64px}
#mood{scroll-margin-top:64px}
.mine-grid{display:grid;grid-template-columns:1fr 1.3fr;gap:28px;margin:8px 0 6px}
.mstat{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.mstat strong{font-size:28px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.mstat span{font-size:12.5px;color:var(--muted)}
.cost-scale{position:relative;height:12px;margin:34px 0 30px;border-radius:6px;background:var(--wash)}
.cs-range{position:absolute;top:0;bottom:0;border-radius:6px;background:color-mix(in srgb,var(--btc) 30%,transparent)}
.cs-tick{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink2)}
.cs-tick b{position:absolute;top:22px;left:50%;transform:translateX(-50%);font-size:11.5px;font-weight:600;white-space:nowrap;color:var(--ink2)}
.cs-tick.allin{background:var(--down)}.cs-tick.allin b{color:var(--down)}
.cs-price{position:absolute;top:-6px;bottom:-6px;width:4px;margin-left:-2px;border-radius:2px;background:var(--ink);box-shadow:0 0 0 2px var(--surface)}
.cs-price b{position:absolute;bottom:26px;left:50%;transform:translateX(-50%);font-size:12px;white-space:nowrap}
.cs-legend{font-size:11.5px;color:var(--muted)}.cs-legend .k{display:inline-block;width:14px;height:8px;border-radius:3px;margin-right:6px;vertical-align:0}
.cs-legend .k.range{background:color-mix(in srgb,var(--btc) 30%,transparent)}
.zchip{font-size:11px;font-weight:700;border-radius:6px;padding:1px 7px;margin-right:4px;background:var(--wash)}.zchip.warn{color:var(--btc)}
.exit-status{display:flex;align-items:center;gap:10px;margin:6px 0 2px}.exit-status strong{font-size:20px;letter-spacing:-.01em}
.exit-icon{font-size:20px;line-height:1}.ex-fired .exit-icon,.ex-armed .exit-icon{color:var(--down)}.ex-closed .exit-icon{color:var(--muted)}.ex-watch .exit-icon{color:var(--btc)}
.ex-fired,.ex-armed{border-color:color-mix(in srgb,var(--down) 45%,transparent)}
.exit-rules{margin:4px 0 10px;padding-left:18px;font-size:13px;color:var(--ink2)}.exit-rules li{margin:2px 0}
.h-exit{font-size:12px;color:#9c9a92;margin-top:6px}.h-exit b{color:#e6e4de;font-weight:600}
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
.m-label{font-weight:500}.m-src{font-size:11.5px;color:var(--muted)}
.m-val{display:flex;flex-direction:column;align-items:flex-end;text-align:right}.m-val strong{font-size:18px;font-variant-numeric:tabular-nums}
.m-chg{font-size:12px;font-variant-numeric:tabular-nums;color:var(--ink2)}.m-chg em{font-style:normal;color:var(--muted)}
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
.record h3{margin-top:4px}
.zr{display:flex;flex-direction:column;gap:14px;margin-top:12px}
.zr-row{position:relative;display:grid;grid-template-columns:170px 1fr;column-gap:12px;align-items:center;outline:none}
.zr-label{font-size:13.5px;font-weight:500;display:flex;align-items:center;flex-wrap:wrap}.zr-band{font-size:11px;color:var(--muted);margin-left:6px;font-variant-numeric:tabular-nums}
.zr-track{position:relative;height:22px}
.zr-zero{position:absolute;top:-4px;bottom:-4px;width:1px;background:var(--axis)}
.zr-bar{position:absolute;top:3px;height:16px;border-radius:4px}
.zr-val{position:absolute;top:2px;font-size:13px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.zr-sub{grid-column:2;font-size:11.5px;color:var(--muted);margin-top:1px}
.zr-row:hover .zr-bar,.zr-row:focus .zr-bar{filter:brightness(1.08)}
[data-tip]:hover::after,[data-tip]:focus::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 6px);z-index:3;max-width:320px;
 background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:8px 11px;font-size:12px;line-height:1.45;color:var(--ink);box-shadow:0 8px 24px rgba(0,0,0,.16)}
.ladder{display:flex;flex-direction:column;gap:18px;margin-top:12px}
.lad-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;font-size:13.5px}
.lad-chips{margin-left:auto;display:flex;gap:6px}.chip-s{font-size:11.5px;color:var(--ink2);border:1px solid var(--ring);border-radius:999px;padding:1px 8px;background:var(--surface2);white-space:nowrap}
.lad-track{position:relative;height:30px;margin:26px 0 6px;border-radius:6px;background:var(--wash)}
.lad-fall{position:absolute;left:0;top:0;bottom:0;border-radius:6px 0 0 6px;background:color-mix(in srgb,var(--down) 18%,transparent)}
.lad-saved,.k-saved{background:repeating-linear-gradient(135deg,color-mix(in srgb,var(--down) 55%,transparent) 0 3px,transparent 3px 7px)}
.lad-saved{position:absolute;top:0;bottom:0}
.k-saved{display:inline-block;width:14px;height:10px;border-radius:2px;vertical-align:-1px;border:1px solid color-mix(in srgb,var(--down) 55%,transparent)}
.lad-mark{position:absolute;top:-24px;bottom:0;transform:translateX(-1px)}
.lad-mark i{position:absolute;left:0;top:20px;bottom:0;width:3px;border-radius:2px;background:var(--ink)}
.lad-mark b{position:absolute;left:-2px;top:0;font-size:12px;white-space:nowrap}
.lad-low{position:absolute;top:0;bottom:0;border-left:2px solid var(--down)}
.lad-low b{position:absolute;right:6px;top:7px;font-size:12px;white-space:nowrap;color:var(--ink)}
.lad-foot{font-size:12.5px;color:var(--ink2)}
.lad-early{font-size:12.5px;color:var(--ink2);margin-top:6px;padding:6px 10px;border-radius:8px;background:var(--surface2);border:1px dashed var(--ring)}
.sub{margin:22px 0 10px;font-size:15px}
.mood-head{display:flex;align-items:center;gap:14px}.mood-num{font-size:48px;font-weight:700;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.mood-label{display:flex;align-items:center;gap:8px;font-size:18px;font-weight:650}.mood-label span{width:12px;height:12px;border-radius:50%}
.mscale{position:relative;display:flex;gap:2px;height:10px;margin:14px 0 4px}.mscale span{border-radius:3px}
.mscale i{position:absolute;top:-5px;width:4px;height:20px;margin-left:-2px;background:var(--ink);border-radius:2px;box-shadow:0 0 0 2px var(--surface)}
.mscale-labels{display:flex;font-size:10.5px;color:var(--muted)}.mscale-labels span{text-align:center}
.mparts{margin-top:14px;display:flex;flex-direction:column;gap:10px}
.mp-top{display:flex;justify-content:space-between;gap:10px;font-size:13.5px}.mp-detail{color:var(--ink2);font-variant-numeric:tabular-nums}
.mp-bar{position:relative;height:6px;border-radius:3px;background:linear-gradient(90deg,#2f6fd0,#7fb2f0,#a9a8a0,#ee9e9d,#e34948);opacity:.35;margin-top:5px}
.mp-bar span{position:absolute;top:-3px;width:12px;height:12px;margin-left:-6px;border-radius:50%;border:2px solid var(--surface);opacity:1}
.mparts .mp-bar{opacity:1;background:var(--wash)}
.read{background:var(--surface2);border:1px solid var(--ring);border-radius:14px;padding:14px 18px}
.read-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}.read h3{margin:0}
.ai-tag{font-size:11px;color:var(--muted);border:1px solid var(--ring);border-radius:999px;padding:2px 8px}
.read ul{margin:10px 0 6px;padding-left:18px}.read li{margin:6px 0;font-size:14.5px}
.flow-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.fcard.wide{grid-column:1/-1}
.holders summary{list-style:none;cursor:pointer;display:flex;flex-direction:column;gap:10px;outline:none}
.holders summary::-webkit-details-marker{display:none}
.h-sum-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
.h-toggle{font-size:13px;font-weight:600;color:var(--s1);white-space:nowrap}.h-toggle .t-close{display:none}
.holders[open] .h-toggle .t-open{display:none}.holders[open] .h-toggle .t-close{display:inline}
.holders summary:hover .h-toggle,.holders summary:focus-visible .h-toggle{text-decoration:underline}
.holders[open] summary{margin-bottom:6px}
.hchips{display:flex;flex-wrap:wrap;gap:8px}.hchip{font-size:12.5px;border:1px solid var(--ring);border-radius:999px;padding:3px 10px;background:var(--surface);font-variant-numeric:tabular-nums}
.tr-table tr.extra{display:none}.tr-table.show-all tr.extra{display:table-row}
.more-btn{font:inherit;font-size:12.5px;font-weight:600;color:var(--s1);background:none;border:0;padding:4px 0;cursor:pointer}
.tr-table tr.grp td{padding-top:14px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--ink2);border-bottom:1px solid var(--axis)}
.tr-table tr.grp td span{float:right;font-weight:500;letter-spacing:0;text-transform:none;color:var(--muted)}
.pctcell{display:flex;align-items:center;justify-content:flex-end;gap:8px}
.pbar{display:inline-block;width:90px;height:6px;border-radius:3px;background:var(--wash);overflow:hidden}.pbar i{display:block;height:100%;background:var(--btc);border-radius:3px}
.est{position:relative;font-size:10.5px;font-weight:600;color:var(--muted);border:1px dashed var(--ring);border-radius:5px;padding:0 5px;margin-left:4px;cursor:help;outline:none}
.fcard{border:1px solid var(--ring);border-radius:14px;padding:16px;background:var(--surface2);display:flex;flex-direction:column;gap:6px;min-width:0}
.fcard em{font-style:normal;font-size:11.5px;color:var(--muted);margin-top:auto;padding-top:6px}
.fbig{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}.fbig strong{font-size:24px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.fbig span{font-size:12.5px;color:var(--muted)}
.pos{color:var(--s1)}.neg{color:var(--down)}
.etf-cols{display:flex;gap:3px;height:110px;margin-top:8px;position:relative}
.ec{position:relative;flex:1;display:grid;grid-template-rows:1fr 1fr 14px;outline:none}
.ec-up{display:flex;align-items:flex-end;border-bottom:1px solid var(--axis)}.ec-dn{display:flex;align-items:flex-start}
.ec-bar{display:block;width:100%;border-radius:3px}.ec-bar.in{background:var(--s1)}.ec-bar.out{background:var(--down)}
.ec:hover .ec-bar,.ec:focus .ec-bar{filter:brightness(1.15)}
.ec-lab{font-size:9.5px;color:var(--muted);white-space:nowrap;text-align:center}
.ec[data-tip]:hover::after,.ec[data-tip]:focus::after{left:50%;transform:translateX(-50%);top:auto;bottom:calc(100% + 4px);width:max-content;max-width:240px}
.ec-key{font-size:11.5px;color:var(--muted)}.ec-key .k{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 4px 0 6px;vertical-align:-1px}
.ec-key .k.in{background:var(--s1)}.ec-key .k.out{background:var(--down)}
.movers{margin-top:6px}.mover{display:flex;justify-content:space-between;font-size:13.5px;padding:4px 0;border-top:1px solid var(--grid);font-variant-numeric:tabular-nums}
.spark{width:100%;height:44px;margin:6px 0}
.kv2{display:flex;justify-content:space-between;font-size:13.5px;padding:3px 0;border-top:1px solid var(--grid);font-variant-numeric:tabular-nums}
.tr-table{font-size:13px}.tr-table td,.tr-table th{padding:5px 4px}
.tone{font-size:11px;font-weight:700;border-radius:6px;padding:2px 8px}
.t-bull{color:var(--s1);background:color-mix(in srgb,var(--s1) 12%,transparent)}.t-bear{color:var(--down);background:color-mix(in srgb,var(--down) 12%,transparent)}
.t-neu{color:var(--ink2);background:var(--wash)}
.agenda{list-style:none;margin:8px 0 0;padding:8px 12px;border-radius:10px;background:var(--surface2);border:1px solid var(--ring);font-size:12.5px;color:var(--ink2)}
.agenda li{margin:2px 0;padding-left:14px;position:relative}.agenda li:not(.ag-h)::before{content:"›";position:absolute;left:2px;color:var(--muted)}
.agenda .ag-h{padding:0;font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
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
@media (max-width:1020px){.kpis{grid-template-columns:1fr 1fr}.exit-card{grid-column:1/-1}.mine-grid{grid-template-columns:1fr}}
@media (max-width:700px){.flow-grid{grid-template-columns:1fr}.pbar{width:40px}}
@media (max-width:860px){.cols,.cols.even{grid-template-columns:1fr}}
@media (max-width:600px){.tabs{max-width:100%;overflow-x:auto;scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}.hero::after{font-size:240px;right:-30px;top:-40px;color:rgba(247,147,26,.06)}.tabs{flex-wrap:nowrap;gap:2px}.tabs a{padding:6px 9px;font-size:12.5px;white-space:nowrap}.kpis{grid-template-columns:1fr}.zr-row{grid-template-columns:1fr}.zr-sub{grid-column:1}.lad-chips{margin-left:0}}
@media (max-width:600px){.hero{padding:18px}.hero-grid{grid-template-columns:1fr;gap:22px}.price{font-size:44px}
 .views{grid-template-columns:1fr}.ind-grid{grid-template-columns:1fr}.panel{padding:18px}.chip{display:none}}
/*{{CHART_CSS}}*/
/*{{WEBAPP_CSS}}*/
</style></head><body><main>
{{BODY}}
</main>
<script>
const D={{DATA}};
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const rows=D.h.map(r=>({t:Date.parse(r[0]),d:r[0],p:r[1],s:r[2],w:r[3],r:r[4],m:r[5]}));
const exits=D.exits.map(x=>({t:Date.parse(x[0]),p:x[1],final:!!x[2]}));
const fmtUsd=v=>v==null?'–':'$'+Math.round(v).toLocaleString('en-US');
const fmtK=v=>v>=1000?'$'+(v/1000).toFixed(v>=1e5?0:1)+'k':'$'+Math.round(v);
const fmtDate=t=>new Date(t).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const NS='http://www.w3.org/2000/svg';
let range='4y';const charts=[];
function el(tag,attrs,parent){const n=document.createElementNS(NS,tag);for(const k in attrs)n.setAttribute(k,attrs[k]);if(parent)parent.appendChild(n);return n}
function zoneOf(s){for(const z of D.zones)if(s<z[0])return z;return D.zones[D.zones.length-1]}
function visible(){const last=rows[rows.length-1].t,span={all:Infinity,'4y':4*365.25*864e5,'1y':365.25*864e5}[range];return rows.filter(r=>last-r.t<=span)}

// Every chart uses the SAME data window and the SAME left/right margins, so a date sits at the same x in each.
function chart(id,cfg){
  const box=document.getElementById(id);box.innerHTML='';
  const W=box.clientWidth,H=box.clientHeight,gutter=W>=560,m={l:58,r:gutter?132:12,t:14,b:26};
  const data=visible(),x0=data[0].t,x1=data[data.length-1].t,X=t=>m.l+(t-x0)/(x1-x0)*(W-m.l-m.r);
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
    t.textContent=cfg.log?fmtK(v):v}
  const xt=[];
  if(range==='1y'){const d=new Date(x0);d.setUTCDate(1);while(d.getTime()<=x1){d.setUTCMonth(d.getUTCMonth()+1);if(d.getUTCMonth()%3===0&&d.getTime()<=x1)xt.push([d.getTime(),d.toLocaleDateString('en-GB',{month:'short',year:'2-digit',timeZone:'UTC'})])}}
  else{const step=range==='all'?2:1;for(let y=new Date(x0).getUTCFullYear()+1;y<=new Date(x1).getUTCFullYear();y+=step)xt.push([Date.UTC(y,0,1),String(y)])}
  for(const [t,l] of xt){el('line',{x1:X(t),x2:X(t),y1:H-m.b,y2:H-m.b+4,stroke:css('--axis')},svg);
    const tx=el('text',{x:X(t),y:H-6,'text-anchor':'middle','font-size':11,fill:css('--muted'),'data-tick':l},svg);tx.textContent=l}
  el('line',{x1:m.l,x2:W-m.r,y1:H-m.b,y2:H-m.b,stroke:css('--axis')},svg);
  // past exit signals: same dashed line on every chart
  for(const ex of exits){if(ex.t<x0||ex.t>x1)continue;const x=X(ex.t);
    el('line',{x1:x,x2:x,y1:m.t,y2:H-m.b,stroke:css('--down'),'stroke-dasharray':ex.final?'4 3':'2 4','stroke-width':ex.final?1.5:1,'stroke-opacity':ex.final?1:.55},svg);
    if(ex.final){const lb=el('text',{x:x+4,y:m.t+2,'font-size':10,'font-weight':600,fill:css('--ink2')},svg);lb.textContent='Exit signal'}
    if(cfg.log)el('path',{d:`M${x-5} ${Y(ex.p)-11}L${x+5} ${Y(ex.p)-11}L${x} ${Y(ex.p)-3}Z`,fill:css('--down'),'fill-opacity':ex.final?1:.5},svg)}
  for(const s of cfg.series){let d='',pen=false;for(const r of data){const v=r[s.k];if(v==null){pen=false;continue}d+=(pen?'L':'M')+X(r.t).toFixed(1)+' '+Y(v).toFixed(1);pen=true}
    el('path',{d,fill:'none',stroke:css(s.c),'stroke-width':s.w||2,'stroke-linejoin':'round','stroke-linecap':'round'},svg)}
  // direct end labels in the right gutter (de-overlapped)
  if(cfg.endLabels&&gutter){const lr=data[data.length-1];
    const labs=cfg.series.filter(s=>lr[s.k]!=null).map(s=>({s,y:Y(lr[s.k])})).sort((a,b)=>a.y-b.y);
    for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<15)labs[i].y=labs[i-1].y+15;
    for(const l of labs){el('rect',{x:W-m.r+8,y:l.y-4,width:8,height:3,rx:1.5,fill:css(l.s.c)},svg);
      const t=el('text',{x:W-m.r+20,y:l.y+1,'font-size':11,fill:css('--ink2')},svg);t.textContent=l.s.short+' '+fmtK(lr[l.s.k])}}
  // hover (synced across charts)
  const vline=el('line',{y1:m.t,y2:H-m.b,stroke:css('--muted'),'stroke-dasharray':'3 3',visibility:'hidden'},svg);
  const dots=cfg.series.map(s=>el('circle',{r:4,fill:css(s.c),stroke:css('--surface'),'stroke-width':2,visibility:'hidden'},svg));
  const tip=document.createElement('div');tip.className='tip';box.appendChild(tip);
  const hit=el('rect',{x:m.l,y:0,width:W-m.l-m.r,height:H,fill:'transparent'},svg);
  function nearest(t){let a=0,b=data.length-1;while(b-a>1){const mid=(a+b)>>1;if(data[mid].t<t)a=mid;else b=mid}return Math.abs(data[a].t-t)<Math.abs(data[b].t-t)?data[a]:data[b]}
  function show(t){const r=nearest(t),x=X(r.t);
    vline.setAttribute('x1',x);vline.setAttribute('x2',x);vline.setAttribute('visibility','visible');
    let h='<b>'+fmtDate(r.t)+'</b>';
    cfg.series.forEach((s,i)=>{const v=r[s.k];if(v==null){dots[i].setAttribute('visibility','hidden');return}
      dots[i].setAttribute('cx',x);dots[i].setAttribute('cy',Y(v));dots[i].setAttribute('visibility','visible');
      h+='<div class="r"><span>'+s.label+'</span><b>'+s.f(v)+'</b></div>'});
    if(cfg.bands)h+='<div class="r"><span>Zone</span><b>'+zoneOf(r.s)[2]+'</b></div>';
    tip.innerHTML=h;tip.style.display='block';const tw=tip.offsetWidth;tip.style.left=(x+12+tw>W-m.r?x-12-tw:x+12)+'px';tip.style.top='8px'}
  function hide(){vline.setAttribute('visibility','hidden');dots.forEach(d=>d.setAttribute('visibility','hidden'));tip.style.display='none'}
  function move(ev){const rect=svg.getBoundingClientRect();const px=(ev.touches?ev.touches[0].clientX:ev.clientX)-rect.left;
    const t=x0+(px-m.l)/(W-m.l-m.r)*(x1-x0);charts.forEach(c=>c.show(t))}
  hit.addEventListener('mousemove',move);hit.addEventListener('touchmove',move,{passive:true});
  hit.addEventListener('mouseleave',()=>charts.forEach(c=>c.hide()));
  return {show,hide};
}
const priceSeries=[{k:'p',label:'BTC price',short:'BTC',c:'--s1',f:fmtUsd},{k:'m',label:'50-day MA (exit line)',short:'50D',c:'--s4',f:fmtUsd,w:1.75},
  {k:'w',label:'200-week MA',short:'200W',c:'--s2',f:fmtUsd},{k:'r',label:'Realized price',short:'Realized',c:'--s3',f:fmtUsd}];
function legend(){document.getElementById('lg-price').innerHTML=priceSeries.map(s=>'<span><i style="background:'+css(s.c)+'"></i>'+s.label+'</span>').join('')}
function draw(){
  charts.length=0;
  charts.push(chart('c-score',{series:[{k:'s',label:'Cycle score',c:'--ink',f:v=>v.toFixed(0)}],bands:true,aria:'Cycle score over time with zone bands'}));
  charts.push(chart('c-price',{series:priceSeries,log:true,endLabels:true,aria:'BTC price, 50-day and 200-week moving averages and realized price, log scale'}));
  legend();
}
document.querySelectorAll('.ranges button').forEach(b=>b.addEventListener('click',()=>{range=b.dataset.r;
  document.querySelectorAll('.ranges button').forEach(x=>x.classList.toggle('on',x===b));draw()}));
let rt;addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120)});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
document.fonts&&document.fonts.ready.then(draw);
draw();
</script>
<!--{{CHART_JS}}-->
<!--{{WEBAPP_JS}}-->
</body></html>'''


# ---------------------------------------------------------------- email
def email_html(cycle, news, brief, spot, market=None) -> str:
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
    tldr = (bullet(summ["market"]) + bullet(summ["score"]) + bullet(f'Exit signal: {cycle["exit"]["label"]}. {cycle["exit"]["detail"]}', "#c23b3b")
            + (bullet(f'Market mood: {market["mood"]["label"]} ({market["mood"]["value"]:.0f}/100). '
                      + (market["interpretation"][0] if market["interpretation"] else ""), "#2f6fd0")
               if market and market["mood"].get("value") is not None else "")
            + "".join(bullet(p, "#a9a8a0") for p in summ["news"]))

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
data (Coin Metrics, Coinbase, New York Fed, US Treasury, ECB and the listed news sources), not personalised financial advice.</td></tr>
</table></td></tr></table></body></html>'''
