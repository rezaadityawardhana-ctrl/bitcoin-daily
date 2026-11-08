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

    # completed weekly closes and their 20-week moving average (the exit "trend line")
    keys = [date.fromisoformat(d).isocalendar()[:2] for d in dates]
    wk_idx = [i for i in range(len(dates) - 1) if keys[i + 1] != keys[i]]
    w20 = sma([price[i] for i in wk_idx], 20)
    ma20w_daily, j = [], -1
    for i in range(len(dates)):
        while j + 1 < len(wk_idx) and wk_idx[j + 1] <= i:
            j += 1
        ma20w_daily.append(w20[j] if j >= 0 else None)
    exit_info = exit_layer(dates, price, wk_idx, w20)

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
         "w": round(ma1400[i], 2), "r": round(realized_price[i], 2) if realized_price[i] else None,
         "m": round(ma20w_daily[i], 2) if ma20w_daily[i] else None}
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
        "exit": exit_info,
        "hashrate_change_30d": hashrate[last] / hr30 - 1 if hr30 else None,
        "history": history,
    }


def add_months(d: date, m: int) -> date:
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    return date(y, mo, min(d.day, 28))


EXIT_WINDOW = (12, 24)  # months after a halving where every past cycle top formed


def exit_layer(dates, price, wk_idx, w20) -> dict:
    """Trend-break exit signal for the late cycle, evaluated day by day with no look-ahead.

    Rule: inside the exit window (12-24 months after a halving), once price makes a new all-time high
    the signal is ARMED; the first completed weekly close below the 20-week moving average after that
    TRIGGERS it (a cue to sell a bigger tranche). A further all-time high re-arms it.
    New all-time highs while armed are scale-out steps (cue to sell a small slice)."""
    today = date.fromisoformat(dates[-1])
    pos = {d: i for i, d in enumerate(dates)}
    week_of = {i: j for j, i in enumerate(wk_idx)}
    events, current = [], None
    for h in HALVINGS:
        start, end = add_months(h, EXIT_WINDOW[0]), add_months(h, EXIT_WINDOW[1])
        first = next((i for i, d in enumerate(dates) if date.fromisoformat(d) >= start), None)
        if first is None:
            continue
        ath = max(price[:first]) if first else 0
        armed, hi_i, n_highs, triggers = False, None, 0, []
        new_high_today = False
        for i in range(first, len(dates)):
            if date.fromisoformat(dates[i]) > end:
                break
            if price[i] > ath:
                ath, armed, hi_i = price[i], True, i
                n_highs += 1
                new_high_today = i == len(dates) - 1
            j = week_of.get(i)
            if armed and j is not None and w20[j] and price[i] < w20[j]:
                triggers.append({"date": dates[i], "price": price[i], "from_high": price[i] / ath - 1,
                                 "high": ath, "high_date": dates[hi_i]})
                armed = False
        for t in triggers:
            later = price[pos[t["date"]]: pos[t["date"]] + 800]
            t["later_low"] = min(later) / t["high"] - 1 if len(later) > 30 else None
            t["low_final"] = pos[t["date"]] + 800 <= len(price)
            events.append({**t, "halving": h.isoformat()})
        current = {"halving": h, "start": start, "end": end, "armed": armed, "triggers": triggers,
                   "new_high_today": new_high_today, "ath": ath, "n_highs": n_highs}

    last_wk = wk_idx[-1]
    w20_now = w20[-1]
    st = current
    if today < st["start"]:
        status, label = "waiting", "Not active yet"
        detail = f"The exit window opens on {st['start']:%-d %b %Y} (12 months after the halving)."
    elif today <= st["end"]:
        if st["armed"]:
            status, label = "armed", "Armed: new all-time highs in the exit window"
            detail = (f"Each new all-time high is a scale-out step. A weekly close below the 20-week MA "
                      f"(${w20_now:,.0f}) triggers the exit signal.")
        elif st["triggers"]:
            t = st["triggers"][-1]
            status, label = "triggered", "Exit signal triggered"
            detail = (f"Weekly close ${t['price']:,.0f} on {date.fromisoformat(t['date']):%-d %b %Y} fell below the 20-week MA, "
                      f"{abs(t['from_high']) * 100:.0f}% under the ${t['high']:,.0f} high.")
        else:
            status, label = "watch", "Watching: exit window open"
            detail = "No new all-time high yet in this window. The signal arms on the first one."
    else:
        nxt = add_months(NEXT_HALVING_EST, EXIT_WINDOW[0])
        if st["triggers"]:
            t = st["triggers"][-1]
            status, label = "closed", f"Fired {date.fromisoformat(t['date']):%b %Y} · window closed"
            detail = (f"This cycle's signal fired on {date.fromisoformat(t['date']):%-d %b %Y} at ${t['price']:,.0f}, "
                      f"{abs(t['from_high']) * 100:.0f}% below the ${t['high']:,.0f} top. Next exit window opens ≈ {nxt:%b %Y}.")
        else:
            status, label = "closed", "Window closed · no signal"
            detail = f"No exit signal fired this cycle. Next exit window opens ≈ {nxt:%b %Y}."
    fired_recently = bool(st["triggers"]) and (today - date.fromisoformat(st["triggers"][-1]["date"])).days <= 7
    return {
        "status": status, "label": label, "detail": detail,
        "window_start": st["start"].isoformat(), "window_end": st["end"].isoformat(),
        "ma20w": w20_now, "price_vs_ma20w": price[-1] / w20_now - 1 if w20_now else None,
        "new_high_today": st["new_high_today"] and status == "armed",
        "fired_recently": fired_recently and status in ("triggered", "closed"),
        "events": events,
    }


def halving_phase(months: float) -> str:
    if months < 12:
        return "Early post-halving: historically the start of bull phases."
    if months < 20:
        return "12–20 months after halving: where the 2013, 2017, 2021 and 2025 peaks formed."
    if months < 32:
        return "20–32 months after halving: historically the post-peak bear market and bottoming phase."
    return "Final year before the next halving: historically a recovery/accumulation phase."
