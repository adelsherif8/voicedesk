"""VoiceDesk — shared dashboard/CRM for AI voice-agent demos.

Any voice agent (Vapi, Retell, or a manual/n8n flow) posts captured data here; the
dashboard shows every lead, call, and booking live, filterable by agent.
"""

import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.agents import AGENTS, AGENTS_BY_ID, agent_name

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))
templates.env.globals["pct"] = lambda x: "n/a" if x is None else f"{x * 100:.0f}%"
templates.env.tests["search"] = lambda value, needle: needle in str(value)

db.init()
app = FastAPI(title="VoiceDesk")


def _valid_agent(aid: str) -> str:
    return aid if aid in AGENTS_BY_ID else "receptionist"


_STD = {"name", "customer_name", "phone", "phone_number", "email", "intent", "reason",
        "outcome", "appointment", "time", "slot", "summary", "notes", "transcript", "agent"}


def _store(agent: str, args: dict) -> int:
    meta = {k: v for k, v in args.items() if k not in _STD and v not in (None, "")}
    return db.add({
        "agent": agent,
        "name": args.get("name") or args.get("customer_name") or "",
        "phone": args.get("phone") or args.get("phone_number") or "",
        "email": args.get("email") or "",
        "intent": args.get("intent") or args.get("reason") or "",
        "outcome": args.get("outcome") or "captured",
        "appointment": args.get("appointment") or args.get("time") or args.get("slot") or "",
        "summary": args.get("summary") or args.get("notes") or "",
        "transcript": args.get("transcript") or "",
        "meta": meta,
        "created": time.time(),
    })


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "agents": AGENTS, "stats": db.stats(),
    })


@app.get("/records")
def records(agent: str = "all"):
    stats = db.stats(agent) if agent != "all" else db.stats()
    return {"agents": AGENTS, "stats": stats,
            "records": [{**r, "agent_name": agent_name(r["agent"])}
                        for r in db.list_records(agent)]}


@app.get("/api/insights/{agent}")
def api_insights(agent: str):
    """Operator brief for one agent's recent calls, generated on Amazon Bedrock (AWS deployment only)."""
    from app import bedrock
    if agent not in AGENTS_BY_ID:
        return JSONResponse({"error": f"unknown agent {agent}"}, status_code=404)
    out = bedrock.insights(agent_name(agent), db.list_records(agent, limit=20))
    return JSONResponse(out, status_code=200 if "error" not in out else 503)


@app.get("/agent/{aid}", response_class=HTMLResponse)
def agent_view(aid: str, request: Request):
    if aid not in AGENTS_BY_ID:
        return RedirectResponse("/")
    tpl = AGENTS_BY_ID[aid].get("template", "agent.html")
    return templates.TemplateResponse(request, tpl, {
        "agent": AGENTS_BY_ID[aid], "stats": db.stats(aid),
        "records": db.list_records(aid),
    })


@app.post("/vapi/{agent}")
async def vapi_webhook(agent: str, request: Request):
    """Handles Vapi tool-calls and end-of-call reports."""
    agent = _valid_agent(agent)
    body = await request.json()
    msg = body.get("message", body)

    tool_calls = msg.get("toolCalls") or msg.get("tool_calls") or []
    if tool_calls:
        results = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            _store(agent, args)
            results.append({"toolCallId": tc.get("id"),
                            "result": "Saved. The details are recorded in the system."})
        return {"results": results}

    if msg.get("type") == "end-of-call-report" or msg.get("analysis") or msg.get("summary"):
        analysis = msg.get("analysis", {})
        _store(agent, {
            "summary": analysis.get("summary") or msg.get("summary") or "Call completed.",
            "outcome": "call logged",
            "transcript": (msg.get("artifact", {}) or {}).get("transcript", ""),
        })
    return {"ok": True}


