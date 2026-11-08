"""News tone, the market-mood gauge, agenda checks and the 'how to read today' interpretation.

Everything here is rule-based and transparent. When the Claude brief is available, its per-story sentiment,
agenda notes and interpretation replace the rule-based versions (see news.summarize)."""
import re

BULL = re.compile(r"\b(inflows?|record high|all-time high|ath|buys?|bought|buying|accumulat\w*|approv\w*|adopt\w*|surg\w*|rall\w*|"
                  r"rebound\w*|recover\w*|gains?|jumps?|soars?|climbs?|strategic reserve|bullish|upgrade[sd]?|eases?|steadies|"
                  r"breakout|demand)\b", re.I)
BEAR = re.compile(r"\b(outflows?|sell\w*|sold|sell-?off|dump\w*|plung\w*|slump\w*|falls?|fell|drops?|crash\w*|liquidat\w*|hack\w*|"
                  r"heist|exploit\w*|bans?|lawsuit|sues|fraud|bankrupt\w*|bleed\w*|loss(es)?|fear\w*|reckoning|tumbl\w*|slid(e|es)?|"
                  r"worst|bearish|halt\w*|scrutiny|crackdown|rout|negative|losing|weak\w*)\b", re.I)

INTERESTED = re.compile(r"\b(Strategy|MicroStrategy|Saylor|BlackRock|Fidelity|Coinbase|Binance|Metaplanet|Tether|Grayscale|ARK|"
                        r"Bitwise|VanEck|Galaxy|Bullish|Kraken|Twenty One|Strive|MARA)\b")
TALKING_BOOK = re.compile(r"\b(says|predicts?|expects?|calls?|bets?|launch\w*|plans?|unveils?|touts?|target\w*|forecasts?|sees)\b", re.I)
PRICE_MOVE = re.compile(r"\b(steadies|eases?|falls?|rises?|slides?|jumps?|tumbles?|rall(y|ies)|sell-?off|slumps?|climbs?|"
                        r"weekly loss|weekly gain|price)\b", re.I)
FLOW_TALK = re.compile(r"\b(ETFs?|inflows?|outflows?)\b", re.I)

MAINSTREAM = re.compile(r"Reuters|Bloomberg|Financial Times|WSJ|Wall Street Journal|AP News|Associated Press|CNBC", re.I)

MOOD_ZONES = [(20, "Extreme fear"), (40, "Fear"), (60, "Neutral"), (80, "Greed"), (101, "Euphoria")]


def mood_label(v: float) -> str:
    return next(label for upper, label in MOOD_ZONES if v < upper)


def story_tone(text: str) -> tuple[str, float]:
    b, s = len(BULL.findall(text)), len(BEAR.findall(text))
    score = (b - s) / max(1, b + s)
    return ("bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"), score


def agenda_flags(story: dict, flows: dict) -> list[str]:
    """Plain-language 'who benefits / how solid is this' notes for one story."""
    title = story["title"]
    flags = []
    lead = story["sources"][0]["name"] if story.get("sources") else ""
    if story["tier"] == 3 and not story["corroborated"] and not MAINSTREAM.search(lead):
        flags.append("Single source: no other outlet has reported it yet.")
    if INTERESTED.search(title) and TALKING_BOOK.search(title):
        flags.append("Interested party: a company that profits from bitcoin's price or products is talking about it.")
    if PRICE_MOVE.search(title) and story["category"] in ("Macro & liquidity", "Market structure", "Mining & network"):
        flags.append("Price-move story: these explain moves after the fact and rarely predict the next one.")
    etf = flows.get("etf", {})
    if FLOW_TALK.search(title) and "sum_7d" in etf:
        direction = "outflows" if etf["sum_7d"] < 0 else "inflows"
        said = "outflow" in title.lower() or "bleed" in title.lower() or "negative" in title.lower()
        if said == (etf["sum_7d"] < 0):
            flags.append(f"Checked: ETF data confirms 7-day net {direction} of ${abs(etf['sum_7d']):,.0f}m.")
        else:
            flags.append(f"Check: ETF data shows 7-day net {direction} of ${abs(etf['sum_7d']):,.0f}m, the opposite of the headline.")
    return flags


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def market_mood(stories: list[dict], flows: dict) -> dict:
    """0 = extreme fear, 100 = euphoria. Weighted blend of four inputs; missing inputs are skipped."""
    parts = []
    fg = flows.get("fear_greed", {})
    if "value" in fg:
        parts.append(("Fear & Greed Index", 0.40, float(fg["value"]), f'{fg["value"]} · {fg["label"]}'))
    if stories:
        avg = sum(s["tone_score"] for s in stories) / len(stories)
        n_bull = sum(s["tone"] == "bullish" for s in stories)
        n_bear = sum(s["tone"] == "bearish" for s in stories)
        parts.append(("News tone", 0.25, 50 + 50 * avg, f"{n_bear} bearish · {n_bull} bullish of {len(stories)}"))
    etf = flows.get("etf", {})
    if "sum_7d" in etf:
        parts.append(("ETF flows, 7 days", 0.20, _clamp(50 + etf["sum_7d"] / 1500 * 50),
                      f'{"+" if etf["sum_7d"] >= 0 else "−"}${abs(etf["sum_7d"]):,.0f}m'))
    ex = flows.get("exchanges", {})
    if ex.get("change_7d") is not None:
        parts.append(("Coins on exchanges, 7 days", 0.15, _clamp(50 - ex["change_7d"] / 50000 * 50),
                      f'{"+" if ex["change_7d"] >= 0 else "−"}{abs(ex["change_7d"]):,.0f} BTC'))
    if not parts:
        return {"value": None, "label": "Unavailable", "parts": []}
    w = sum(p[1] for p in parts)
    value = sum(p[1] * p[2] for p in parts) / w
    return {"value": value, "label": mood_label(value),
            "parts": [{"name": n, "weight": wt / w, "score": sc, "detail": d, "label": mood_label(sc)} for n, wt, sc, d in parts]}


