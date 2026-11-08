"""Daily news: gather from tiered sources, drop noise, merge duplicates, rank, then
(optionally) have Claude write a neutral, cited summary.

Tier 1 = primary/official sources, Tier 2 = institutional research, Tier 3 = news outlets.
Edit FEEDS / NOISE / CATEGORIES to change what gets through.
"""
import email.utils
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from common import http_get

GNEWS = ("https://news.google.com/rss/search?q=bitcoin+when:2d+(site:reuters.com+OR+site:bloomberg.com"
         "+OR+site:ft.com+OR+site:wsj.com+OR+site:cnbc.com+OR+site:apnews.com)&hl=en-US&gl=US&ceid=US:en")

# Glassnode's research feed (insights.glassnode.com/rss) blocks scripted readers, so it isn't listed.
# name, url, tier, filter: "btc" = must mention bitcoin/btc, "crypto" = crypto-related headline, "fed"/"sec" = topic filters, None = keep all
FEEDS = [
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", 1, "fed"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss", 1, "sec"),
    ("Bitcoin Optech", "https://bitcoinops.org/feed.xml", 1, None),
    ("Coin Metrics", "https://coinmetrics.substack.com/feed", 2, None),
    ("Mainstream (Reuters/Bloomberg/FT/WSJ/CNBC/AP)", GNEWS, 3, "crypto"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", 3, "btc"),
    ("The Block", "https://www.theblock.co/rss.xml", 3, "btc"),
    ("Blockworks", "https://blockworks.co/feed", 3, "btc"),
    ("Decrypt", "https://decrypt.co/feed", 3, "btc"),
]
MAX_AGE = {1: timedelta(days=3), 2: timedelta(days=7), 3: timedelta(hours=48)}

BTC_RE = re.compile(r"\b(bitcoin|btc)\b", re.I)
FED_RE = re.compile(r"FOMC|monetary policy|federal funds|interest rate|Beige Book|balance sheet", re.I)
CRYPTO_RE = re.compile(r"\b(bitcoin|btc|crypto\w*|digital asset|stablecoin|Coinbase|Binance|spot ETF)\b", re.I)
SEC_RE = re.compile(r"bitcoin|crypto|digital asset|\bETF|\bETP|stablecoin", re.I)
NOISE = re.compile(
    r"price prediction|could (hit|reach|soar)|to the moon|\bwill (hit|reach)\b|top \d+ |altcoin|memecoin|meme coin"
    r"|dogecoin|shiba|pepe|presale|airdrop|sponsored|giveaway|casino|betting|here'?s why|what'?s next for"
    r"|price analysis|technical analysis|whale alert|\bvs\.? ethereum\b|influencer|podcast|newsletter:|daybook"
    r"|market wrap|stock price|quotes and news|latest news$|trending news|latest updates|this week in|crypto (stocks|markets) today|fear (and|&) greed",
    re.I,
)
CATEGORIES = [  # (category, weight, pattern) - matched with word boundaries, case-insensitive
    ("Regulation & policy", 3, r"SEC|CFTC|regulat\w*|laws?|legislation|bill|congress|senate|treasury|sanctions?|court|lawsuit|ban(s|ned)?|tax(es)?|strategic reserve|government"),
    ("ETFs & institutions", 3, r"ETFs?|ETPs?|inflows?|outflows?|BlackRock|Fidelity|institution\w*|MicroStrategy|Strategy|banks?|custod\w*|pension|sovereign|corporate treasur\w*"),
    ("Macro & liquidity", 2, r"Fed|FOMC|rates?|inflation|CPI|jobs|payrolls|dollar|yields?|liquidity|recession|tariffs?|Powell|selloff"),
    ("Protocol & security", 2, r"BIPs?|soft fork|upgrade|Bitcoin Core|vulnerabilit\w*|exploit\w*|hack\w*|heist|Lightning|quantum|mempool|consensus|Optech"),
    ("Mining & network", 2, r"miners?|mining|hashrate|hash rate|difficulty|halving|energy"),
    ("Market structure", 1, r"liquidat\w*|futures|options|open interest|funding|exchanges?|stablecoins?|on-chain|long-term holders?|supply"),
]