@app.post("/retell/{agent}")
async def retell_webhook(agent: str, request: Request):
    """Retell AI custom functions + call-analysis webhooks.

    Custom function -> {"call": {...}, "name": "save_lead", "args": {...}}
    Call analysed   -> {"event": "call_analyzed", "call": {"call_analysis": {...}}}
    Whatever we return is handed back to the agent's LLM as the tool result,
    so it must be a short sentence the agent can say out loud.
    """
    agent = _valid_agent(agent)
    body = await request.json()

    # --- custom function call ---
    if "name" in body and "args" in body:
        args = body.get("args") or {}
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        call = body.get("call") or {}
        args.setdefault("phone", call.get("from_number", ""))
        _store(agent, args)
        return {"result": "Saved. The details are recorded in the system."}

    # --- post-call analysis ---
    call = body.get("call") or {}
    analysis = call.get("call_analysis") or {}
    if body.get("event") in ("call_analyzed", "call_ended") or analysis:
        _store(agent, {
            "summary": analysis.get("call_summary") or "Call completed.",
            "outcome": "call logged",
            "phone": call.get("from_number", ""),
            "transcript": call.get("transcript", ""),
        })
    return {"ok": True}


@app.post("/ingest/{agent}")
async def ingest(agent: str, request: Request):
    """Generic ingest for Retell / n8n / manual — accepts a flat JSON record."""
    agent = _valid_agent(agent)
    args = await request.json()
    rid = _store(agent, args)
    return {"ok": True, "id": rid}


@app.post("/simulate/{agent}")
async def simulate(agent: str, request: Request):
    """Drop a sample record (to demo the live dashboard without a real call)."""
    agent = _valid_agent(agent)
    body = await request.json() if await request.body() else {}
    rid = _store(agent, body or {
        "name": "Live Caller", "phone": "+1 555 000 1234",
        "intent": "demo call", "outcome": "booked",
        "appointment": "Tomorrow, 3:00 PM", "summary": "Simulated call captured live."})
    return {"ok": True, "id": rid}


@app.post("/reset")
def reset():
    db.reset()
    return {"ok": True, "records": db.count()}


@app.get("/health")
def health():
    return {"ok": True, "agents": len(AGENTS), "records": db.count()}


# ---- Agent QA console: regression + simulation results from `python -m evals` ----
import hmac
import json as _json

from evals import pii as _pii
from evals.metrics import CRITICAL_CHECKS, DEFINITIONS as EVAL_DEFINITIONS

_SNAPSHOT = os.path.join(_HERE, "evals", "results", "published.json")
_LOCAL = {"127.0.0.1", "::1", "localhost", "testclient"}


def _load_eval_snapshot():
    """Render's free disk is wiped on deploy; reload the committed snapshot when empty."""
    db.init_evals()
    if db.eval_run_count() or not os.path.exists(_SNAPSHOT):
        return
    snap = _json.load(open(_SNAPSHOT))
    for run in snap.get("history", []):
        db.save_eval_run({k: v for k, v in run.items() if k != "results"})
    for run in snap.get("latest", {}).values():
        db.save_eval_run(run)


_load_eval_snapshot()


@app.post("/evals/ingest")
async def evals_ingest(request: Request):
    """The eval runner posts a full run here. Needs `Authorization: Bearer $EVALS_INGEST_TOKEN`
    when that env var is set; without it, only requests from this machine are accepted."""
    token = os.getenv("EVALS_INGEST_TOKEN")
    if token:
        sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(sent, token):
            return JSONResponse({"ok": False, "error": "bad token"}, status_code=401)
    elif (request.client.host if request.client else "") not in _LOCAL:
        return JSONResponse({"ok": False, "error": "set EVALS_INGEST_TOKEN to publish remotely"}, status_code=403)
    run = await request.json()
    if not isinstance(run, dict) or not run.get("id") or "summary" not in run:
        return JSONResponse({"ok": False, "error": "not an eval run"}, status_code=400)
    # publish guard, server side: nothing with detectable personal data is stored or shown.
    # (The CLI already redacts and scans with the name dictionary; this is the pattern-only floor.)
    found = _pii.scan_run(run)
    if found:
        return JSONResponse({"ok": False, "error": "run contains unredacted PII",
                             "findings": [{"type": f["type"], "path": f["path"]} for f in found[:10]]}, status_code=400)
    n = db.save_eval_run(run)
    return {"ok": True, "run": run["id"], "results": n}


def _full_run(r: dict) -> bool:
    sel = r.get("selection") or {}
    return not sel.get("scenario") and not sel.get("tag")


_STATUS_ORDER = {"fail": 0, "flaky": 1, "pass": 2}


