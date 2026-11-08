"""Candle charts and technical analysis for BTC/USD and BTC/CHF.

Data: Kraken public OHLC API (no key). Daily candles cover ~2 years; weekly BTC/USD goes back to 2013.
Kraken's CHF market trades little, so the CHF charts use the BTC volume from the USD market (same coin, same days).

This module
- fetches the candles (embedded in the page, where the chart computes indicators for drawing),
- computes a technical snapshot (moving averages, RSI, MACD, Bollinger Bands, volume profile, support/resistance,
  Fibonacci levels, weekly trend),
- turns the snapshot into an analyst-style read: Claude when available, otherwise transparent rules.
"""
import json
import os
from datetime import datetime, timezone

from common import DATA_DIR, http_json
from indicators import sma, wilder_rsi

CACHE = DATA_DIR / "candles_cache.json"


# ------------------------------------------------------------------ data
def _kraken(pair: str, interval: int) -> list[list[float]]:
    d = http_json(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}", timeout=30)
    if d.get("error"):
        raise ValueError(d["error"])
    key = next(k for k in d["result"] if k != "last")
    # [time, open, high, low, close, vwap, volume, count] -> [time, o, h, l, c, volume]
    return [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[6])] for r in d["result"][key]]


def fetch_candles() -> dict:
    import time
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < 3 * 3600:
        return json.loads(CACHE.read_text())
    out = {"usd_d": _kraken("XBTUSD", 1440), "usd_w": _kraken("XBTUSD", 10080),
           "chf_d": _kraken("XBTCHF", 1440), "chf_w": _kraken("XBTCHF", 10080)}
    for cur in ("d", "w"):  # CHF volume -> BTC volume traded on the (much deeper) USD market
        vol = {c[0]: c[5] for c in out[f"usd_{cur}"]}
        out[f"chf_{cur}"] = [c[:5] + [vol.get(c[0], c[5])] for c in out[f"chf_{cur}"]]
    DATA_DIR.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out))
    return out


# ------------------------------------------------------------------ indicators
def ema(values, n):
    out, k, prev = [], 2 / (n + 1), None
    for i, v in enumerate(values):
        if i < n - 1:
            out.append(None)
            continue
        prev = sum(values[:n]) / n if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    start = next(i for i, v in enumerate(line) if v is not None)
    sig_part = ema(line[start:], signal)
    sig = [None] * start + sig_part
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def bollinger(closes, n=20, k=2.0):
    mid = sma(closes, n)
    up, lo = [], []
    for i, m in enumerate(mid):
        if m is None:
            up.append(None); lo.append(None); continue
        w = closes[i - n + 1:i + 1]
        sd = (sum((x - m) ** 2 for x in w) / n) ** 0.5
        up.append(m + k * sd); lo.append(m - k * sd)
    return up, mid, lo


def volume_profile(candles, bins=40):
    """Volume at price: each candle's volume is spread evenly over its high-low range."""
    lo = min(c[3] for c in candles); hi = max(c[2] for c in candles)
    step = (hi - lo) / bins or 1
    vol = [0.0] * bins
    for _, _, h, l, _, v in candles:
        a, b = int((l - lo) / step), min(bins - 1, int((h - lo) / step))
        share = v / (b - a + 1)
        for j in range(a, b + 1):
            vol[j] += share
    poc = max(range(bins), key=lambda j: vol[j])
    # value area: 70% of volume around the POC
    total, area, lo_i, hi_i = sum(vol), vol[poc], poc, poc
    while area < 0.7 * total and (lo_i > 0 or hi_i < bins - 1):
        down = vol[lo_i - 1] if lo_i > 0 else -1
        up = vol[hi_i + 1] if hi_i < bins - 1 else -1
        if up >= down:
            hi_i += 1; area += up
        else:
            lo_i -= 1; area += down
    mid = lambda j: lo + (j + 0.5) * step
    hvn = sorted(range(bins), key=lambda j: -vol[j])[:6]
    return {"poc": mid(poc), "va_low": lo + lo_i * step, "va_high": lo + (hi_i + 1) * step,
            "hvn": sorted(mid(j) for j in hvn)}


