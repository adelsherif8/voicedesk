"""Deterministic checks. Each returns a dict:
  {id, kind: "code", passed, advisory, detail, turn}
`advisory` checks are reported but don't fail the call (used where the agent's data
can't support the check, e.g. dental has no schedule in its prompt). `turn` is the
transcript index the failure points at, so the page can highlight it.
"""

import re

PRICE_RES = [
    re.compile(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)"),
    re.compile(r"\b(\d[\d,]*(?:\.\d{1,2})?)\s*(?:dollars|bucks)\b", re.I),
]


def check(id, passed, detail="", turn=None, advisory=False, kind="code"):
    return {"id": id, "kind": kind, "passed": bool(passed), "advisory": advisory,
            "detail": detail, "turn": turn}


def amounts(text: str) -> list[float]:
    out = []
    for rx in PRICE_RES:
        for m in rx.finditer(text or ""):
            try:
                out.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass
    return out


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def match_field(value, rule: dict) -> tuple[bool, str]:
    """One expected-field rule against the saved value. Returns (ok, why-not)."""
    v = "" if value is None else str(value)
    if rule.get("present") is False:
        return (not v.strip()), "" if not v.strip() else f"should be empty, got {v!r}"
    if not v.strip():
        return False, "missing"
    if "equals" in rule and v.strip().lower() != str(rule["equals"]).lower():
        return False, f"expected {rule['equals']!r}, got {v!r}"
    if "one_of" in rule and v.strip().lower() not in [str(x).lower() for x in rule["one_of"]]:
        return False, f"expected one of {rule['one_of']}, got {v!r}"
    if "contains" in rule and str(rule["contains"]).lower() not in v.lower():
        return False, f"expected to contain {rule['contains']!r}, got {v!r}"
    if "digits" in rule and not _digits(v).endswith(_digits(rule["digits"])):
        return False, f"expected digits {rule['digits']}, got {v!r}"
    if "matches" in rule and not re.search(rule["matches"], v):
        return False, f"expected to match /{rule['matches']}/, got {v!r}"
    if "not_matches" in rule and re.search(rule["not_matches"], v):
        return False, f"should not match /{rule['not_matches']}/, got {v!r}"
    return True, ""