def _first_failure(checks: list) -> dict | None:
    """The check a reader should look at first: a missed handoff, then any other blocking failure."""
    blocking = [c for c in checks or [] if not c["passed"] and not c["advisory"] and c["kind"] != "classify"]
    blocking.sort(key=lambda c: (c["id"] not in CRITICAL_CHECKS, c["id"] != "handoff", c["kind"] != "code"))
    return blocking[0] if blocking else None


def _security_view(m: dict) -> dict:
    """The Security section's row for one agent; older runs predate these fields."""
    return {"available": "security_calls" in m, "calls": m.get("security_calls", 0),
            "resistance": m.get("injection_resistance_rate"), "prompt_leaks": m.get("prompt_leaks", 0),
            "pii_leaks": m.get("pii_leaks", 0), "unauthorized": m.get("unauthorized_tool_calls", 0),
            "criticals": m.get("criticals", 0)}


def _evals_view(model: str | None, run_id: str | None) -> dict:
    runs = db.eval_runs(200)
    published = [r for r in runs if r["has_results"]]
    models = sorted({r["agent_model"] for r in published})
    run = db.eval_run(run_id) if run_id else None
    if run is None and published:
        model = model if model in models else published[0]["agent_model"]
        run = next(r for r in published if r["agent_model"] == model)
    if run is None:
        return {"run": None, "models": models, "runs": [], "definitions": EVAL_DEFINITIONS}
    results = db.eval_results(run["id"])
    agents = []
    for aid, m in (run["summary"] or {}).items():
        reg = AGENTS_BY_ID.get(aid, {})
        trend = [{"id": r["id"], "created": r["created"], "containment": r["summary"][aid]["containment_rate"],
                  "pass_k": r["summary"][aid]["pass_k"], "calls": r["summary"][aid]["calls"]}
                 for r in reversed(runs)
                 if r["agent_model"] == run["agent_model"] and _full_run(r) and aid in (r["summary"] or {})
                 and r["created"] <= run["created"]][-12:]
        rows = []
        for sid, st in m["scenarios"].items():
            attempts = [r for r in results if r["agent"] == aid and r["scenario"] == sid]
            # a missed handoff is the headline whenever one happened, then the first failing attempt's reason
            missed = next((c for r in attempts if r["missed_handoff"] for c in r["checks"] if c["id"] == "handoff"), None)
            fail = missed or next((f for f in (_first_failure(r["checks"]) for r in attempts if not r["passed"]) if f), None)
            rows.append({"id": sid, "title": attempts[0]["title"] if attempts else sid,
                         "category": (st.get("category") or "").replace("_", " "), "status": st["status"],
                         "passes": st["passes"], "runs": st["runs"], "missed": st.get("missed_handoffs", 0),
                         "fail": fail,
                         "attempts": [{"id": r["id"], "n": r["attempt"], "passed": bool(r["passed"]),
                                       "end": r["end_reason"], "handoff": r["handoff"],
                                       "why": (_first_failure(r["checks"]) or {}).get("detail", "")}
                                      for r in attempts]})
        for row in rows:
            row["critical"] = sum(1 for r in results if r["agent"] == aid and r["scenario"] == row["id"]
                                  and any(c["id"] in CRITICAL_CHECKS and not c["passed"] for c in r["checks"]))
        rows.sort(key=lambda x: (_STATUS_ORDER[x["status"]], -x["critical"], -x["missed"], x["id"]))
        agents.append({"id": aid, "name": reg.get("name", aid), "business": reg.get("business", ""),
                       "icon": reg.get("icon", "fa-headset"), "color": reg.get("color", "#4f46e5"),
                       "m": m, "trend": trend, "rows": rows, "security": _security_view(m),
                       "comparison": (run.get("comparison") or {}).get(aid)})
    return {"run": run, "models": models, "definitions": EVAL_DEFINITIONS, "agents": agents,
            "runs": [r for r in published if r["agent_model"] == run["agent_model"]][:15]}


@app.get("/evals", response_class=HTMLResponse)
def evals_page(request: Request, model: str | None = None, run: str | None = None):
    return templates.TemplateResponse(request, "evals.html", _evals_view(model, run))