def swing_levels(candles, k=5, tol=0.025):
    """Support/resistance from swing highs/lows, clustered when within `tol` of each other."""
    piv = []
    for i in range(k, len(candles) - k):
        h, l = candles[i][2], candles[i][3]
        if h == max(c[2] for c in candles[i - k:i + k + 1]):
            piv.append(h)
        if l == min(c[3] for c in candles[i - k:i + k + 1]):
            piv.append(l)
    piv.sort()
    clusters = []
    for p in piv:
        if clusters and p / clusters[-1][-1] - 1 < tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [{"price": sum(c) / len(c), "touches": len(c)} for c in clusters if len(c) >= 2]


def fib_levels(candles):
    """Retracements of the move from the highest high (last ~400 bars) down to the lowest low after it."""
    w = candles[-400:]
    hi_i = max(range(len(w)), key=lambda i: w[i][2])
    after = w[hi_i:]
    lo_i = min(range(len(after)), key=lambda i: after[i][3])
    hi, lo = w[hi_i][2], after[lo_i][3]
    if hi <= lo * 1.05:
        return None
    return {"high": hi, "high_time": w[hi_i][0], "low": lo, "low_time": after[lo_i][0],
            "levels": {str(r): lo + (hi - lo) * r for r in (0.236, 0.382, 0.5, 0.618, 0.786)}}


def _cross_date(fast, slow, times):
    """Most recent crossing of two series: ('golden'|'death', time)."""
    for i in range(len(fast) - 1, 0, -1):
        if None in (fast[i], slow[i], fast[i - 1], slow[i - 1]):
            break
        if (fast[i] > slow[i]) != (fast[i - 1] > slow[i - 1]):
            return ("golden" if fast[i] > slow[i] else "death"), times[i]
    return None, None


def snapshot(candles: dict, cur: str = "usd") -> dict:
    d, w = candles[f"{cur}_d"], candles[f"{cur}_w"]
    t = [c[0] for c in d]
    close = [c[4] for c in d]
    vol = [c[5] for c in d]
    s50, s200 = sma(close, 50), sma(close, 200)
    rsi = wilder_rsi(close, 14)
    m, sig, hist = macd(close)
    bu, bm, bl = bollinger(close)
    last = len(close) - 1
    cross, cross_t = _cross_date(s50, s200, t)
    mcross, mcross_t = _cross_date(m, sig, t)
    width = [(u - l) / mid if u and mid else None for u, mid, l in zip(bu, bm, bl)]
    recent_w = [x for x in width[-180:] if x]
    # RSI divergence over ~30 days: price makes a lower low while RSI makes a higher low (bullish), or the reverse
    win = 30
    p_now_lo, p_prev_lo = min(close[-10:]), min(close[-win:-10])
    r_now_lo, r_prev_lo = min(x for x in rsi[-10:] if x), min(x for x in rsi[-win:-10] if x)
    p_now_hi, p_prev_hi = max(close[-10:]), max(close[-win:-10])
    r_now_hi, r_prev_hi = max(x for x in rsi[-10:] if x), max(x for x in rsi[-win:-10] if x)
    divergence = ("bullish" if p_now_lo < p_prev_lo and r_now_lo > r_prev_lo + 2 else
                  "bearish" if p_now_hi > p_prev_hi and r_now_hi < r_prev_hi - 2 else None)

    wc = [c[4] for c in w]
    w20, w21e, w50 = sma(wc, 20), ema(wc, 21), sma(wc, 50)
    w200 = sma(wc, 200) if len(wc) >= 200 else [None] * len(wc)
    wrsi = wilder_rsi(wc, 14)
    _, _, whist = macd(wc)

    vp = volume_profile(d[-180:])
    price = close[last]
    levels = swing_levels(d[-365:])
    supports = sorted([l for l in levels if l["price"] < price * 0.995], key=lambda l: -l["price"])[:3]
    resist = sorted([l for l in levels if l["price"] > price * 1.005], key=lambda l: l["price"])[:3]
    fib = fib_levels(d)
    iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else None
    return {
        "currency": cur.upper(), "date": iso(t[last]), "price": price,
        "change_7d": price / close[-8] - 1, "change_30d": price / close[-31] - 1,
        "sma50": s50[last], "sma200": s200[last],
        "vs_sma50": price / s50[last] - 1, "vs_sma200": price / s200[last] - 1,
        "sma200_slope_20d": s200[last] / s200[last - 20] - 1,
        "ma_cross": cross, "ma_cross_date": iso(cross_t),
        "rsi": rsi[last], "rsi_14d_ago": rsi[last - 14], "rsi_divergence": divergence,
        "macd": m[last], "macd_signal": sig[last], "macd_hist": hist[last],
        "macd_hist_rising": hist[last] > hist[last - 1] > hist[last - 2],
        "macd_cross": mcross, "macd_cross_date": iso(mcross_t),
        "bb_upper": bu[last], "bb_lower": bl[last],
        "bb_pct_b": (price - bl[last]) / (bu[last] - bl[last]) if bu[last] != bl[last] else None,
        "bb_width_percentile": sum(x <= width[last] for x in recent_w) / len(recent_w) if recent_w else None,
        "volume_20d_vs_90d": (sum(vol[-20:]) / 20) / (sum(vol[-90:]) / 90) - 1,
        "volume_profile_180d": vp,
        "supports": supports, "resistances": resist,
        "fib": fib,
        "weekly": {
            "close": wc[-1], "sma20": w20[-1], "ema21": w21e[-1], "sma50": w50[-1], "sma200": w200[-1],
            "above_bull_band": wc[-1] > max(w20[-1], w21e[-1]), "below_bull_band": wc[-1] < min(w20[-1], w21e[-1]),
            "rsi": wrsi[-1], "macd_hist": whist[-1], "macd_hist_prev": whist[-2],
        },
    }


