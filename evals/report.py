"""Plain-text summary printed at the end of a run."""


def pct(x) -> str:
    return "  n/a" if x is None else f"{x * 100:4.0f}%"


def print_summary(run: dict) -> None:
    s = run["summary"]
    print()
    head = f"{'agent':14} {'calls':>5} {'pass^k':>6} {'contain':>7} {'transfer':>8} {'missed':>6} {'task':>5} {'halluc':>6} {'cost':>8}"
    print(head)
    print("-" * len(head))
    for agent, m in s.items():
        print(f"{agent:14} {m['calls']:>5} {pct(m['pass_k']):>6} {pct(m['containment_rate']):>7} "
              f"{pct(m['transfer_rate']):>8} {m['missed_handoffs']:>6} {pct(m['task_success_rate']):>5} "
              f"{pct(m['hallucination_rate']):>6} ${m['cost_usd']:>7.4f}")
    print()
    for agent, m in s.items():
        print(f"{agent}: scenarios")
        for sid, sc in sorted(m["scenarios"].items()):
            mark = {"pass": "PASS ", "flaky": "FLAKY", "fail": "FAIL "}[sc["status"]]
            print(f"  {mark} {sc['passes']}/{sc['runs']}  {sid}")
            fails = [r for r in run["results"] if r["agent"] == agent and r["scenario"] == sid and not r["passed"]]
            seen = set()
            for r in fails:
                for c in r["checks"]:
                    if not c["passed"] and not c["advisory"] and c["kind"] != "classify" and (c["id"], c["detail"]) not in seen:
                        seen.add((c["id"], c["detail"]))
                        print(f"          - [{c['id']}] {c['detail'][:110]}")
    advisory = sorted({(r["agent"], c["id"]) for r in run["results"] for c in r["checks"]
                       if c["advisory"] and c["kind"] != "classify" and not c["passed"]})
    if advisory:
        print("\nadvisory (reported, not failing): " + ", ".join(f"{a}/{c}" for a, c in advisory))
    print(f"\nrun {run['id']}  model {run['agent_model']}  k={run['k']}  "
          f"calls {len(run['results'])}/{run['planned_calls']}  spent ${run['cost_usd']:.4f} "
          f"({', '.join(f'{k} ${v:.4f}' for k, v in run['cost_by_role'].items())})")
    if run["patches"]:
        print("PATCHED AGENT (deliberate breakage): " + "; ".join(run["patches"]))
    if run["aborted"]:
        print(f"ABORTED: cost cap reached ({run['aborted']})")


def print_comparison(agent: str, cmp: dict) -> None:
    c_base, c_now = cmp["containment"]
    print(f"\n{agent}: vs baseline {cmp['baseline_run']} (k={cmp['baseline_k']}), {cmp['shared']} shared scenarios, "
          f"containment {pct(c_base).strip()} -> {pct(c_now).strip()}")
    for line in cmp["regressions"]:
        print(f"  REGRESSION  {line}")
    for line in cmp["warnings"]:
        print(f"  warning     {line}")
    for line in cmp["improvements"]:
        print(f"  improved    {line}")
    if cmp["new"]:
        print(f"  new (not in baseline): {', '.join(cmp['new'])}")
    if not (cmp["regressions"] or cmp["warnings"] or cmp["improvements"]):
        print("  no change")
