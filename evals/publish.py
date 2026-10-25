"""Publishing runs to VoiceDesk.

`--publish` does two things:
  1. POSTs the run to <url>/evals/ingest (Authorization: Bearer $EVALS_INGEST_TOKEN)
  2. updates evals/results/published.json, the committed snapshot VoiceDesk loads on boot
     when its tables are empty (Render's free disk is wiped on every deploy)
The snapshot keeps the latest full run per model with transcripts, plus summary-only
history for the trend lines, so it stays small.

Publish guard: both steps first scan the run (transcripts, tool events, check details,
scenario definitions) with the deterministic PII detector plus the dictionary of every
persona and fixture name. Any hit raises PIIDetected and nothing is written or sent.
"""

import json
import os
import urllib.error
import urllib.request

from evals import config, pii

SNAPSHOT = config.RESULTS_DIR / "published.json"


class PIIDetected(RuntimeError):
    pass


def guard(run: dict) -> None:
    """Raise PIIDetected if any result in `run` still holds detectable personal data."""
    found = pii.scan_run(run, pii.known_names())
    if found:
        shown = "; ".join(f"{f['type']} at {f['path']}" for f in found[:5])
        raise PIIDetected(f"{len(found)} PII value(s) in the run: {shown}" + (" ..." if len(found) > 5 else ""))
HISTORY = 20
DEFAULT_URL = os.getenv("EVALS_PUBLISH_URL", "http://127.0.0.1:8000")


def summary_only(run: dict) -> dict:
    return {k: v for k, v in run.items() if k != "results"}


def update_snapshot(run: dict) -> str:
    guard(run)
    snap = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {"history": [], "latest": {}}
    history = [h for h in snap["history"] if h["id"] != run["id"]] + [summary_only(run)]
    snap["history"] = sorted(history, key=lambda h: h["created"])[-HISTORY:]
    snap["latest"][run["agent_model"]] = run
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, separators=(",", ":")))
    return str(SNAPSHOT.relative_to(config.ROOT))


def post(run: dict, url: str = DEFAULT_URL) -> str:
    guard(run)
    req = urllib.request.Request(
        url.rstrip("/") + "/evals/ingest", method="POST", data=json.dumps(run).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {os.environ['EVALS_INGEST_TOKEN']}"}
                    if os.getenv("EVALS_INGEST_TOKEN") else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return f"publish failed: {url} answered but isn't VoiceDesk ({raw[:60]!r})"
        if not body.get("ok"):
            return f"publish failed: {body}"
        return f"published to {url.rstrip('/')}/evals ({body.get('results', 0)} results)"
    except urllib.error.HTTPError as e:
        return f"publish failed: HTTP {e.code} {e.read().decode()[:200]}"
    except urllib.error.URLError as e:
        return f"publish failed: {url} unreachable ({e.reason}); snapshot still updated"