def _text(el, tag):
    found = el.find(tag)
    return (found.text or "").strip() if found is not None and found.text else ""


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(s: str):
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_feed(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    atom = "{http://www.w3.org/2005/Atom}"
    items = []
    for it in root.iter("item"):
        src = it.find("source")
        items.append({
            "title": _clean(_text(it, "title")), "link": _text(it, "link"),
            "summary": _clean(_text(it, "description"))[:600],
            "published": _parse_date(_text(it, "pubDate")),
            "outlet": (src.text or "").strip() if src is not None else None,
        })
    for it in root.iter(f"{atom}entry"):
        link = it.find(f"{atom}link")
        items.append({
            "title": _clean(_text(it, f"{atom}title")),
            "link": link.get("href", "") if link is not None else "",
            "summary": _clean(_text(it, f"{atom}summary") or _text(it, f"{atom}content"))[:600],
            "published": _parse_date(_text(it, f"{atom}updated") or _text(it, f"{atom}published")),
            "outlet": None,
        })
    return items


def _keep(item, rule) -> bool:
    text = f"{item['title']} {item['summary']}"
    if NOISE.search(item["title"]):
        return False
    if rule == "btc":
        return bool(BTC_RE.search(text))
    if rule == "crypto":
        return bool(CRYPTO_RE.search(item["title"]))
    if rule == "fed":
        return bool(FED_RE.search(text))
    if rule == "sec":
        return bool(SEC_RE.search(text))
    return True


def _tokens(title: str) -> set:
    stop = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "as", "is", "at", "by", "with", "its",
            "bitcoin", "btc", "crypto", "after", "from", "amid", "over", "says"}
    return {w for w in re.findall(r"[a-z0-9$]+", title.lower()) if w not in stop and len(w) > 2}


