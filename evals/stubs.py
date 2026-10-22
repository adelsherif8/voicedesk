"""Tool executors for the agent under test.

The live webhooks (/retell/<agent>) only store the payload and answer with one fixed
sentence, so the stub returns that exact sentence: the agent sees what it sees in
production. Behind it, a resource built from the same data VoiceDesk shows on the
dashboards records what the call consumed, so a booking really takes a slot and a
double-booking or an invented unit size is caught by the checks.

Resource kinds (pick one in evals/agents/<id>.yaml under `resource.kind`):
  calendar     provider schedule, e.g. dental     (registry: schedule)
  inventory    unit sizes with stock, e.g. storage (registry: inventory)
  truck_board  2-hour windows per truck, e.g. plumbing (registry: trucks)
"""

import re

LIVE_RESULT = "Saved. The details are recorded in the system."   # app/main.py retell_webhook

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b", re.I)
_AMPM = r"(a\.?m\.?|p\.?m\.?)?"
_TIME_RE = re.compile(
    r"\b(\d{1,2})(?!\d)(?::(\d{2}))?\s*" + _AMPM +                  # start: 2, 2:30, 2pm
    r"(?:\s*(?:-|–|to)\s*(\d{1,2})(?!\d)(?::\d{2})?\s*" + _AMPM + r")?",  # optional end: -4pm
    re.I)


def parse_day(text: str, today: str) -> str | None:
    t = (text or "").lower()
    if "tomorrow" in t:
        return DAYS[(DAYS.index(today) + 1) % 7]
    if "today" in t or "tonight" in t or "right now" in t or re.search(r"\bnow\b", t):
        return today
    m = _DAY_RE.search(t)
    return m.group(1).title() if m else None


def parse_time(text: str, assume_pm_below: int = 8) -> int | None:
    """Minutes after midnight for the first clock time in `text` ('2:30 PM', '2-4pm',
    '10am'). Bare hours below `assume_pm_below` are read as afternoon, the way the
    dashboards write them ('1:00 Root canal')."""
    t = (text or "").lower()
    if "noon" in t:
        return 12 * 60
    for m in _TIME_RE.finditer(t):
        h, mins = int(m.group(1)), int(m.group(2) or 0)
        ampm = (m.group(3) or "").replace(".", "")
        end_h, end_ampm = m.group(4), (m.group(5) or "").replace(".", "")
        if h > 23 or mins > 59 or not (m.group(2) or ampm or end_h):
            continue  # a bare number like "2 kids" or "14," in a date is not a time
        if not ampm and end_ampm:
            # "2-4pm" -> 2 PM, "12-2pm" -> noon, "10-12pm" -> 10 AM, "11-1pm" -> 11 AM
            eh = int(end_h)
            ampm = "pm" if end_ampm == "pm" and (h == 12 or (h < eh and eh != 12)) else "am"
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        elif not ampm and h < assume_pm_below:
            h += 12
        return h * 60 + mins
    return None