# ------------------------------------------------------------------ analysis
def _fmt(v, cur="USD"):
    sym = "$" if cur == "USD" else "CHF "
    return f"{sym}{v:,.0f}"


def rule_based_read(s: dict) -> dict:
    """Analyst-style read built from fixed rules (used when Claude isn't available)."""
    cur, wk = s["currency"], s["weekly"]
    score = 0
    score += 1 if s["vs_sma200"] > 0 else -1
    score += 1 if s["sma50"] > s["sma200"] else -1
    score += 1 if s["vs_sma50"] > 0 else -1
    score += 1 if s["macd_hist"] > 0 else -1
    score += 1 if s["rsi"] >= 50 else -1
    score += 1 if wk["above_bull_band"] else -1 if wk["below_bull_band"] else 0
    bias = "Bullish" if score >= 3 else "Bearish" if score <= -3 else "Neutral / range"
    conf = "high" if abs(score) >= 5 else "medium" if abs(score) >= 3 else "low"

    trend = []
    trend.append(f"Price is {abs(s['vs_sma200']) * 100:.0f}% {'above' if s['vs_sma200'] > 0 else 'below'} the 200-day MA "
                 f"({_fmt(s['sma200'], cur)}), which is {'rising' if s['sma200_slope_20d'] > 0 else 'falling'}.")
    if s["ma_cross"]:
        trend.append(f"Last 50/200-day cross: {'golden cross' if s['ma_cross'] == 'golden' else 'death cross'} on {s['ma_cross_date']}.")
    trend.append(f"Weekly: close is {'above' if wk['above_bull_band'] else 'below' if wk['below_bull_band'] else 'inside'} the bull-market "
                 f"support band (20-week SMA {_fmt(wk['sma20'], cur)} / 21-week EMA {_fmt(wk['ema21'], cur)}).")

    mom = [f"Daily RSI {s['rsi']:.0f} (was {s['rsi_14d_ago']:.0f} two weeks ago)"
           + (": oversold." if s["rsi"] < 30 else ": overbought." if s["rsi"] > 70 else ".")]
    mom.append(f"MACD histogram is {'positive' if s['macd_hist'] > 0 else 'negative'} and "
               f"{'rising' if s['macd_hist_rising'] else 'not yet turning up'}"
               + (f"; last signal-line cross was {'bullish' if s['macd_cross'] == 'golden' else 'bearish'} on {s['macd_cross_date']}." if s["macd_cross"] else "."))
    if s["rsi_divergence"]:
        mom.append(f"{s['rsi_divergence'].capitalize()} RSI divergence over the last month: momentum "
                   f"{'is improving while price makes lower lows' if s['rsi_divergence'] == 'bullish' else 'is fading while price makes higher highs'}.")
    if s["bb_width_percentile"] is not None and s["bb_width_percentile"] < 0.15:
        mom.append("Bollinger Bands are unusually tight: a large move is likely soon (direction not given by the squeeze itself).")

    vp = s["volume_profile_180d"]
    vol = [f"Volume over the last 20 days is {abs(s['volume_20d_vs_90d']) * 100:.0f}% "
           f"{'above' if s['volume_20d_vs_90d'] > 0 else 'below'} its 90-day average."]
    vol.append(f"Volume profile (180 days): most traded price (POC) {_fmt(vp['poc'], cur)}, value area "
               f"{_fmt(vp['va_low'], cur)}–{_fmt(vp['va_high'], cur)}. Price is "
               f"{'above' if s['price'] > vp['va_high'] else 'below' if s['price'] < vp['va_low'] else 'inside'} the value area.")

    levels = []
    for l in s["supports"]:
        levels.append({"price": l["price"], "type": "support", "why": f"swing lows touched {l['touches']}×"})
    for l in s["resistances"]:
        levels.append({"price": l["price"], "type": "resistance", "why": f"swing highs touched {l['touches']}×"})
    levels.append({"price": vp["poc"], "type": "support" if vp["poc"] < s["price"] else "resistance", "why": "volume POC (180 days)"})
    for name, val in (("200-day MA", s["sma200"]), ("50-day MA", s["sma50"])):
        levels.append({"price": val, "type": "support" if val < s["price"] else "resistance", "why": name})
    if s["fib"]:
        for r, val in s["fib"]["levels"].items():
            if abs(val / s["price"] - 1) < 0.15:
                levels.append({"price": val, "type": "support" if val < s["price"] else "resistance",
                               "why": f"Fibonacci {r} retracement of the drop from {_fmt(s['fib']['high'], cur)}"})
    # confluence: merge levels within 1.5% of each other
    levels.sort(key=lambda l: -l["price"])
    merged = []
    for l in levels:
        if merged and abs(merged[-1]["price"] / l["price"] - 1) < 0.015 and merged[-1]["type"] == l["type"]:
            merged[-1]["why"] += f" + {l['why']}"
            merged[-1]["confluence"] = True
        else:
            merged.append(dict(l))
    levels = merged

    sup = max((l["price"] for l in levels if l["type"] == "support"), default=None)
    res = min((l["price"] for l in levels if l["type"] == "resistance"), default=None)
    scenarios = []
    if res:
        scenarios.append({"name": "Bull case", "trigger": f"Daily close above {_fmt(res, cur)}",
                          "target": f"next resistance / {_fmt(max(res * 1.08, s['sma200']), cur)}"})
    if sup:
        scenarios.append({"name": "Bear case", "trigger": f"Daily close below {_fmt(sup, cur)}",
                          "target": f"{_fmt(sup * 0.92, cur)} area / lower volume nodes"})
    lt = ("The daily trend matters less than the cycle score and exit signal. "
          + ("A downtrend at low cycle valuations has historically been an accumulation zone; scaling in near support "
             "beats chasing breakouts." if bias != "Bullish" else
             "Trend is supportive; let the position run and follow the scale-out plan near cycle highs."))
    return {"source": "rules", "bias": bias, "confidence": conf,
            "summary": f"{bias} bias ({conf} confidence): {trend[0]} {mom[0]}",
            "trend": trend, "momentum": mom, "volume": vol, "levels": levels[:8], "scenarios": scenarios,
            "invalidation": (
                f"The bullish view is invalidated by a daily close below {_fmt(sup, cur)}." if bias == "Bullish" and sup else
                f"The bearish view is invalidated by a daily close above {_fmt(res, cur)}." if bias == "Bearish" and res else
                f"The range ends on a daily close above {_fmt(res, cur)} (bullish) or below {_fmt(sup, cur)} (bearish)." if sup and res else
                "No clear invalidation level nearby."),
            "long_term": lt}