def interpret(mood: dict, cycle: dict, flows: dict, stories: list[dict]) -> list[str]:
    """Rule-based 'how to read today'. Contrarian where history supports it; flows over headlines."""
    out = []
    zone = cycle["zone"]["key"]
    m = mood.get("value")
    if m is not None:
        if m < 40 and zone in ("strong-accumulate", "accumulate"):
            out.append(f"Mood is {mood['label'].lower()} while valuations are low (cycle score {cycle['score']:.0f}). "
                       "Historically, fearful headlines at low valuations have been accumulation time, not selling time.")
        elif m < 40:
            out.append(f"Mood is {mood['label'].lower()}, but valuations aren't cheap (cycle score {cycle['score']:.0f}). "
                       "Fear alone isn't a buy signal here; wait for the score to fall.")
        elif m >= 70 and (zone in ("scale-out", "take-profit") or cycle["exit"]["status"] in ("armed", "watch")):
            out.append(f"Mood is {mood['label'].lower()} late in the cycle. Euphoric headlines near highs are when institutions "
                       "tend to sell into retail demand; follow your scale-out plan.")
        elif m >= 70:
            out.append(f"Mood is {mood['label'].lower()}. Strong optimism with mid-range valuations: fine to hold, "
                       "but don't chase.")
        else:
            out.append(f"Mood is neutral ({m:.0f}/100). No extreme in either direction; the cycle score matters more today.")

    etf, ex = flows.get("etf", {}), flows.get("exchanges", {})
    if stories and "sum_7d" in etf:
        bear_news = sum(s["tone"] == "bearish" for s in stories) > sum(s["tone"] == "bullish" for s in stories)
        money_in = etf["sum_7d"] > 0
        if bear_news and money_in:
            out.append(f"Headlines lean bearish, yet ETFs took in ${etf['sum_7d']:,.0f}m over 7 days: money is buying the bad news.")
        elif not bear_news and not money_in:
            out.append(f"Headlines lean upbeat, but ETFs saw ${abs(etf['sum_7d']):,.0f}m of outflows over 7 days: "
                       "follow the flows, not the tone.")
        elif bear_news and not money_in:
            out.append(f"Headlines and money agree: both negative (ETF outflows ${abs(etf['sum_7d']):,.0f}m over 7 days). "
                       "Selling pressure is real, but it often exhausts itself when fear is high.")
        else:
            out.append(f"Headlines and money agree: both positive (ETF inflows ${etf['sum_7d']:,.0f}m over 7 days).")
    if etf.get("movers_7d") and "sum_7d" in etf and abs(etf["sum_7d"]) > 100:
        top_f, top_v = etf["movers_7d"][0]
        share = abs(top_v) / max(sum(abs(v) for _, v in etf["movers_7d"]), 1)
        if share > 0.6:
            out.append(f"{share:.0%} of the 7-day ETF movement came from one fund ({top_f}, "
                       f"{'+' if top_v >= 0 else '−'}${abs(top_v):,.0f}m). A single large client can drive that; "
                       "it is less of a broad trend than the total suggests.")
    if ex.get("change_7d") is not None and abs(ex["change_7d"]) > 10000:
        if ex["change_7d"] > 0:
            out.append(f"{ex['change_7d']:,.0f} BTC moved onto exchanges this week. Coins on exchanges can be sold quickly, "
                       "so this adds short-term supply.")
        else:
            out.append(f"{abs(ex['change_7d']):,.0f} BTC left exchanges this week, usually holders moving coins into "
                       "long-term storage.")
    mn = cycle.get("mining")
    if mn and mn["zone"] in ("capitulation", "squeeze"):
        out.append(f"Mining: price is {abs(mn['price_vs_all_in']) * 100:.0f}% below miners' estimated all-in cost "
                   f"(${mn['all_in_cost'] / 1000:,.0f}k). {'Below even the electricity cost, ' if mn['zone'] == 'capitulation' else ''}"
                   "Squeezed miners tend to sell coins, which adds supply now but has historically come near bottoms.")
    fg = flows.get("fear_greed", {})
    if fg.get("month_ago") is not None and abs(fg["value"] - fg["month_ago"]) >= 20:
        out.append(f"The Fear & Greed Index moved from {fg['month_ago']} a month ago to {fg['value']}: "
                   f"sentiment has {'cooled' if fg['value'] < fg['month_ago'] else 'heated up'} sharply.")
    return out
