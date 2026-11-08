"""Who is actually buying or selling: institutional and large-holder flows, plus the Fear & Greed index.

All free, no API keys:
- US spot bitcoin ETF daily flows by fund (Farside Investors, farside.co.uk), in US$ millions
- BTC held on exchanges (Coin Metrics Community API)
- Holdings: ETFs/funds (bitcointreasuries.net), public companies and governments (CoinGecko public API);
  a daily snapshot is saved so 7/30-day changes build up
- Crypto Fear & Greed Index (alternative.me)
"""
import html
import json
import re
from datetime import date, datetime, timedelta

from common import DATA_DIR, http_get, http_json

TREASURY_SNAPSHOTS = DATA_DIR / "treasury_snapshots.json"


def _num(s: str):
    s = s.replace(",", "").strip()
    if s in ("", "-", "–"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


def etf_flows() -> dict:
    """Daily net flows (US$m) for each US spot bitcoin ETF over the last few weeks."""
    page = http_get("https://farside.co.uk/btc/", timeout=30).decode("utf-8", "replace")
    table = re.search(r'<table[^>]*class="[^"]*etf[^"]*"[^>]*>.*?</table>', page, re.S)
    if not table:
        raise ValueError("ETF flow table not found")
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S):
        rows.append([html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)])
    header = next(r for r in rows if "IBIT" in r)
    funds = [f for f in header[1:] if f]
    days = []
    for r in rows:
        try:
            d = datetime.strptime(r[0], "%d %b %Y").date()
        except (ValueError, IndexError):
            continue
        vals = {f: _num(v) for f, v in zip(funds, r[1:1 + len(funds)])}
        total = _num(r[len(funds) + 1]) if len(r) > len(funds) + 1 else None
        if total is None:  # day not reported yet
            continue
        days.append({"date": d.isoformat(), "total": total, "funds": vals})
    days.sort(key=lambda x: x["date"])
    if days:
        cutoff = (date.fromisoformat(days[-1]["date"]) - timedelta(days=6)).isoformat()
        last7 = [d for d in days if d["date"] >= cutoff]  # last 7 calendar days (5 trading days)
    else:
        last7 = []
    fund_7d = {f: sum((d["funds"].get(f) or 0) for d in last7) for f in funds}
    movers = sorted(((f, v) for f, v in fund_7d.items() if abs(v) >= 1), key=lambda x: -abs(x[1]))
    streak = 0
    for d in reversed(days):
        if streak == 0:
            streak = 1 if d["total"] > 0 else -1 if d["total"] < 0 else 0
            if streak == 0:
                break
        elif (d["total"] > 0) == (streak > 0) and d["total"] != 0:
            streak += 1 if streak > 0 else -1
        else:
            break
    return {
        "days": days,
        "last": days[-1] if days else None,
        "sum_7d": sum(d["total"] for d in last7),
        "trading_days_7d": len(last7),
        "sum_all": sum(d["total"] for d in days),
        "n_days": len(days),
        "streak": streak,              # +3 = three inflow days in a row, -2 = two outflow days
        "movers_7d": movers[:5],       # biggest fund moves over the last 7 days (US$m)
        "source": "Farside Investors",
    }


def exchange_flows() -> dict:
    """BTC held on exchanges. Falling balances usually mean holders are moving coins to long-term storage
    (accumulation); rising balances mean more coins are sitting where they can be sold.
    (Coin Metrics' free daily in/out flow figures are preliminary and don't reconcile with balances, so only
    the balance itself is used.)"""
    start = (date.today() - timedelta(days=75)).isoformat()
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc"
           f"&metrics=SplyExNtv&frequency=1d&start_time={start}&page_size=200")
    rows = [r for r in http_json(url)["data"] if r.get("SplyExNtv")]
    bal = [float(r["SplyExNtv"]) for r in rows]
    return {
        "date": rows[-1]["time"][:10],
        "balance": bal[-1],
        "change_7d": bal[-1] - bal[-8] if len(bal) > 7 else None,
        "change_30d": bal[-1] - bal[-31] if len(bal) > 30 else None,
        "change_30d_pct": bal[-1] / bal[-31] - 1 if len(bal) > 30 else None,
        "series": [[r["time"][:10], round(v)] for r, v in zip(rows[-60:], bal[-60:])],
        "source": "Coin Metrics",
    }


