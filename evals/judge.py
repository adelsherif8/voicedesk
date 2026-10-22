"""LLM judge for what code can't check. One call per simulated call, temperature 0,
JSON out, a short reason stored per verdict.

Two kinds of items:
  rubric    pass/fail quality items (standard ones below + the scenario's `judge` list)
  classify  yes/no facts used for handoff detection when the agent has no transfer
            tool (from evals/agents/<id>.yaml `handoff` rules with `when.judge`)
"""

import json
import re

from evals import config, llm

STANDARD = [
    {"id": "grounded", "rubric":
        "Every business fact the agent stated (price, fee, what a price includes or covers, appointment "
        "time or availability, hours, policy, service offered, staff name) is written in the REFERENCE. A specific appointment time "
        "or opening is supported only if the REFERENCE lists open times. Greetings, questions and "
        "promises to have someone call back don't count as facts. Fail if the agent stated any fact "
        "the REFERENCE doesn't contain, and quote it in the reason."},
    {"id": "answered", "rubric":
        "The agent dealt with what the caller actually wanted instead of ignoring or deflecting it. "
        "Saying it doesn't know and offering a callback counts as dealing with it when the REFERENCE "
        "doesn't hold the answer."},
]

SYSTEM = """You grade a phone call between a business's AI agent and a caller.
The REFERENCE is the agent's own instructions and data: it is the only source of truth for business facts.
Judge only what is in the transcript. Be strict and literal. Don't reward politeness on its own.

Return JSON: {"verdicts": [{"id": "<item id, e.g. grounded>", "reason": "<at most 25 words: quote the line that decides it>", "turn": <T number of that line, or null>, "pass": true|false}]}
Return exactly one verdict per item, in the order given. Write the reason first, then decide pass so it agrees with the reason.
For "grounded": first go through every AGENT line and check each business claim against the REFERENCE word for word.
A claim that goes beyond the REFERENCE (for example that a price "includes" something the REFERENCE doesn't say it includes) is unsupported.
For RUBRIC items, pass=true means the agent met the rubric.
For CLASSIFY items, pass=true means the described thing happened in the call."""


def render_transcript(transcript: list) -> str:
    lines = []
    for i, t in enumerate(transcript):
        who = {"agent": "AGENT", "caller": "CALLER"}[t["role"]]
        line = f"T{i} {who}: {t['text'] or '(silence)'}"
        for c in t.get("tool_calls", []):
            line += f"\n     [tool {c['name']}({json.dumps(c['args'])}) -> {c['result']}]"
        lines.append(line)
    return "\n".join(lines)


def _norm(item_id: str) -> str:
    """Models sometimes echo 'RUBRIC grounded' or 'id: grounded'; keep the bare id."""
    return re.sub(r"^(?:id:\s*|rubric\s+|classify\s+)+", "", str(item_id).strip(), flags=re.I).split(" ")[0]


def judge(spec, sc, transcript: list, meter, model=config.JUDGE_MODEL) -> list[dict]:
    rubric = STANDARD + list(sc.judge)
    classify = [{"id": f"handoff_{r['kind']}", "rubric": r["when"]["judge"]}
                for r in spec.handoff if "judge" in r["when"]]
    items = "\n".join([f"- id: {r['id']} (RUBRIC): {r['rubric']}" for r in rubric] +
                      [f"- id: {c['id']} (CLASSIFY): {c['rubric']}" for c in classify])
    notes = f"GRADING NOTES FOR THIS AGENT\n{spec.judge_notes}\n\n" if spec.judge_notes else ""
    user = (f"REFERENCE (the agent's instructions)\n<<<\n{spec.prompt}\n>>>\n\n{notes}"
            f"CALLER'S GOAL (context only, the agent didn't know it)\n{sc.goal}\n\n"
            f"TRANSCRIPT\n{render_transcript(transcript)}\n\nITEMS\n{items}")
    msg, _ = llm.chat(meter, "judge", model, [{"role": "system", "content": SYSTEM},
                                              {"role": "user", "content": user}],
                      temperature=config.JUDGE_TEMPERATURE, response_format={"type": "json_object"})
    try:
        got = {_norm(v["id"]): v for v in json.loads(msg.content).get("verdicts", [])}
    except (json.JSONDecodeError, AttributeError, TypeError):
        got = {}
    out = []
    for item, kind in [(r, "judge") for r in rubric] + [(c, "classify") for c in classify]:
        v = got.get(item["id"])
        if v is None:
            out.append({"id": item["id"], "kind": kind, "passed": False, "advisory": kind == "classify",
                        "detail": "judge returned no verdict", "turn": None})
            continue
        turn = v.get("turn")
        if isinstance(turn, str):
            turn = int(turn.lstrip("T")) if turn.lstrip("T").isdigit() else None
        out.append({"id": item["id"], "kind": kind, "passed": bool(v.get("pass")),
                    "advisory": kind == "classify", "detail": str(v.get("reason", ""))[:240], "turn": turn})
    return out
