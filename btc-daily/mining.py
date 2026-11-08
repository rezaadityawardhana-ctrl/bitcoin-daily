"""Estimated cost of producing one bitcoin, plus measured miner revenue (hashprice).

Nobody publishes miners' real costs, so this estimates them from public network data and stated assumptions:

    energy per day  = network hashrate (TH/s) x average fleet efficiency (J/TH) x 24h
    electricity/BTC = energy per day x electricity price / BTC mined per day (new coins + fees)
    all-in cost/BTC = electricity/BTC / electricity share of total cost (hardware, hosting, staff make up the rest)

The low/mid/high cases bracket realistic fleet efficiency and power prices. Edit ASSUMPTIONS to tune them.
"""

ASSUMPTIONS = {
    # average efficiency of all machines on the network, in joules per terahash (newest machines are ~10-15)
    "efficiency_j_per_th": {"low": 14.0, "mid": 19.0, "high": 25.0},
    # average electricity price paid by miners, US$ per kWh
    "electricity_usd_kwh": {"low": 0.040, "mid": 0.055, "high": 0.070},
    # electricity as a share of a miner's all-in cost (the rest: machine depreciation, hosting, staff)
    "electricity_share": 0.65,
}


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _cost(hashrate_th, btc_per_day, eff, usd_kwh):
    kwh_per_day = hashrate_th * eff * 24 / 1000  # TH/s x J/TH = W; x 24h / 1000 = kWh
    return kwh_per_day * usd_kwh / btc_per_day


def estimate(rows: list[dict], price_now: float | None = None) -> dict | None:
    """Uses 7-day averages to smooth out the noise in daily hashrate and block counts."""
    if len(rows) < 40 or rows[-1].get("HashRate") is None or rows[-1].get("IssTotNtv") is None:
        return None
    a = ASSUMPTIONS

    def window(end):
        w = rows[end - 7:end]
        h = _avg([r.get("HashRate") for r in w])
        btc = _avg([(r.get("IssTotNtv") or 0) + (r.get("FeeTotNtv") or 0) for r in w])
        usd = _avg([((r.get("IssTotNtv") or 0) + (r.get("FeeTotNtv") or 0)) * r["PriceUSD"] for r in w])
        return h, btc, usd

    h, btc_day, usd_day = window(len(rows))
    h30, btc30, _ = window(len(rows) - 30)
    case = {k: _cost(h, btc_day, a["efficiency_j_per_th"][k], a["electricity_usd_kwh"][k]) for k in ("low", "mid", "high")}
    mid_30d_ago = _cost(h30, btc30, a["efficiency_j_per_th"]["mid"], a["electricity_usd_kwh"]["mid"])
    all_in = case["mid"] / a["electricity_share"]
    price = price_now or rows[-1]["PriceUSD"]

    # hashprice: what one petahash of mining earns per day (measured, no assumptions)
    hashprice_ph = usd_day / (h / 1000)
    kwh_per_th_day = a["efficiency_j_per_th"]["mid"] * 86400 / 3.6e6
    breakeven_kwh = (usd_day / h) / kwh_per_th_day  # power price at which a mid-efficiency machine breaks even

    if price < case["mid"]:
        zone, reading = "capitulation", ("Price is below the estimated electricity cost: the average miner loses money on every "
                                         "coin. Miners switching off and selling has historically marked late bear markets.")
    elif price < all_in:
        zone, reading = "squeeze", ("Price is between miners' electricity cost and their all-in cost: the average miner covers "
                                    "power but not hardware. That pressure, which pushes weaker miners to sell, has been "
                                    "common near bear-market lows.")
    elif price < all_in * 1.5:
        zone, reading = "healthy", "Price is above the estimated all-in cost: miners are profitable, with a normal margin."
    else:
        zone, reading = "rich", ("Price is far above production cost: mining margins are very high, as in past bull markets. "
                                 "New machines will flood in and push costs up.")
    return {
        "hashrate_eh": h / 1e6,
        "hashrate_change_30d": h / h30 - 1 if h30 else None,
        "btc_per_day": btc_day,
        "electricity_cost": case,             # US$ per BTC, low / mid / high
        "electricity_cost_30d_ago": mid_30d_ago,
        "all_in_cost": all_in,
        "price": price,
        "price_vs_electricity": price / case["mid"] - 1,
        "price_vs_all_in": price / all_in - 1,
        "hashprice_ph_day": hashprice_ph,
        "breakeven_kwh": breakeven_kwh,
        "zone": zone, "reading": reading,
        "assumptions": a,
    }