def fmt(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{(h - 1) % 12 + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"


class Calendar:
    """Provider x weekday grid of appointment start times."""

    def __init__(self, registry: dict, cfg: dict):
        self.today = cfg.get("today", "Mon")
        self.start = parse_time(cfg.get("hours", {}).get("start", "8:00 AM"))
        self.end = parse_time(cfg.get("hours", {}).get("end", "5:00 PM"))
        self.step = int(cfg.get("hours", {}).get("step_min", 30))
        self.open_days = cfg.get("open_days", DAYS[:5])
        self.booked = {(p, d, parse_time(s)) for p, days in registry.get("schedule", {}).items()
                       for d, slots in days.items() for s in slots}
        self.providers = list(registry.get("schedule", {}))

    def provider(self, text: str) -> str | None:
        t = (text or "").lower()
        return next((p for p in self.providers if any(w in t for w in re.findall(r"[a-z]+", p.lower()) if len(w) > 2 and w not in ("dr", "hygiene"))), None)

    def free(self, provider: str, day: str) -> list[int]:
        if day not in self.open_days:
            return []
        return [t for t in range(self.start, self.end, self.step) if (provider, day, t) not in self.booked]

    def apply(self, args: dict) -> dict | None:
        appt = args.get("appointment") or ""
        if not appt or re.search(r"cancel", args.get("outcome", ""), re.I):
            return None
        prov, day, time = self.provider(args.get("provider", "")), parse_day(appt, self.today), parse_time(appt)
        eff = {"kind": "booking", "requested": appt, "provider": prov, "day": day,
               "time": fmt(time) if time is not None else None}
        if prov is None:
            return {**eff, "ok": False, "reason": "unknown provider"}
        if day is None or time is None:
            return {**eff, "ok": False, "reason": "could not read day and time"}
        if day not in self.open_days or not (self.start <= time < self.end):
            return {**eff, "ok": False, "reason": "outside opening hours"}
        if (prov, day, time) in self.booked:
            return {**eff, "ok": False, "reason": "slot already booked"}
        self.booked.add((prov, day, time))
        return {**eff, "ok": True}


class Inventory:
    """Unit sizes with stock; a reservation takes one unit."""

    def __init__(self, registry: dict, cfg: dict):
        held = cfg.get("reserved", {})
        self.units = {u["size"]: {"price": u["price"], "left": u["total"] - held.get(u["size"], 0)}
                      for u in registry.get("inventory", [])}

    def size(self, text: str) -> str | None:
        t = (text or "").lower().replace(" ", "").replace("×", "x")
        cc = "climate" in t or "cc" in t
        dims = re.search(r"\d+x\d+", t)
        if not dims:
            return None
        want = dims.group(0) + (" CC" if cc else "")
        return next((s for s in self.units if s.lower().replace(" ", "") == want.lower().replace(" ", "")), None)

    def apply(self, args: dict) -> dict | None:
        if not re.search(r"reserv", args.get("outcome", ""), re.I):
            return None
        size = self.size(args.get("unit_size", ""))
        eff = {"kind": "reservation", "requested": args.get("unit_size", ""), "size": size}
        if size is None:
            return {**eff, "ok": False, "reason": "unit size not in inventory"}
        if self.units[size]["left"] <= 0:
            return {**eff, "ok": False, "reason": "no units left"}
        self.units[size]["left"] -= 1
        return {**eff, "ok": True, "left": self.units[size]["left"]}


class TruckBoard:
    """Today's five 2-hour windows per truck. Other days have no data, so a booking
    on another day is recorded but can't be verified."""

    WINDOWS = [8 * 60, 10 * 60, 12 * 60, 14 * 60, 16 * 60]

    def __init__(self, registry: dict, cfg: dict):
        self.today = cfg.get("today", "Mon")
        self.free = [sum(1 for t in registry.get("trucks", []) if not re.search(r"[A-Za-z]", t["slots"][i]))
                     for i in range(5)]

    def apply(self, args: dict) -> dict | None:
        appt = args.get("appointment") or ""
        if not appt:
            return None
        day, time = parse_day(appt, self.today), parse_time(appt)
        eff = {"kind": "booking", "requested": appt, "day": day, "time": fmt(time) if time is not None else None}
        if day not in (None, self.today):
            return {**eff, "ok": True, "note": "not today: no board data to check"}
        if time is None:
            return {**eff, "ok": False, "reason": "could not read the window"}
        if time not in self.WINDOWS:
            return {**eff, "ok": False, "reason": "not one of the 2-hour windows"}
        i = self.WINDOWS.index(time)
        if self.free[i] <= 0:
            return {**eff, "ok": False, "reason": "no truck free in that window"}
        self.free[i] -= 1
        return {**eff, "ok": True, "trucks_left": self.free[i]}


KINDS = {"calendar": Calendar, "inventory": Inventory, "truck_board": TruckBoard}


class ToolRuntime:
    """Executes the agent's tool calls for one simulated call and logs every event."""

    def __init__(self, spec):
        self.spec = spec
        kind = spec.resource.get("kind")
        self.resource = KINDS[kind](spec.registry, spec.resource) if kind else None
        self.events: list[dict] = []
        self.ended = False

    def execute(self, name: str, args: dict, turn: int) -> str:
        ev = {"turn": turn, "tool": name, "args": args}
        if name == "end_call":
            self.ended = True
            result = "Call ended."
        elif name == self.spec.save_tool:
            ev["effect"] = self.resource.apply(args) if self.resource else None
            result = LIVE_RESULT
        else:
            result = f"Error: no tool named {name}."
        ev["result"] = result
        self.events.append(ev)
        return result

    def saves(self) -> list[dict]:
        return [e for e in self.events if e["tool"] == self.spec.save_tool]