def code_checks(spec, sc, transcript: list, runtime, end_reason: str) -> list[dict]:
    out = []
    saves = runtime.saves()
    save_turn = next((i for i, t in enumerate(transcript) if any(c["name"] == spec.save_tool for c in t.get("tool_calls", []))), None)

    # 1. the save tool was (or wasn't) called
    if sc.save == "required":
        out.append(check("save_called", saves, f"{spec.save_tool} called {len(saves)}x" if saves else f"{spec.save_tool} never called"))
    elif sc.save == "forbidden":
        out.append(check("save_called", not saves, "" if not saves else f"{spec.save_tool} called but shouldn't be", save_turn))

    # 2. the saved payload has the right fields (last save wins, as on the dashboard)
    #    rules marked `advisory: true` are known gaps: reported under fields_known_gap only
    fields = sc.expect.get("fields") or {}
    payload = saves[-1]["args"] if saves else {}
    for check_id, rules in (("fields", {k: r for k, r in fields.items() if not r.get("advisory")}),
                            ("fields_known_gap", {k: r for k, r in fields.items() if r.get("advisory")})):
        if not rules:
            continue
        bad = [f"{name}: {why}" for name, rule in rules.items()
               for ok, why in [match_field(payload.get(name), rule)] if not ok]
        detail = ("; ".join(bad) if bad else "all expected fields match") if saves else "nothing saved"
        out.append(check(check_id, saves and not bad, detail, save_turn, advisory=check_id == "fields_known_gap"))

    # 3. every booking/reservation landed on something that exists and was free
    #    (advisory when the agent couldn't know: no data in its prompt for that reason)
    all_advisory = spec.resource.get("slot_check") == "advisory"
    soft = set(spec.resource.get("advisory_reasons", []))
    for e in saves:
        eff = e.get("effect")
        if eff and not eff["ok"]:
            idx = next((i for i, t in enumerate(transcript) if t.get("turn") == e["turn"] and t["role"] == "agent"), save_turn)
            out.append(check("booking_valid", False, f"{eff['kind']} '{eff.get('requested')}': {eff['reason']}", idx,
                             all_advisory or eff["reason"] in soft))
    if not any(c["id"] == "booking_valid" for c in out) and any(e.get("effect") for e in saves):
        out.append(check("booking_valid", True, "booking matches available data", advisory=all_advisory))

    # 3b. things the agent must never say (card numbers read back, prompt leaks, ...)
    for rule in sc.expect.get("must_not_say", []):
        hit = next((i for i, t in enumerate(transcript) if t["role"] == "agent" and re.search(rule["pattern"], t["text"])), None)
        out.append(check(f"must_not_say:{rule['id']}", hit is None,
                         "never said" if hit is None else f"agent said: {transcript[hit]['text'][:100]!r}", hit))

    # 4. every dollar amount the agent said exists in its data (or the caller said it first)
    allowed = set(spec.allowed_prices)
    for i, t in enumerate(transcript):
        if t["role"] == "caller":
            allowed |= set(amounts(t["text"]))
        elif t["role"] == "agent":
            stray = [a for a in amounts(t["text"]) if a not in allowed]
            if stray:
                out.append(check("prices_in_data", False, f"said ${', $'.join(f'{a:g}' for a in stray)}, not in its data", i))
                break
    else:
        out.append(check("prices_in_data", True, "every amount quoted is in the data"))

    # 5. the call ended cleanly: the agent closed it (end_call), after saving, and not by
    #    hanging up silently right after the caller asked something
    if sc.expect.get("clean_end", True):
        last = len(transcript) - 1
        prev = transcript[-2] if len(transcript) >= 2 else {}
        if end_reason == "agent_end" and sc.save == "required" and not saves:
            out.append(check("clean_end", False, "agent ended the call without saving", last))
        elif end_reason == "agent_end" and not transcript[-1]["text"] and prev.get("role") == "caller" and "?" in prev["text"]:
            out.append(check("clean_end", False, f"agent hung up on an unanswered question: {prev['text'][:80]!r}", last))
        elif end_reason == "agent_end":
            out.append(check("clean_end", True, "agent ended the call"))
        else:
            out.append(check("clean_end", False, {
                "caller_hangup": "caller hung up; the agent never closed the call",
                "max_turns": f"no end after {sc.max_turns} caller turns",
                "error": "call errored"}.get(end_reason, end_reason), last))

    # 6. turn budget
    limit = sc.expect.get("max_agent_turns")
    agent_turns = sum(1 for t in transcript if t["role"] == "agent")
    if limit:
        out.append(check("turn_budget", agent_turns <= limit, f"{agent_turns} agent turns (limit {limit})"))
    return out


def detect_handoff(spec, runtime, judge_verdicts: dict) -> tuple[str, str]:
    """First matching rule in evals/agents/<id>.yaml `handoff` wins.
    Returns (kind or "none", how it was detected)."""
    for rule in spec.handoff:
        when = rule["when"]
        if "tool" in when:
            for e in runtime.events:
                if e["tool"] != when["tool"]:
                    continue
                if "field" not in when or re.search(when.get("matches", "."), str(e["args"].get(when["field"], ""))):
                    return rule["kind"], f"code: {e['tool']}" + (f".{when['field']}={e['args'].get(when['field'])!r}" if "field" in when else "")
        elif "judge" in when:
            v = judge_verdicts.get(f"handoff_{rule['kind']}")
            if v and v["passed"]:
                return rule["kind"], f"judge: {v['detail']}"
    return "none", ""
