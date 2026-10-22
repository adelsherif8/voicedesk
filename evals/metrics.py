"""Metric definitions. Pure functions over call results, no I/O, so they're unit-tested.

Per call (score_call):
  goal_met        save/fields checks passed and the judge says the agent dealt with the request
  contained       goal_met AND no handoff expected AND none happened AND the call ended cleanly:
                  the agent closed it, or the caller said goodbye and hung up after the goal
                  was met. An abrupt hang-up or an abandoned call is never contained, whatever
                  was captured; a goodbye hang-up without the goal met is abandonment.
  transferred     a handoff happened (live transfer, or the agent's escalation outcome)
  missed_handoff  the scenario required a handoff and none happened (critical failure)
  unnecessary     a handoff happened where the scenario's acceptable outcome was no handoff
  (a scenario may accept several outcomes, e.g. [none, human] when a manager callback is
  as valid as answering; a handoff of the wrong kind fails the call but is neither)
  task_success    the saved payload matched every expected field (None if none expected)
  hallucinated    a dollar amount or booking not in the data, or the judge found an
                  ungrounded fact
  passed          every non-advisory check passed and the handoff was right

Per agent (summarize): rates are over all calls. Pass^k groups the k attempts of a
scenario: pass = all k passed, flaky = some, fail = none.
"""

GOAL_CHECKS = {"save_called", "fields", "answered"}
# How a call may end and still count as contained: the agent closed it, or the caller said
# their last line and hung up after the goal was met. An abrupt hang-up (caller_hangup),
# running out of turns, or an error is never contained.
CLEAN_ENDINGS = {"agent_end", "caller_goodbye"}
HALLUCINATION_CHECKS = {"prices_in_data", "grounded"}


def score_call(checks: list[dict], handoff: str, expected, end_reason: str, error: str | None = None) -> dict:
    """`expected` is the acceptable handoff outcome(s): "none", "emergency", "none|human" or a list."""
    ok_handoffs = set(expected.split("|") if isinstance(expected, str) else expected)
    by_id = {}
    for c in checks:
        by_id.setdefault(c["id"], []).append(c)
    failed = lambda cid: any(not c["passed"] for c in by_id.get(cid, []))
    blocking = [c for c in checks if not c["advisory"] and c["kind"] != "classify"]

    goal_met = not error and all(not failed(cid) for cid in GOAL_CHECKS)
    transferred = handoff != "none"
    handoff_ok = handoff in ok_handoffs
    missed = "none" not in ok_handoffs and not transferred
    unnecessary = transferred and not handoff_ok and "none" in ok_handoffs
    contained = goal_met and "none" in ok_handoffs and not transferred and end_reason in CLEAN_ENDINGS
    hallucinated = any(failed(cid) for cid in HALLUCINATION_CHECKS) or any(
        not c["passed"] and not c["advisory"] for c in by_id.get("booking_valid", []))
    return {
        "goal_met": goal_met,
        "contained": contained,
        "transferred": transferred,
        "handoff_ok": handoff_ok,
        "missed_handoff": missed,
        "unnecessary_handoff": unnecessary,
        "task_success": None if "fields" not in by_id else not failed("fields"),
        "hallucinated": hallucinated,
        "passed": not error and handoff_ok and all(c["passed"] for c in blocking),
    }


def _rate(n: int, d: int) -> float | None:
    return None if d == 0 else n / d


def scenario_status(passes: int, runs: int) -> str:
    return "pass" if passes == runs else "fail" if passes == 0 else "flaky"


def summarize(results: list[dict]) -> dict:
    """results: one dict per call with score_call's keys plus agent, scenario, cost."""
    out = {}
    for agent in sorted({r["agent"] for r in results}):
        rs = [r for r in results if r["agent"] == agent]
        n = len(rs)
        tasks = [r for r in rs if r["task_success"] is not None]
        scen = {}
        for r in rs:
            s = scen.setdefault(r["scenario"], {"runs": 0, "passes": 0, "contained": 0, "missed_handoffs": 0,
                                                "category": r.get("category")})
            s["runs"] += 1
            s["passes"] += bool(r["passed"])
            s["contained"] += bool(r["contained"])
            s["missed_handoffs"] += bool(r["missed_handoff"])
        for s in scen.values():
            s["status"] = scenario_status(s["passes"], s["runs"])
        transferred = sum(r["transferred"] for r in rs)
        out[agent] = {
            "calls": n,
            "containment_rate": _rate(sum(r["contained"] for r in rs), n),
            "transfer_rate": _rate(transferred, n),
            "correct_transfers": sum(r["transferred"] and r["handoff_ok"] for r in rs),
            "unnecessary_transfers": sum(r["unnecessary_handoff"] for r in rs),
            "missed_handoffs": sum(r["missed_handoff"] for r in rs),
            "missed_handoff_rate": _rate(sum(r["missed_handoff"] for r in rs), n),
            "task_success_rate": _rate(sum(bool(r["task_success"]) for r in tasks), len(tasks)),
            "hallucination_rate": _rate(sum(r["hallucinated"] for r in rs), n),
            "call_pass_rate": _rate(sum(r["passed"] for r in rs), n),
            "pass_k": _rate(sum(s["status"] == "pass" for s in scen.values()), len(scen)),
            "flaky": sorted(k for k, s in scen.items() if s["status"] == "flaky"),
            "failing": sorted(k for k, s in scen.items() if s["status"] == "fail"),
            "scenarios": scen,
            "cost_usd": round(sum(r.get("cost_usd", 0) for r in rs), 4),
        }
    return out
