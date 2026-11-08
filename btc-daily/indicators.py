"""Cycle indicators and the composite Cycle Score (0 = deep value, 100 = overheated).

Every indicator is mapped to a 0-100 sub-score with fixed, explainable breakpoints
(edit SCORE_MAPS to tune them). The Cycle Score is the plain average of sub-scores.
All history values are computed without look-ahead, so the backtest table is honest.
"""
import math
from datetime import date

HALVINGS = [date(2012, 11, 28), date(2016, 7, 9), date(2020, 5, 11), date(2024, 4, 20)]
NEXT_HALVING_EST = date(2028, 4, 15)  # estimate; depends on block times

# (indicator value, sub-score) breakpoints, linearly interpolated and clamped.
SCORE_MAPS = {
    "mvrv_z":   [(-0.5, 0), (0, 10), (1, 30), (2.5, 55), (4, 75), (6, 92), (7, 100)],
    "mayer":    [(0.6, 0), (0.8, 10), (1.0, 30), (1.5, 60), (2.0, 80), (2.4, 95), (3.0, 100)],
    "wma200":   [(0.8, 0), (1.0, 10), (1.5, 35), (2.5, 60), (4.0, 85), (6.0, 100)],
    "pi_cycle": [(0.3, 0), (0.5, 20), (0.7, 50), (0.9, 80), (1.0, 100)],
    "puell":    [(0.4, 0), (0.6, 15), (1.0, 40), (2.0, 70), (3.0, 90), (4.0, 100)],
    "rsi_w":    [(25, 0), (35, 15), (50, 45), (70, 75), (85, 95), (90, 100)],
}

INDICATOR_INFO = {
    "mvrv_z": ("MVRV Z-Score", "Market value vs. on-chain cost basis, in standard deviations",
               "Below 0 = historically deep value · above 6 = historically overheated"),
    "mayer": ("Mayer Multiple", "Price ÷ 200-day moving average",
              "Below 0.8 = undervalued · above 2.4 = overheated"),
    "wma200": ("Price ÷ 200-week MA", "Distance from the long-run trend line",
               "Near or below 1.0 = cycle lows · above 4 = late-cycle froth"),
    "pi_cycle": ("Pi Cycle ratio", "111-day MA ÷ (2 × 350-day MA)",
                 "Reaching 1.0 (crossover) has coincided with past cycle tops"),
    "puell": ("Puell Multiple", "Daily miner issuance (USD) ÷ its 365-day average",
              "Below 0.5 = miner stress/value · above 3 = miner windfall/top risk"),
    "rsi_w": ("Weekly RSI (14)", "Momentum on weekly candles",
              "Below 35 = oversold · above 85 = overbought"),
}

ZONES = [  # (upper bound, key, label, playbook)
    (20, "strong-accumulate", "Strong accumulation",
     "Historically rare deep-value zone. Playbook: increase regular buys (e.g. 2× DCA)."),
    (40, "accumulate", "Accumulate",
     "Below-average valuation. Playbook: keep regular DCA going."),
    (70, "hold", "Hold / neutral",
     "Mid-cycle. Playbook: hold; no action needed."),
    (85, "scale-out", "Scale out gradually",
     "Elevated valuation. Playbook: consider trimming in small steps (e.g. 5–10% per step)."),
    (101, "take-profit", "Overheated",
     "Historically near cycle tops. Playbook: take profit in larger steps; keep a core position."),
]


def zone_for(score: float) -> dict:
    for upper, key, label, playbook in ZONES:
        if score < upper:
            return {"key": key, "label": label, "playbook": playbook}
    return {"key": "take-profit", "label": ZONES[-1][2], "playbook": ZONES[-1][3]}


