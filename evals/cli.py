"""python -m evals run --agent dental --k 3   (see --help)

Exit codes: 0 ok, 1 regression against the baseline, 2 usage error, 3 cost cap hit.
"""

import argparse
import sys

import json

from evals import baseline, config, metrics, publish, report, runner, scenario, spec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals", description="VoiceDesk agent regression suite")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run scenarios against agents")
    who = run.add_mutually_exclusive_group(required=True)
    who.add_argument("--agent", action="append", help="agent id (repeatable)")
    who.add_argument("--all", action="store_true", help="every agent with a config in evals/agents/")
    run.add_argument("--scenario", help="run only this scenario id")
    run.add_argument("--tag", help="run only scenarios with this tag (e.g. smoke)")
    run.add_argument("--k", type=int, default=config.DEFAULT_K, help="attempts per scenario (pass^k)")
    run.add_argument("--model", default=config.AGENT_MODEL, help="agent-under-test model")
    run.add_argument("--prod-parity", action="store_true", help=f"test on the production model ({config.PROD_MODEL})")
    run.add_argument("--max-cost", type=float, default=config.MAX_COST_USD, help="hard USD cap for the run")
    run.add_argument("--backend", default="openai-text", choices=["openai-text", "retell", "vapi"])
    run.add_argument("--workers", type=int, default=config.WORKERS)
    run.add_argument("--baseline", choices=["compare", "save", "off"], default="compare",
                     help="compare with the saved baseline (default), save this run as the baseline, or skip")
    run.add_argument("--threshold", type=float, default=baseline.CONTAINMENT_DROP,
                     help="containment drop that counts as a regression (0.10 = 10 points)")
    run.add_argument("--strict", action="store_true", help="treat pass -> flaky as a regression")
    run.add_argument("--confirm", type=int, default=2,
                     help="re-run a scenario that went pass -> fail this many extra times before calling it a "
                          "regression (0 = off); missed handoffs are never retried")
    run.add_argument("--publish", nargs="?", const=publish.DEFAULT_URL, metavar="URL",
                     help=f"post the run to VoiceDesk (default {publish.DEFAULT_URL}) and update the committed snapshot")
    pub = sub.add_parser("publish", help="publish an existing results file to VoiceDesk")
    pub.add_argument("file", help="evals/results/run-....json")
    pub.add_argument("--url", default=publish.DEFAULT_URL)
    a = ap.parse_args(argv)

    if a.cmd == "publish":
        return _publish(json.loads(open(a.file).read()), a.url)

    model = config.PROD_MODEL if a.prod_parity else a.model
    agents = spec.available() if a.all else a.agent
    jobs = []
    for aid in agents:
        scs = scenario.load_all(aid, only=a.scenario, tag=a.tag)
        if scs:
            jobs.append((spec.load(aid), scs))
    n_calls = sum(len(scs) for _, scs in jobs) * a.k
    if not n_calls:
        print("no scenarios matched", file=sys.stderr)
        return 2

    est = runner.estimate(n_calls, model)
    print(f"{n_calls} calls ({len(jobs)} agent(s), k={a.k}) on {model}: estimated ${est:.2f}, cap ${a.max_cost:.2f}")
    if est > a.max_cost:
        print(f"estimate is over the cap; raise --max-cost or narrow the run", file=sys.stderr)
        return 2

    def progress(r):
        mark = "pass" if r["passed"] else "FAIL"
        print(f"  {mark}  {r['agent']}/{r['scenario']} #{r['attempt']}  {r['turns']} turns  "
              f"{r['end_reason']}  ${r['cost_usd']:.4f}", flush=True)

    result = runner.run_suite(jobs, a.k, model, a.max_cost, a.backend, a.workers, on_result=progress)
    # what the run covered: the page only trends runs that covered every scenario
    result["selection"] = {"agents": None if a.all else sorted(agents), "scenario": a.scenario, "tag": a.tag}
    report.print_summary(result)

    code = 3 if result["aborted"] else 0
    if a.baseline == "save":
        if result["aborted"] or result["patches"]:
            print("not saving a baseline from an aborted or patched run", file=sys.stderr)
            code = code or 2
        else:
            for p in baseline.save(result):
                print(f"baseline saved: {p}")
    elif a.baseline == "compare":
        result["comparison"] = {}
        if a.confirm and not result["aborted"]:
            _confirm_failures(result, jobs, model, a)
        for agent, summary in result["summary"].items():
            base = baseline.load(agent, model)
            if base is None:
                print(f"\n{agent}: no baseline for {model} (save one with --baseline save)")
                continue
            cmp = baseline.compare(base, summary, a.threshold, a.strict)
            result["comparison"][agent] = cmp
            report.print_comparison(agent, cmp)
            if cmp["regressions"]:
                code = 1
        if code == 1:
            print("\nREGRESSION: exit 1")
    print(f"results: {runner.save(result)}")
    if a.publish:
        if _publish(result, a.publish):
            code = code or 2
    return code


def _publish(run: dict, url: str) -> int:
    if run.get("patches"):
        print("refusing to publish a run of a deliberately patched agent", file=sys.stderr)
        return 2
    print(f"snapshot: {publish.update_snapshot(run)}")
    msg = publish.post(run, url)
    print(msg)
    return 0 if msg.startswith("published") else 1


def _confirm_failures(result: dict, jobs: list, model: str, a) -> None:
    """A single failed attempt of a scenario that passed every baseline attempt may be a flake.
    Re-run just those scenarios `a.confirm` more times and fold the attempts into the run,
    so the comparison sees e.g. 0/3 (regression) or 2/3 (newly flaky, a warning)."""
    retry = []
    for spec_, scs in jobs:
        base = baseline.load(spec_.id, model)
        if not base:
            continue
        broke = set(baseline.compare(base, result["summary"][spec_.id], a.threshold)["broke"])
        if broke:
            retry.append((spec_, [s for s in scs if s.id in broke]))
    if not retry:
        return
    names = ", ".join(f"{sp.id}/{s.id}" for sp, scs in retry for s in scs)
    print(f"\nconfirming {names} with {a.confirm} more attempt(s) each...")
    extra = runner.run_suite(retry, a.confirm, model, max(a.max_cost - result["cost_usd"], 0.01), a.backend, a.workers)
    for r in extra["results"]:
        r["attempt"] += result["k"]
        r["confirmation"] = True
    result["results"] = sorted(result["results"] + extra["results"], key=lambda r: (r["agent"], r["scenario"], r["attempt"]))
    result["cost_usd"] = round(result["cost_usd"] + extra["cost_usd"], 4)
    result["aborted"] = result["aborted"] or extra["aborted"]
    result["summary"] = metrics.summarize(result["results"])
    for sp, scs in retry:
        for s in scs:
            st = result["summary"][sp.id]["scenarios"][s.id]
            print(f"  {sp.id}/{s.id}: {st['passes']}/{st['runs']} -> {st['status']}")
