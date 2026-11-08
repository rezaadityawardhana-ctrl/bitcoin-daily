"""Market, on-chain and macro data from free, primary sources.

- Coin Metrics Community API: daily price, market cap, MVRV, miner issuance, hashrate
- Coinbase: live spot price
- New York Fed: effective Fed funds rate · US Treasury: 10-year yield · ECB reference rates: dollar index
  (all public, no account or API key)
"""
import csv
import io
import json
import time
from datetime import datetime, timedelta

from common import DATA_DIR, http_get, http_json

CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
CM_METRICS = ["PriceUSD", "CapMrktCurUSD", "CapMVRVCur", "IssTotUSD", "HashRate", "IssTotNtv", "FeeTotNtv"]
CACHE = DATA_DIR / "coinmetrics_cache.json"
CACHE_MAX_AGE = 6 * 3600  # seconds



def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_coinmetrics(force: bool = False) -> list[dict]:
    """Full daily BTC history since 2010, cached locally for a few hours."""
    if not force and CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_MAX_AGE:
        cached = json.loads(CACHE.read_text())
        if cached and all(m in cached[-1] for m in CM_METRICS):  # refetch if the metric list changed
            return cached
    url = (
        f"{CM_URL}?assets=btc&metrics={','.join(CM_METRICS)}&frequency=1d"
        "&page_size=10000&paging_from=start&start_time=2010-07-18"
    )
    rows = []
    while url:
        page = http_json(url, timeout=60)
        rows.extend(page.get("data", []))
        url = page.get("next_page_url")
    out = [
        {"date": r["time"][:10], **{m: _num(r.get(m)) for m in CM_METRICS}}
        for r in rows
    ]
    out = [r for r in out if r["PriceUSD"]]
    DATA_DIR.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out))
    return out


def fetch_chf() -> dict | None:
    """BTC price in Swiss francs (Coinbase spot) and the USD/CHF exchange rate (ECB reference rates via Frankfurter)."""
    try:
        btc_chf = float(http_json("https://api.coinbase.com/v2/prices/BTC-CHF/spot")["data"]["amount"])
        start = (datetime.now() - timedelta(days=14)).date().isoformat()
        rates = sorted(http_json(f"https://api.frankfurter.dev/v1/{start}..?base=USD&symbols=CHF")["rates"].items())
        series = [(d, r["CHF"]) for d, r in rates if "CHF" in r]
        date_, fx = series[-1]
        prev = series[-2][1] if len(series) > 1 else None
        week = next((v for d, v in reversed(series) if d <= (datetime.fromisoformat(date_) - timedelta(days=7)).date().isoformat()), None)
        return {"btc_chf": btc_chf, "usd_chf": fx, "date": date_,
                "fx_change_1d": fx / prev - 1 if prev else None,
                "fx_change_7d": fx / week - 1 if week else None}
    except Exception as exc:
        print(f"[market] CHF data unavailable: {exc}")
        return None


def fetch_spot() -> float | None:
    try:
        return float(http_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])
    except Exception:
        return None


def _treasury_10y() -> dict:
    """Daily 10-year par yield from the US Treasury's public CSV (no key)."""
    rows = []
    year = datetime.now().year
    for y in (year - 1, year):  # previous year too, so early January still has a month of history
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
               f"{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        text = http_get(url, timeout=30).decode()
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            if r.get("10 Yr"):
                m, d, yy = r["Date"].split("/")
                rows.append((f"{yy}-{m}-{d}", float(r["10 Yr"])))
    rows.sort()
    date_, value = rows[-1]
    prev = rows[-22][1] if len(rows) > 21 else None
    return {"value": value, "date": date_, "change_30d": None if prev is None else value - prev}


def _fed_funds() -> dict:
    """Effective federal funds rate (EFFR) from the New York Fed's public API (no key)."""
    obs = http_json("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/30.json")["refRates"]
    obs.sort(key=lambda o: o["effectiveDate"])
    last = obs[-1]
    prev = obs[-22]["percentRate"] if len(obs) > 21 else None
    return {"value": last["percentRate"], "date": last["effectiveDate"],
            "change_30d": None if prev is None else last["percentRate"] - prev,
            "note": f'target {last["targetRateFrom"]:.2f}–{last["targetRateTo"]:.2f}%'}


DXY_WEIGHTS = {"EUR": 0.576, "JPY": 0.136, "GBP": 0.119, "CAD": 0.091, "SEK": 0.042, "CHF": 0.036}


def _dollar_index() -> dict:
    """US dollar index computed with the standard DXY formula from ECB reference rates (via Frankfurter, no key).
    With USD as base, DXY = 50.14348112 x prod(USD->ccy ^ weight)."""
    start = (datetime.now() - timedelta(days=50)).date().isoformat()
    data = http_json(f"https://api.frankfurter.dev/v1/{start}..?base=USD&symbols={','.join(DXY_WEIGHTS)}")
    series = []
    for day, rates in sorted(data["rates"].items()):
        if all(c in rates for c in DXY_WEIGHTS):
            v = 50.14348112
            for c, w in DXY_WEIGHTS.items():
                v *= rates[c] ** w
            series.append((day, v))
    date_, value = series[-1]
    prev = series[-22][1] if len(series) > 21 else None
    return {"value": value, "date": date_, "change_30d": None if prev is None else value - prev}


MACRO_SOURCES = [  # id, label, unit, source, fetcher
    ("effr", "Fed funds rate", "%", "New York Fed", _fed_funds),
    ("ust10", "US 10-year Treasury yield", "%", "US Treasury", _treasury_10y),
    ("dxy", "US dollar index", "", "ECB rates, DXY formula", _dollar_index),
]


def fetch_macro() -> list[dict]:
    """Latest value and ~1-month change for each macro series, all from keyless official sources."""
    results = []
    for mid, label, unit, source, fn in MACRO_SOURCES:
        try:
            results.append({"id": mid, "label": label, "unit": unit, "source": source, **fn()})
        except Exception as exc:  # one failing series shouldn't break the report
            results.append({"id": mid, "label": label, "unit": unit, "source": source, "error": str(exc)})
    return results