AI_SCHEMA = {
    "type": "object",
    "properties": {
        "bias": {"type": "string", "enum": ["Bullish", "Bearish", "Neutral / range"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "summary": {"type": "string"},
        "trend": {"type": "array", "items": {"type": "string"}},
        "momentum": {"type": "array", "items": {"type": "string"}},
        "volume": {"type": "array", "items": {"type": "string"}},
        "levels": {"type": "array", "items": {"type": "object", "properties": {
            "price": {"type": "number"}, "type": {"type": "string", "enum": ["support", "resistance"]}, "why": {"type": "string"}},
            "required": ["price", "type", "why"], "additionalProperties": False}},
        "scenarios": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "trigger": {"type": "string"}, "target": {"type": "string"}},
            "required": ["name", "trigger", "target"], "additionalProperties": False}},
        "invalidation": {"type": "string"},
        "long_term": {"type": "string"},
    },
    "required": ["bias", "confidence", "summary", "trend", "momentum", "volume", "levels", "scenarios", "invalidation", "long_term"],
    "additionalProperties": False,
}

AI_SYSTEM = """You are a senior technical analyst writing a concise read of the bitcoin chart for a long-term holder.
You receive a computed snapshot: daily moving averages (50/200), RSI, MACD, Bollinger Bands, volume and a 180-day
volume profile (POC, value area, high-volume nodes), swing support/resistance, Fibonacci retracements, and the weekly
trend (bull-market support band = 20-week SMA + 21-week EMA, 50/200-week SMAs), plus the cycle score context.

Rules:
- Use only the numbers provided; never invent levels. Quote prices rounded sensibly.
- Be specific: name the levels, what confirms or invalidates each scenario.
- Weigh the weekly trend above the daily one. Mention confluence (several tools pointing to the same level).
- No certainty language, no price predictions as facts, no buy/sell orders; describe conditions and probabilities.
- long_term: one or two sentences relating the chart to a long-term holder's plan (DCA, scale-out), consistent with the
  cycle context provided."""