GOV_CACHE = DATA_DIR / "governments_cache.json"
MAX_SUPPLY = 21_000_000

# No live source exists for these. Published figures, shown with their source and date, and labelled as estimates.
STATIC_HOLDERS = [
    {"group": "Individuals (publicly disclosed)", "name": "Tim Draper", "country": "US", "btc": 29_656,
     "note": "Bought at the 2014 US Marshals auction; current holding not disclosed", "estimate": True},
    {"group": "Individuals (publicly disclosed)", "name": "Michael Saylor (personal)", "country": "US", "btc": 17_732,
     "note": "Disclosed Oct 2020; has said he holds more since", "estimate": True},
    {"group": "Lost & unmoved (estimates)", "name": "Satoshi Nakamoto (unmoved since 2010)", "country": None, "btc": 1_100_000,
     "note": "Estimate from early-mining analysis (Lerner, 'Patoshi pattern'); never moved", "estimate": True},
    {"group": "Lost & unmoved (estimates)", "name": "Lost coins (Chainalysis range 2.8M–3.8M)", "country": None, "btc": 3_300_000,
     "note": "Chainalysis 2020 estimate, midpoint shown; may overlap with Satoshi's coins", "estimate": True},
]


FUND_CACHE = DATA_DIR / "funds_cache.json"


