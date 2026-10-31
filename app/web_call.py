"""Browser "Talk to this agent" calls: mints Retell web-call tokens behind cost limits.

The API key stays on this server. The browser only ever gets the short-lived token for
one call. Limits live in this process, so a restart clears them. Render's free plan
restarts after 15 idle minutes, so the daily count is reloaded from Retell's own call
list on the first request after boot; if that lookup fails, no call is started.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger("voicedesk.web_call")

API = "https://api.retellai.com"
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_IDS = os.path.join(_HERE, "docs", "retell_created.json")  # gitignored provisioning state

# Pages that offer a call, with a button colour that keeps white text readable on that page.
CALL_COLORS = {
    "receptionist": "#2f5d8a", "recovery": "#0f4c81", "dental": "#0b6f71", "realty": "#0b2545",
    "restaurant": "#9b1c1c", "support": "#1428a0", "voicemail": "#1f2933",
}

MSG_IP_LIMIT = "You have used your demo calls for this hour. Please try again a little later."
MSG_DAY_LIMIT = "The demo line has reached its call limit for today. Please try again tomorrow."
MSG_UNAVAILABLE = "The demo line is not available right now. Please try again in a few minutes."


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def api_key() -> str:
    return os.environ.get("RETELL_API_KEY", "").strip()


def max_seconds() -> int:
    # Retell accepts 60s to 2h for max_call_duration_ms.
    return max(60, _int_env("WEB_CALL_MAX_SECONDS", 180))


def agent_ids() -> dict:
    """slug -> Retell agent id: RETELL_AGENT_IDS (JSON) in production, the local state file in dev."""
    raw = os.environ.get("RETELL_AGENT_IDS", "").strip()
    if raw:
        try:
            ids = json.loads(raw)
        except ValueError:
            log.error("RETELL_AGENT_IDS is not valid JSON")
            return {}
    elif os.path.exists(_LOCAL_IDS):
        with open(_LOCAL_IDS) as f:
            ids = {slug: v.get("agent_id") for slug, v in json.load(f).items()}
    else:
        return {}
    return {slug: aid for slug, aid in ids.items() if slug in CALL_COLORS and aid}


def retell(path: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    """One Retell API call. Raises on any failure; callers never pass upstream text to a client."""
    req = urllib.request.Request(
        f"{API}/{path}", method="POST" if body is not None else "GET",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


# ---- limits ----
class Limits:
    def __init__(self):
        self.lock = threading.Lock()
        self.ip_hits: dict[str, list[float]] = {}
        self.day = None
        self.day_count = 0
        self.hydrated = False

    def _roll_day(self, now: float) -> None:
        day = int(now // 86400)
        if day != self.day:
            self.day, self.day_count = day, 0

    def hydrate(self, now: float) -> None:
        """After a restart, count today's joined web calls from Retell so the daily limit survives."""
        if self.hydrated:
            return
        ids = list(agent_ids().values())
        midnight_ms = int(now // 86400) * 86400 * 1000
        out = retell("v3/list-calls", {
            "filter_criteria": {
                "agent": [{"agent_id": a} for a in ids],
                "call_type": {"type": "enum", "op": "in", "value": ["web_call"]},
                "start_timestamp": {"type": "number", "op": "ge", "value": midnight_ms},
            },
            "limit": 1, "include_total": True,
        })
        with self.lock:
            self._roll_day(now)
            if not self.hydrated:
                self.day_count += int(out["total"])
                self.hydrated = True

    def reserve(self, ip: str, now: float) -> str | None:
        """Take a slot, or return which limit stopped it ("ip" or "day")."""
        with self.lock:
            self._roll_day(now)
            for k in [k for k, v in self.ip_hits.items() if not v or v[-1] <= now - 3600]:
                del self.ip_hits[k]
            hits = [t for t in self.ip_hits.get(ip, []) if t > now - 3600]
            if len(hits) >= _int_env("WEB_CALL_PER_IP_HOURLY", 3):
                return "ip"
            if self.day_count >= _int_env("WEB_CALL_GLOBAL_DAILY", 30):
                return "day"
            hits.append(now)
            self.ip_hits[ip] = hits
            self.day_count += 1
            return None

    def release(self, ip: str, now: float) -> None:
        """Give a slot back when Retell created no call."""
        with self.lock:
            self._roll_day(now)
            self.day_count = max(0, self.day_count - 1)
            if self.ip_hits.get(ip):
                self.ip_hits[ip].pop()


limits = Limits()


# ---- request checks ----
def same_origin(headers) -> bool:
    """Browsers always send Origin on POST; a page on another site cannot forge it.

    (A script outside a browser can, which is what the rate limits are for.)
    """
    origin = headers.get("origin", "").strip().rstrip("/")
    if not origin or headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return False
    allowed = [o.strip().rstrip("/") for o in os.environ.get("WEB_CALL_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return origin in allowed or urlsplit(origin).netloc == headers.get("host", "")


def client_ip(request) -> str:
    """Per-IP key. WEB_CALL_CLIENT_IP_HEADER names the header our proxy overwrites (render.yaml);
    without it nothing client-supplied is trusted, so a caller cannot pick their own bucket."""
    header = os.environ.get("WEB_CALL_CLIENT_IP_HEADER", "").strip()
    if header:
        ip = request.headers.get(header, "").strip()
        if ip:
            return ip
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


# ---- what the page shows ----
_storage: dict[str, str] = {}


def _records_calls(agent_id: str) -> bool:
    """Whether Retell keeps recordings for this agent. If unknown, say it may record."""
    if agent_id not in _storage:
        try:
            _storage[agent_id] = retell(f"get-agent/{agent_id}", timeout=2.0).get("data_storage_setting") or "everything"
        except Exception as e:
            log.warning("could not read agent storage setting: %s", type(e).__name__)
            return True
    return _storage[agent_id] != "basic_attributes_only"


def page_config(slug: str) -> dict | None:
    """The button's settings, or None to hide it (no key, or no Retell agent for this page)."""
    aid = agent_ids().get(slug) if api_key() else None
    if not aid:
        return None
    return {"slug": slug, "color": CALL_COLORS[slug], "max_seconds": max_seconds(),
            "minutes": max_seconds() // 60, "recorded": _records_calls(aid)}


# ---- token ----
def start(slug: str, ip: str) -> tuple[int, dict]:
    """Returns (status, JSON body). The success body is what the browser SDK needs for one call."""
    aid = agent_ids().get(slug)
    if not api_key() or not aid:
        return 404, {"ok": False, "reason": "unavailable", "message": MSG_UNAVAILABLE}
    now = time.time()
    try:
        limits.hydrate(now)
    except Exception as e:
        log.error("could not read today's call count: %s", type(e).__name__)
        return 503, {"ok": False, "reason": "unavailable", "message": MSG_UNAVAILABLE}
    hit = limits.reserve(ip, now)
    if hit:
        return 429, {"ok": False, "reason": "limit", "scope": hit,
                     "message": MSG_IP_LIMIT if hit == "ip" else MSG_DAY_LIMIT}
    try:
        call = retell("v3/create-web-call", {
            "agent_id": aid,
            # per-call override: the stored agents allow 10 minutes
            "agent_override": {"agent": {"max_call_duration_ms": max_seconds() * 1000}},
            "metadata": {"source": "voicedesk-web-demo", "slug": slug},
        })
        return 201, {k: call[k] for k in ("call_id", "access_token", "transport", "ice_servers", "expires_at")}
    except urllib.error.HTTPError as e:
        limits.release(ip, now)
        log.error("create-web-call failed for %s: HTTP %s", slug, e.code)
    except Exception as e:
        limits.release(ip, now)
        log.error("create-web-call failed for %s: %s", slug, type(e).__name__)
    return 503, {"ok": False, "reason": "unavailable", "message": MSG_UNAVAILABLE}