def interp(x: float, pts: list[tuple]) -> float:
    if x <= pts[0][0]:
        return float(pts[0][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return float(pts[-1][1])


def sma(values: list, n: int) -> list:
    out, total, window = [], 0.0, []
    for v in values:
        window.append(v)
        total += v
        if len(window) > n:
            total -= window.pop(0)
        out.append(total / n if len(window) == n else None)
    return out


def wilder_rsi(closes: list[float], n: int = 14) -> list:
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_g, avg_l = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(closes)):
        if i > n:
            avg_g = (avg_g * (n - 1) + gains[i - 1]) / n
            avg_l = (avg_l * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def weekly_rsi_by_day(dates: list[str], prices: list[float]) -> list:
    """For each day: RSI of weekly closes, using the previous *completed* week (no look-ahead),
    except the latest day, which uses the current (partial) week like a live chart would."""
    week_keys = [date.fromisoformat(d).isocalendar()[:2] for d in dates]
    week_close_idx = [i for i in range(len(dates)) if i == len(dates) - 1 or week_keys[i + 1] != week_keys[i]]
    closes = [prices[i] for i in week_close_idx]
    rsi = wilder_rsi(closes)
    out, w = [None] * len(dates), -1
    for i in range(len(dates)):
        # w = index of the last completed week before day i
        while w + 1 < len(week_close_idx) and week_close_idx[w + 1] < i:
            w += 1
        out[i] = rsi[w] if w >= 0 else None
    out[-1] = rsi[-1]
    return out


def compute(rows: list[dict]) -> dict:
    dates = [r["date"] for r in rows]
    price = [r["PriceUSD"] for r in rows]
    mcap = [r["CapMrktCurUSD"] for r in rows]
    mvrv = [r["CapMVRVCur"] for r in rows]
    iss = [r["IssTotUSD"] or 0.0 for r in rows]
    hashrate = [r["HashRate"] for r in rows]

    ma111, ma200, ma350, ma1400 = sma(price, 111), sma(price, 200), sma(price, 350), sma(price, 1400)
    iss365 = sma(iss, 365)
    rsi_w = weekly_rsi_by_day(dates, price)

    # MVRV Z = (market cap - realized cap) / std(market cap so far)  [expanding std, no look-ahead]
    mvrv_z, n, mean, m2 = [], 0, 0.0, 0.0
    for mc, mv in zip(mcap, mvrv):
        if mc is None or not mv:
            mvrv_z.append(None)
            continue
        n += 1
        d = mc - mean
        mean += d / n
        m2 += d * (mc - mean)
        std = math.sqrt(m2 / n) if n > 1 else 0
        mvrv_z.append((mc - mc / mv) / std if std > 0 and n > 365 else None)

    realized_price = [p / mv if mv else None for p, mv in zip(price, mvrv)]

    raw = {
        "mvrv_z": mvrv_z,
        "mayer": [p / m if m else None for p, m in zip(price, ma200)],
        "wma200": [p / m if m else None for p, m in zip(price, ma1400)],
        "pi_cycle": [a / (2 * b) if a and b else None for a, b in zip(ma111, ma350)],
        "puell": [v / m if m and v else None for v, m in zip(iss, iss365)],
        "rsi_w": rsi_w,
    }

    score = []
    for i in range(len(dates)):
        vals = [raw[k][i] for k in SCORE_MAPS]
        score.append(None if any(v is None for v in vals) else
                     sum(interp(v, SCORE_MAPS[k]) for k, v in zip(SCORE_MAPS, vals)) / len(vals))

    last = len(dates) - 1
    indicators = []
    for key, pts in SCORE_MAPS.items():
        name, desc, guide = INDICATOR_INFO[key]
        val = raw[key][last]
        indicators.append({"key": key, "name": name, "desc": desc, "guide": guide,
                           "value": val, "subscore": interp(val, pts) if val is not None else None})

    # backtest: forward 1-year return by score band (overlapping windows, few cycles: read with care)
    bands = [(0, 20), (20, 40), (40, 70), (70, 85), (85, 101)]
    backtest = []
    for lo, hi in bands:
        fwd = [price[i + 365] / price[i] - 1 for i in range(len(dates) - 365)
               if score[i] is not None and lo <= score[i] < hi]
        fwd.sort()
        backtest.append({
            "band": f"{lo}–{min(hi, 100)}", "label": zone_for(lo)["label"], "days": len(fwd),
            "median": fwd[len(fwd) // 2] if fwd else None,
            "pct_positive": sum(f > 0 for f in fwd) / len(fwd) if fwd else None,
        })

    # cycle context
    today = date.fromisoformat(dates[last])
    last_halving = max(h for h in HALVINGS if h <= today)
    months_since_halving = (today - last_halving).days / 30.44
    ath_i = max(range(len(price)), key=lambda i: price[i])
    hr30 = hashrate[last - 30] if last >= 30 and hashrate[last - 30] else None

    first_scored = next(i for i, s in enumerate(score) if s is not None)
    history = [
        {"d": dates[i], "p": round(price[i], 2), "s": round(score[i], 1),
         "w": round(ma1400[i], 2), "r": round(realized_price[i], 2) if realized_price[i] else None}
        for i in range(first_scored, len(dates))
    ]

    s_now = score[last]
    return {
        "as_of": dates[last],
        "price_close": price[last],
        "change_1d": price[last] / price[last - 1] - 1,
        "change_30d": price[last] / price[last - 30] - 1,
        "score": s_now,
        "score_30d_ago": score[last - 30],
        "zone": zone_for(s_now),
        "indicators": indicators,
        "backtest": backtest,
        "realized_price": realized_price[last],
        "wma200": ma1400[last],
        "ath": {"price": price[ath_i], "date": dates[ath_i], "drawdown": price[last] / price[ath_i] - 1},
        "halving": {
            "last": last_halving.isoformat(), "next_est": NEXT_HALVING_EST.isoformat(),
            "months_since": months_since_halving,
            "days_to_next": (NEXT_HALVING_EST - today).days,
            "phase": halving_phase(months_since_halving),
        },
        "hashrate_change_30d": hashrate[last] / hr30 - 1 if hr30 else None,
        "history": history,
    }


def halving_phase(months: float) -> str:
    if months < 12:
        return "Early post-halving: historically the start of bull phases."
    if months < 20:
        return "12–20 months after halving: where the 2013, 2017, 2021 and 2025 peaks formed."
    if months < 32:
        return "20–32 months after halving: historically the post-peak bear market and bottoming phase."
    return "Final year before the next halving: historically a recovery/accumulation phase."