def gather(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    items, failures = [], []
    for name, url, tier, rule in FEEDS:
        try:
            for it in parse_feed(http_get(url, timeout=20)):
                if not it["title"] or not it["published"] or now - it["published"] > MAX_AGE[tier]:
                    continue
                if not _keep(it, rule):
                    continue
                it.update(source=it.pop("outlet") or name, tier=tier)
                if tier == 3 and name.startswith("Mainstream"):
                    # Google News titles end with " - Outlet"
                    it["title"] = re.sub(r"\s+-\s+[^-]+$", "", it["title"])
                items.append(it)
        except Exception as exc:
            failures.append(f"{name}: {exc}")

    # categorise
    for it in items:
        text = f"{it['title']} {it['summary']}"
        hits = [(c, w) for c, w, pat in CATEGORIES if re.search(rf"\b(?:{pat})\b", text, re.I)]
        it["category"] = hits[0][0] if hits else "Other"
        it["cat_weight"] = max((w for _, w in hits), default=0)

    # merge duplicates (same story from several outlets) by title-word overlap
    clusters = []
    for it in sorted(items, key=lambda x: x["tier"]):
        toks = _tokens(it["title"])
        for c in clusters:
            inter = len(toks & c["tokens"])
            if toks and inter / min(len(toks), len(c["tokens"]) or 1) >= 0.6 and inter >= 3:
                c["items"].append(it)
                c["tokens"] |= toks
                break
        else:
            clusters.append({"tokens": toks, "items": [it]})

    stories = []
    for c in clusters:
        lead = c["items"][0]
        sources = sorted({i["source"] for i in c["items"]})
        score = (4 - lead["tier"]) * 2 + lead["cat_weight"] * 2 + min(len(sources), 4) * 1.5
        if lead["category"] == "Other" and lead["tier"] == 3:
            score -= 4  # uncategorised outlet chatter
        stories.append({
            "title": lead["title"], "summary": lead["summary"], "category": lead["category"],
            "tier": lead["tier"], "score": score, "corroborated": len(sources) >= 2,
            "published": max(i["published"] for i in c["items"]).isoformat(),
            "sources": [{"name": i["source"], "link": i["link"], "tier": i["tier"]} for i in c["items"]][:5],
        })
    stories.sort(key=lambda s: -s["score"])
    research = [s for s in stories if s["tier"] == 2][:4]
    top = [s for s in stories if s["tier"] != 2 and s["score"] >= 6][:7]
    return {"top": top, "research": research, "scanned": len(items), "failures": failures}


SYSTEM_PROMPT = """You are the editor of a neutral daily Bitcoin brief for a long-term holder.
You receive pre-filtered stories (headline, RSS summary, sources with tier: 1 primary/official,
2 institutional research, 3 news outlet) plus today's on-chain cycle metrics.

Rules:
- Use only the information provided. Never add facts, numbers or events from memory.
- Neutral, plain language. No hype, no price predictions, no buy/sell instructions.
- Label each item: "fact" (official/primary or reported by 2+ independent outlets),
  "report" (a single outlet's reporting), or "analysis" (research or opinion).
- For "analysis" items, and any item whose impact is debatable, give one bull and one bear reading.
- Keep "why it matters" to the long-term (months/years) view, not today's price.
- If a story is minor or repeats another, drop it. Fewer, better items beat more.
- key_points: the 2-3 takeaways a busy holder needs, each one plain sentence of at most 20 words.
- If nothing material happened, set quiet_day to true and say so in the overview."""

SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string", "description": "2-3 sentence neutral overview of the day"},
        "key_points": {"type": "array", "items": {"type": "string"},
                       "description": "The day's 2-3 most important takeaways, max 20 words each"},
        "quiet_day": {"type": "boolean"},
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "story_index": {"type": "integer"},
                "headline": {"type": "string"},
                "what_happened": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "label": {"type": "string", "enum": ["fact", "report", "analysis"]},
                "bull_view": {"type": "string"},
                "bear_view": {"type": "string"},
            },
            "required": ["story_index", "headline", "what_happened", "why_it_matters", "label",
                         "bull_view", "bear_view"],
            "additionalProperties": False,
        }},
        "research_takeaways": {"type": "array", "items": {
            "type": "object",
            "properties": {"story_index": {"type": "integer"}, "takeaway": {"type": "string"}},
            "required": ["story_index", "takeaway"], "additionalProperties": False,
        }},
    },
    "required": ["overview", "key_points", "quiet_day", "items", "research_takeaways"],
    "additionalProperties": False,
}


def summarize(news: dict, cycle: dict) -> dict | None:
    """Claude-written brief. Returns None (dashboard falls back to filtered headlines) when
    the anthropic package or credentials are missing, or on any API error."""
    if os.environ.get("BTC_DAILY_NO_AI"):
        return None
    try:
        import anthropic
    except ImportError:
        return None

    stories = news["top"] + news["research"]
    if not stories:
        return None
    payload = {
        "cycle_metrics": {
            "date": cycle["as_of"], "cycle_score_0_100": round(cycle["score"], 1),
            "zone": cycle["zone"]["label"], "drawdown_from_ath": round(cycle["ath"]["drawdown"], 3),
            "indicators": {i["name"]: round(i["value"], 3) for i in cycle["indicators"]},
        },
        "stories": [
            {"index": i, "headline": s["title"], "rss_summary": s["summary"], "category": s["category"],
             "sources": [{"name": x["name"], "tier": x["tier"]} for x in s["sources"]]}
            for i, s in enumerate(stories)
        ],
    }
    try:
        client = anthropic.Anthropic()
        response = client.beta.messages.create(
            model="claude-opus-5-5",
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        if response.stop_reason == "refusal":
            return None
        text = next(b.text for b in response.content if b.type == "text")
        brief = json.loads(text)
        brief["model"] = response.model
        return brief
    except Exception as exc:
        print(f"[news] AI summary skipped: {exc}")
        return None