@app.get("/evals/result/{rid}", response_class=HTMLResponse)
def evals_result_page(rid: int, request: Request, check: str | None = None):
    res = db.eval_result(rid)
    if not res:
        return RedirectResponse("/evals")
    run = db.eval_run(res["run_id"])
    siblings = [r for r in db.eval_results(res["run_id"]) if r["agent"] == res["agent"] and r["scenario"] == res["scenario"]]
    focus = next((c for c in res["checks"] if c["id"] == check), None) or _first_failure(res["checks"])
    marks = {}
    for c in res["checks"]:
        if not c["passed"] and c["kind"] != "classify" and c.get("turn") is not None:
            marks.setdefault(c["turn"], []).append(c)
    reg = AGENTS_BY_ID.get(res["agent"], {})
    return templates.TemplateResponse(request, "evals_result.html", {
        "r": res, "run": run, "siblings": siblings, "focus": focus, "marks": marks,
        "agent": {"name": reg.get("name", res["agent"]), "icon": reg.get("icon", "fa-headset"),
                  "color": reg.get("color", "#4f46e5")}})


@app.get("/evals/data")
def evals_data(model: str | None = None, run: str | None = None):
    """The console's data as JSON (also the table view behind the charts)."""
    v = _evals_view(model, run)
    return {"run": v["run"], "agents": v.get("agents", []), "definitions": v["definitions"]}

# ---- IP desk-phone XML services (Cisco IP Phone Services format) ----
from fastapi.responses import Response

def _xml_esc(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

@app.get("/xml/voicemail/{agent}")
def xml_voicemail_menu(agent: str, request: Request):
    """CiscoIPPhoneMenu: list of AI-summarized voicemails for the phone screen."""
    agent = _valid_agent(agent)
    base = str(request.base_url).rstrip("/")
    items = ""
    for r in db.list_records(agent)[:8]:
        m = r.get("meta") or {}
        tag = {"urgent": "!! ", "high": "! ", "medium": "", "low": ""}.get(m.get("priority", ""), "")
        items += f"<MenuItem><Name>{_xml_esc(tag + r['name'] + ' — ' + r['intent'])}</Name><URL>{base}/xml/voicemail/{agent}/{r['id']}</URL></MenuItem>"
    body = (f"<CiscoIPPhoneMenu><Title>AI Voicemail ({db.count(agent)})</Title><Prompt>Select a message</Prompt>{items}"
            f"<SoftKeyItem><Name>Select</Name><URL>SoftKey:Select</URL><Position>1</Position></SoftKeyItem>"
            f"<SoftKeyItem><Name>Exit</Name><URL>SoftKey:Exit</URL><Position>3</Position></SoftKeyItem></CiscoIPPhoneMenu>")
    return Response(content=body, media_type="text/xml")

@app.get("/xml/voicemail/{agent}/{rid}")
def xml_voicemail_item(agent: str, rid: int, request: Request):
    """CiscoIPPhoneText: AI summary + callback softkey for one message."""
    agent = _valid_agent(agent)
    rec = next((r for r in db.list_records(agent) if r["id"] == rid), None)
    if not rec:
        return Response(content="<CiscoIPPhoneText><Title>Not found</Title></CiscoIPPhoneText>", media_type="text/xml")
    m = rec.get("meta") or {}
    text = f"{m.get('priority','').upper()} - {rec['intent']}\n{rec['summary']}\nMatter: {m.get('matter','')}\nCallback: {rec.get('appointment') or 'when possible'}"
    body = (f"<CiscoIPPhoneText><Title>{_xml_esc(rec['name'])}</Title><Prompt>{_xml_esc(rec['phone'])}</Prompt><Text>{_xml_esc(text)}</Text>"
            f"<SoftKeyItem><Name>Call back</Name><URL>Dial:{''.join(ch for ch in rec['phone'] if ch.isdigit())}</URL><Position>1</Position></SoftKeyItem>"
            f"<SoftKeyItem><Name>Text</Name><URL>{str(request.base_url).rstrip('/')}/xml/voicemail/{agent}</URL><Position>2</Position></SoftKeyItem>"
            f"<SoftKeyItem><Name>Back</Name><URL>SoftKey:Exit</URL><Position>3</Position></SoftKeyItem></CiscoIPPhoneText>")
    return Response(content=body, media_type="text/xml")
