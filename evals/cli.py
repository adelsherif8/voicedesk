"""python -m evals run --agent dental --k 3   (see --help)"""

import argparse
import sys

from evals import config, report, runner, scenario, spec


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
    a = ap.parse_args(argv)

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
    path = runner.save(result)
    report.print_summary(result)
    print(f"results: {path}")
    return 3 if result["aborted"] else 0