def _fund_holdings() -> list[dict]:
    """BTC held by every bitcoin ETF / fund (US spot ETFs plus funds listed abroad), read from the data embedded in
    bitcointreasuries.net's public page. Cached for 20 hours."""
    import time
    if FUND_CACHE.exists() and time.time() - FUND_CACHE.stat().st_mtime < 20 * 3600:
        return json.loads(FUND_CACHE.read_text())
    page = http_get("https://bitcointreasuries.net/", timeout=40).decode("utf-8", "replace")
    m = re.search(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise ValueError("holdings data not found on bitcointreasuries.net")
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "FUND" and isinstance(o.get("holdings"), list):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    funds, seen = [], set()
    for f in found:
        btc = next((h.get("balance") for h in f["holdings"] if h.get("asset") == "BTC"), None)
        if not btc or f["name"] in seen:
            continue
        seen.add(f["name"])
        funds.append({"name": f["name"], "ticker": (f.get("ticker") or {}).get("symbol"),
                      "country": (f.get("country") or {}).get("alpha2"), "btc": float(btc)})
    funds.sort(key=lambda x: -x["btc"])
    if funds:
        FUND_CACHE.write_text(json.dumps(funds))
    return funds


def _coingecko(url: str):
    """CoinGecko's free API allows only a few calls a minute; wait and retry on HTTP 429."""
    import time
    for attempt in range(4):
        try:
            return http_json(url, timeout=30)
        except Exception as exc:
            if "429" not in str(exc) or attempt == 3:
                raise
            time.sleep(30)


def _government_holdings() -> list[dict]:
    """Government holdings from CoinGecko, one request per government (free tier is rate-limited, so requests are
    spaced out and the result is cached for 20 hours)."""
    import time
    if GOV_CACHE.exists() and time.time() - GOV_CACHE.stat().st_mtime < 20 * 3600:
        return json.loads(GOV_CACHE.read_text())
    ids = [g["id"] for g in _coingecko("https://api.coingecko.com/api/v3/entities/list?entity_type=government&per_page=100")]
    out = []
    for gid in ids:
        time.sleep(2.5)
        try:
            d = _coingecko(f"https://api.coingecko.com/api/v3/public_treasury/{gid}")
        except Exception:
            continue
        btc = next((h["amount"] for h in d.get("holdings", []) if h.get("coin_id") == "bitcoin"), None)
        if btc:
            out.append({"name": d["name"], "country": d.get("country"), "btc": btc})
    out.sort(key=lambda g: -g["btc"])
    if out:
        GOV_CACHE.write_text(json.dumps(out))
    return out


def treasuries() -> dict:
    """Largest holders in four groups: public companies and governments (live, CoinGecko) plus disclosed individuals and
    lost/unmoved coins (published estimates). 7/30-day changes come from locally saved daily snapshots."""
    d = _coingecko("https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin")
    try:
        govs = _government_holdings()
    except Exception as exc:
        print(f"[flows] government holdings unavailable: {exc}")
        govs = []
    try:
        funds = _fund_holdings()
    except Exception as exc:
        print(f"[flows] fund holdings unavailable: {exc}")
        funds = []
    today = date.today().isoformat()
    snaps = json.loads(TREASURY_SNAPSHOTS.read_text()) if TREASURY_SNAPSHOTS.exists() else {}
    snaps[today] = {**{c["name"]: c["total_holdings"] for c in d["companies"]}, **{g["name"]: g["btc"] for g in govs},
                    **{f["name"]: f["btc"] for f in funds}}
    for k in sorted(snaps)[:-120]:  # keep ~120 days
        del snaps[k]
    DATA_DIR.mkdir(exist_ok=True)
    TREASURY_SNAPSHOTS.write_text(json.dumps(snaps))

    def past(days_back):
        target = (date.today() - timedelta(days=days_back)).isoformat()
        older = [k for k in snaps if k <= target]
        return snaps[max(older)] if older else None

    p7, p30 = past(7), past(30)

    def row(group, name, country, btc, note=None, estimate=False):
        key = name.split(" (")[0] if group == "ETFs & funds" else name  # snapshots are keyed by plain fund name
        return {"group": group, "name": name, "country": country, "btc": btc, "pct_supply": btc / MAX_SUPPLY * 100,
                "chg_7d": (btc - p7[key]) if p7 and key in p7 and not estimate else None,
                "chg_30d": (btc - p30[key]) if p30 and key in p30 and not estimate else None,
                "note": note, "estimate": estimate}

    holders = ([row("ETFs & funds", f["name"] + (f" ({f['ticker']})" if f["ticker"] else ""), f["country"], f["btc"]) for f in funds]
               + [row("Public companies", c["name"], c.get("country"), c["total_holdings"]) for c in d["companies"][:6]]
               + [row("Governments", g["name"], g["country"], g["btc"]) for g in govs[:8]]
               + [row(h["group"], h["name"], h["country"], h["btc"], h["note"], True) for h in STATIC_HOLDERS])
    groups = {}
    for h in holders:
        groups.setdefault(h["group"], []).append(h)
    gov_total = sum(g["btc"] for g in govs)
    changes = [h for h in holders if h["chg_7d"]]
    return {
        "groups": groups,
        "totals": {"ETFs & funds": sum(f["btc"] for f in funds), "Public companies": d["total_holdings"],
                   "Governments": gov_total},
        "companies": [h for h in holders if h["group"] == "Public companies"],
        "total_btc": d["total_holdings"], "pct_supply": d.get("market_cap_dominance"),
        "history_days": len(snaps),
        "biggest_7d": max(changes, key=lambda c: abs(c["chg_7d"])) if changes else None,
        "n_funds": len(funds),
        "source": "bitcointreasuries.net (funds); CoinGecko (companies, governments); published estimates (individuals, lost coins)",
    }


def fear_greed() -> dict:
    d = http_json("https://api.alternative.me/fng/?limit=31")["data"]
    vals = [int(x["value"]) for x in d]  # newest first
    return {
        "value": vals[0], "label": d[0]["value_classification"],
        "week_ago": vals[7] if len(vals) > 7 else None,
        "month_ago": vals[30] if len(vals) > 30 else None,
        "source": "alternative.me",
    }


def gather() -> dict:
    out = {}
    for name, fn in [("etf", etf_flows), ("exchanges", exchange_flows), ("treasuries", treasuries), ("fear_greed", fear_greed)]:
        try:
            out[name] = fn()
        except Exception as exc:  # one source failing must not break the report
            out[name] = {"error": str(exc)}
            print(f"[flows] {name} unavailable: {exc}")
    return out
