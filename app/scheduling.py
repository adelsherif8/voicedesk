"""Live booking for the plumbing agent: today's and tomorrow's truck board, worked out from the seed
schedule plus every booking the agent has made.

Bookings are ordinary records (meta: date, window), so the board survives a restart the same way the
records do: they are replayed from Retell in order, and each replay re-runs the same availability check.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.agents import AGENTS_BY_ID

TZ = ZoneInfo("America/New_York")
WINDOWS = ["8-10am", "10am-12pm", "12-2pm", "2-4pm", "4-6pm"]
_START = [8, 10, 12, 14, 16]
DAYS = ["today", "tomorrow"]


def _now(ts: float | None = None) -> datetime:
    return datetime.fromtimestamp(ts, TZ) if ts else datetime.now(TZ)


def date_for(day: str, ts: float | None = None) -> str:
    """'today' or 'tomorrow', as seen at ts in the business's timezone, as an ISO date."""
    return (_now(ts) + timedelta(days=DAYS.index(day))).date().isoformat()


def slot_label(day: str, window: str, ts: float | None = None) -> tuple[str, str]:
    """('Mon Nov 2, 2-4pm', '2026-11-02') for a day and window."""
    when = _now(ts) + timedelta(days=DAYS.index(day))
    return f"{when:%a %b} {when.day}, {window}", when.date().isoformat()


def _seed(agent: str, iso: str, ts: float | None) -> list[dict]:
    """Each truck's five windows: the seed jobs on today's board, open otherwise."""
    today = iso == _now(ts).date().isoformat()
    trucks = []
    for t in AGENTS_BY_ID[agent].get("trucks", []):
        slots = []
        for s in t["slots"]:
            job = s.split(" ", 1)[1] if today and " " in s else ""
            slots.append({"job": job} if job else None)
        trucks.append({"n": t["n"], "slots": slots})
    return trucks


def board(agent: str, iso: str, ts: float | None = None) -> list[dict]:
    """The trucks for one date, with the agent's bookings placed in the first free truck, oldest first."""
    trucks = _seed(agent, iso, ts)
    rows = [r for r in db.list_records(agent, limit=2000) if (r.get("meta") or {}).get("date") == iso]
    for r in sorted(rows, key=lambda r: r.get("created") or 0):
        w = (r["meta"]).get("window")
        if w not in WINDOWS:
            continue
        i = WINDOWS.index(w)
        for t in trucks:
            if t["slots"][i] is None:
                t["slots"][i] = {"ai": True, "name": (r.get("name") or "").split(" ")[0], "job": r.get("intent") or ""}
                break
    return trucks


def open_windows(agent: str, day: str, ts: float | None = None) -> list[str]:
    """Windows on that day with a free truck, skipping today's windows that have already started."""
    iso = date_for(day, ts)
    hour = _now(ts).hour if day == "today" else -1
    trucks = board(agent, iso, ts)
    return [w for i, w in enumerate(WINDOWS)
            if _START[i] > hour and any(t["slots"][i] is None for t in trucks)]


def availability_text(agent: str, ts: float | None = None) -> str:
    parts = []
    for day in DAYS:
        ws = open_windows(agent, day, ts)
        parts.append(f"{day.capitalize()}: {', '.join(ws) if ws else 'fully booked'}.")
    return " ".join(parts) + " Offer the caller two of these, never the whole list."


def check_booking(agent: str, args: dict, ts: float | None = None) -> tuple[bool, str]:
    """Is the requested day and window still free? Returns (ok, the sentence for the agent)."""
    day = str(args.get("day") or "").strip().lower()
    window = str(args.get("window") or "").strip()
    if day not in DAYS or window not in WINDOWS:
        return False, "Not booked: day must be today or tomorrow and window one of " + ", ".join(WINDOWS) + "."
    if window not in open_windows(agent, day, ts):
        return False, f"Not booked: {day} {window} is no longer free. {availability_text(agent, ts)}"
    return True, ""
