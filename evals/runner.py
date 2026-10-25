"""Runs simulated calls: one scenario attempt = one call between the agent under test and
a simulated caller, then checks, judge and per-call metrics."""

import json
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from evals import checks, config, fixtures, llm, metrics, pii
from evals.backends import BACKENDS
from evals.caller import SimulatedCaller
from evals.judge import judge
from evals.stubs import ToolRuntime

SILENCE_TO_AGENT = "..."   # what the agent receives when the caller says nothing


def _agent_entry(turn, i):
    return {"turn": i, "role": "agent", "text": turn.text,
            "tool_calls": [{"name": c.name, "args": c.args, "result": c.result} for c in turn.tool_calls]}


def run_call(spec, sc, attempt: int, backend, model: str, run_meter: llm.Meter) -> dict:
    meter = run_meter.child()
    # security track: a per-call canary in the system prompt, fixture "other customers" the
    # agent must never disclose, and the scenario's tool-result overrides (indirect injection)
    canary = checks.make_canary()
    others = fixtures.others(spec.id)
    runtime = ToolRuntime(spec, fixtures.render_tool_results(sc.tool_results, spec.id))
    session = backend.start(replace(spec, prompt=spec.prompt + checks.canary_line(canary)), runtime, meter, model)
    caller = SimulatedCaller(sc, meter)
    transcript, end_reason, error = [], "max_turns", None
    started = time.time()
    try:
        opening = session.opening()
        if opening:
            transcript.append(_agent_entry(opening, 0))
            caller.hear(opening.text)
        for i in range(1, sc.max_turns + 1):
            text, hung_up = caller.speak()
            transcript.append({"turn": i, "role": "caller", "text": text})
            abrupt = hung_up and (not text or (sc.hangup_after_turns and i >= sc.hangup_after_turns))
            if abrupt:
                end_reason = "caller_hangup"
                break
            reply = session.respond(text or SILENCE_TO_AGENT)
            transcript.append(_agent_entry(reply, i))
            if reply.ended:
                end_reason = "agent_end"
                break
            if hung_up:
                # the caller said their last line and hung up; the agent replied but never closed.
                # Contained only if the goal was met (see metrics.py); otherwise it's abandonment.
                end_reason = "caller_goodbye"
                break
            caller.hear(reply.text)
    except llm.BudgetExceeded:
        raise
    except Exception as e:  # a crashed call is a failed call, not a crashed run
        end_reason, error = "error", f"{type(e).__name__}: {e}"

    found = checks.code_checks(spec, sc, transcript, runtime, end_reason)
    found += checks.security_checks(spec, sc, transcript, runtime, canary, others)
    # PII is redacted before anything leaves this function: the judge sees placeholders,
    # and so do the results file and the /evals console
    redactor = pii.Redactor(names=pii.names_for(sc, others), allow=pii.allow_for(spec))
    transcript = redactor.redact_transcript(transcript)
    verdicts = [] if error else judge(spec, sc, transcript, meter)
    by_id = {v["id"]: v for v in verdicts}
    handoff, how = checks.detect_handoff(spec, runtime, by_id)
    found.append(checks.check(
        "handoff", handoff in sc.handoffs,
        f"expected {sc.handoff}, got {handoff}" + (f" ({how})" if how else ""),
        kind="judge" if how.startswith("judge") else "code"))
    all_checks = found + verdicts
    # in a security scenario these checks decide "did the agent resist": the code checks,
    # the must_not_say rules and the scenario's own judge items
    sec_ids = (metrics.SECURITY_CHECKS | {f"must_not_say:{r['id']}" for r in sc.expect.get("must_not_say", [])}
               | {j["id"] for j in sc.judge})
    for c in all_checks:   # checks a scenario opts out of are still shown, but can't fail it
        if sc.category == "security" and c["id"] in sec_ids:
            c["security"] = True
        if c["id"] in sc.expect.get("skip", []):
            c["advisory"] = True
            c["detail"] = "skipped by scenario: " + c["detail"]
    scored = metrics.score_call(all_checks, handoff, sc.handoff, end_reason, error)
    return {
        "agent": spec.id, "scenario": sc.id, "title": sc.title, "category": sc.category,
        "attempt": attempt, "handoff": handoff, "handoff_expected": sc.handoff,
        "end_reason": end_reason, "error": error,
        "turns": sum(1 for t in transcript if t["role"] == "caller"),
        "checks": redactor.redact_obj(all_checks), "transcript": transcript, "events": redactor.redact_obj(runtime.events),
        "scenario_def": redactor.redact_obj({"goal": sc.goal, "persona": sc.persona, "friction": sc.friction,
                                             "hidden_facts": sc.hidden_facts, "expect": sc.expect, "max_turns": sc.max_turns,
                                             "owasp": sc.owasp, "tool_results": sc.tool_results}),
        "redaction": redactor.engine_name,
        "cost_usd": round(meter.spent, 5), "seconds": round(time.time() - started, 1),
        **scored,
    }


def estimate(n_calls: int, agent_model: str) -> float:
    def cost(model, tokens):
        p_in, _, p_out = config.PRICES.get(model, config.PRICES["gpt-4.1"])
        return (tokens[0] * p_in + tokens[1] * p_out) / 1e6
    t = config.EST_TOKENS_PER_CALL
    per_call = cost(agent_model, t["agent"]) + cost(config.CALLER_MODEL, t["caller"]) + cost(config.JUDGE_MODEL, t["judge"])
    return n_calls * per_call


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT, text=True).strip()
    except Exception:
        return ""


def run_suite(jobs: list, k: int, model: str, cap: float, backend_name: str = "openai-text",
              workers: int = config.WORKERS, on_result=None) -> dict:
    """jobs: [(spec, [scenarios])]. Returns the run dict (results + summary)."""
    backend = BACKENDS[backend_name]()
    meter = llm.Meter(cap=cap)
    tasks = [(spec, sc, a) for spec, scs in jobs for sc in scs for a in range(1, k + 1)]
    results, aborted = [], None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(run_call, spec, sc, a, backend, spec.model or model, meter) for spec, sc, a in tasks]
        for f in as_completed(futs):
            try:
                r = f.result()
            except llm.BudgetExceeded as e:
                aborted = str(e)
                for other in futs:
                    other.cancel()
                continue
            results.append(r)
            if on_result:
                on_result(r)
    results.sort(key=lambda r: (r["agent"], r["scenario"], r["attempt"]))
    return {
        "id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4],
        "created": time.time(), "git_sha": _git_sha(), "backend": backend_name,
        "agent_model": model, "k": k, "cost_usd": round(meter.spent, 4),
        "cost_by_role": {r: round(c, 4) for r, c in meter.by_role.items()},
        "aborted": aborted, "planned_calls": len(tasks),
        "patches": sorted({p for spec, _ in jobs for p in spec.patches}),
        "redaction": results[0]["redaction"] if results else None,
        "summary": metrics.summarize(results), "results": results,
    }


def save(run: dict) -> str:
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RESULTS_DIR / f"run-{run['id']}.json"
    path.write_text(json.dumps(run, indent=1))
    return str(path.relative_to(config.ROOT))
