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
