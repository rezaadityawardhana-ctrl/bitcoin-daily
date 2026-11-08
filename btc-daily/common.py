"""Shared helpers: settings loading and HTTP fetching (standard library only)."""
import json
import os
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
USER_AGENT = "Mozilla/5.0 (compatible; btc-daily-dashboard/1.0)"


def load_env() -> None:
    """Read KEY=VALUE lines from .env into os.environ (existing env vars win)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _ssl_context() -> ssl.SSLContext:
    """Verified TLS context. python.org builds on macOS ship without CA certs, so fall back
    to certifi (if installed) or the macOS system bundle. Verification is never disabled."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    ctx = ssl.create_default_context()
    if Path("/etc/ssl/cert.pem").exists():
        ctx.load_verify_locations("/etc/ssl/cert.pem")
    return ctx


SSL_CONTEXT = _ssl_context()


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
        return resp.read()


def http_json(url: str, timeout: int = 30):
    return json.loads(http_get(url, timeout))


def wait_for_network(max_wait: int = 300) -> bool:
    """After the Mac wakes from sleep, Wi-Fi can take a minute to come back. Poll until online."""
    import time
    deadline = time.time() + max_wait
    while True:
        try:
            http_get("https://api.coinbase.com/v2/time", timeout=10)
            return True
        except Exception:
            if time.time() > deadline:
                return False
            time.sleep(15)
