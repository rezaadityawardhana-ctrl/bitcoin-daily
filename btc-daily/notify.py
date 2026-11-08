"""Push notification to your phone via ntfy (https://ntfy.sh): free, no account needed.

Setup: install the ntfy app on your iPhone, tap +, and subscribe to the topic name in NTFY_TOPIC.
Tapping the notification opens DASHBOARD_URL (the hosted dashboard).

Run on its own to (re)send the latest summary:  python3 notify.py
"""
import json
import os
import urllib.request

from common import OUTPUT_DIR, SSL_CONTEXT, USER_AGENT, load_env

ZONE_TAGS = {  # ntfy turns these tag names into emoji in the notification
    "strong-accumulate": "large_blue_circle", "accumulate": "blue_circle", "hold": "white_circle",
    "scale-out": "orange_circle", "take-profit": "red_circle",
}


def build_payload(summary: dict) -> dict:
    url = os.environ.get("DASHBOARD_URL", "").strip()
    payload = {
        "topic": os.environ["NTFY_TOPIC"].strip(),
        "title": summary["title"],
        "message": summary["message"],
        "tags": (["rotating_light"] if summary.get("priority", 3) >= 5 else [])
                + [ZONE_TAGS.get(summary["zone_key"], "white_circle")],
        # 5 = exit signal fired, 4 = new all-time high in exit window or zone change, 3 = normal day
        "priority": summary.get("priority", 3),
    }
    if url:
        payload["click"] = url
        payload["actions"] = [{"action": "view", "label": "Open dashboard", "url": url, "clear": True}]
    return payload


def send(summary: dict) -> None:
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if os.environ.get("NTFY_TOKEN"):  # only needed for a protected/self-hosted ntfy server
        headers["Authorization"] = f"Bearer {os.environ['NTFY_TOKEN']}"
    req = urllib.request.Request(server, data=json.dumps(build_payload(summary)).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
        resp.read()


def main():
    load_env()
    if not os.environ.get("NTFY_TOPIC"):
        raise SystemExit("NTFY_TOPIC is not set (see .env.example).")
    summary = json.loads((OUTPUT_DIR / "summary.json").read_text())
    send(summary)
    print(f"Notification sent to topic {os.environ['NTFY_TOPIC']}")


if __name__ == "__main__":
    main()
