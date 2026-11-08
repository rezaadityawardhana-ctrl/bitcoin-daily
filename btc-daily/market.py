"""Market, on-chain and macro data from free, primary sources.

- Coin Metrics Community API: daily price, market cap, MVRV, miner issuance, hashrate
- Coinbase: live spot price
- FRED (St. Louis Fed): Fed funds rate, 10-year Treasury yield, broad dollar index
"""
import json
import os
import time

from common import DATA_DIR, http_json

CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
CM_METRICS = ["PriceUSD", "CapMrktCurUSD", "CapMVRVCur", "IssTotUSD", "HashRate"]
CACHE = DATA_DIR / "coinmetrics_cache.json"
CACHE_MAX_AGE = 6 * 3600  # seconds

FRED_SERIES = {
    "DFF": "Fed funds rate",
    "DGS10": "US 10-year Treasury yield",
    "DTWEXBGS": "US dollar index (broad)",
}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_coinmetrics(force: bool = False) -> list[dict]:
    """Full daily BTC history since 2010, cached locally for a few hours."""
    if not force and CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_MAX_AGE:
        return json.loads(CACHE.read_text())
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


def fetch_spot() -> float | None:
    try:
        return float(http_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])
    except Exception:
        return None


def fetch_macro() -> list[dict]:
    """Latest value and ~1-month change for each FRED series.
    Needs a free FRED API key (https://fred.stlouisfed.org/docs/api/api_key.html) in FRED_API_KEY."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return []
    results = []
    for series_id, label in FRED_SERIES.items():
        try:
            url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={key}&file_type=json&sort_order=desc&limit=40"
            )
            obs = [o for o in http_json(url)["observations"] if o["value"] not in ("", ".")]
            date, value = obs[0]["date"], float(obs[0]["value"])
            prev = float(obs[21]["value"]) if len(obs) > 21 else None  # ~21 business days back
            results.append({
                "id": series_id, "label": label, "date": date, "value": value,
                "change_30d": None if prev is None else value - prev,
            })
        except Exception as exc:  # one failing series shouldn't break the report
            results.append({"id": series_id, "label": label, "error": str(exc)})
    return results