def ai_read(s: dict, context: dict) -> dict | None:
    if os.environ.get("BTC_DAILY_NO_AI"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        r = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=AI_SYSTEM,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": AI_SCHEMA}},
            messages=[{"role": "user", "content": json.dumps({"snapshot": s, "context": context}, default=str)}],
        )
        if r.stop_reason == "refusal":
            return None
        out = json.loads(next(b.text for b in r.content if b.type == "text"))
        out["source"] = r.model
        return out
    except Exception as exc:
        print(f"[ta] AI analysis skipped: {exc}")
        return None


def build(context: dict) -> dict | None:
    """Everything the chart view needs: candles for both currencies/timeframes plus the analysis."""
    try:
        candles = fetch_candles()
    except Exception as exc:
        print(f"[ta] candles unavailable: {exc}")
        return None
    out = {"candles": {k: [[c[0], round(c[1], 1), round(c[2], 1), round(c[3], 1), round(c[4], 1), round(c[5], 2)] for c in v]
                       for k, v in candles.items()},
           "analysis": {}, "levels": {}}
    for cur in ("usd", "chf"):
        s = snapshot(candles, cur)
        read = (ai_read(s, context) if cur == "usd" else None) or rule_based_read(s)
        out["analysis"][cur] = {"snapshot": s, "read": read}
        out["levels"][cur] = {"fib": s["fib"], "supports": s["supports"], "resistances": s["resistances"]}
    return out
