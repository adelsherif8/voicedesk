#!/usr/bin/env python3
"""Create every VoiceDesk agent on Retell from docs/RETELL-SETUP.md.

The markdown doc stays the single source of truth — edit a prompt there and
push the change with --update. The API key is read from ~/.retell_key only.

  python3 scripts/retell_provision.py --dry-run     # compare doc and live prompts; GETs only
  python3 scripts/retell_provision.py               # create everything
  python3 scripts/retell_provision.py --only recovery
  python3 scripts/retell_provision.py --update --only recovery   # replace that LLM's prompt, nothing else
"""
import argparse, json, os, re, sys, urllib.error, urllib.request

API = "https://api.retellai.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "RETELL-SETUP.md")
STATE = os.path.join(ROOT, "docs", "retell_created.json")
MODEL = "gpt-4.1"

# preferred voice by agent id -> substrings tried in order against /list-voices
VOICE_PREF = {
    "receptionist": ["cimo", "nova", "myra"],
    "recovery":     ["adrian", "onyx", "brian"],
    "dental":       ["myra", "shimmer", "cimo"],
    "realty":       ["jenny", "nova", "myra"],
    "restaurant":   ["cimo", "shimmer", "myra"],
    "support":      ["adrian", "echo", "brian"],
    "voicemail":    ["jenny", "nova", "myra"],
}


def key():
    p = os.path.expanduser("~/.retell_key")
    if os.path.exists(p):
        return open(p).read().strip()
    sys.exit("No API key. Put it in ~/.retell_key.")


def call(path, body=None, method="POST"):
    req = urllib.request.Request(
        f"{API}/{path}", method=method,
        headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        return json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        sys.exit(f"\nHTTP {e.code} on {method} /{path}\n{e.read().decode()[:900]}")


def parse_doc():
    """Pull the 7 agent blocks out of the markdown."""
    doc = open(DOC).read()
    agents = []
    for chunk in re.split(r"^═{20,}$", doc, flags=re.M):
        if "Agent Name:" not in chunk or "Parameters:" not in chunk:
            continue
        g = lambda p, s=re.S: (re.search(p, chunk, s).group(1).strip()
                               if re.search(p, chunk, s) else "")
        params_raw = re.search(r"Parameters:\n(\{.*?\n\})", chunk, re.S).group(1)
        url = re.search(r"URL:\s*(\S+)", chunk).group(1)
        agents.append({
            # the webhook path IS the agent id: .../retell/<id>
            "id":       url.rstrip("/").rsplit("/", 1)[1],
            "name":     g(r"Agent Name:\s*(.+)", 0),
            "begin":    g(r"BEGIN MESSAGE\n(.*?)\n\nSYSTEM PROMPT"),
            "prompt":   g(r"SYSTEM PROMPT\n(.*?)\n\nFUNCTION"),
            "fn_name":  g(r"^\s*Name:\s*(\S+)", re.M),
            "fn_desc":  " ".join(g(r"Description:\s*(.*?)\n\s*URL:").split()),
            "fn_url":   g(r"URL:\s*(\S+)"),
            "fn_params": json.loads(params_raw),
        })
    return agents


def pick_voice(aid, voices):
    for want in VOICE_PREF.get(aid, []):
        for v in voices:
            if want in (v.get("voice_name", "") + v.get("voice_id", "")).lower():
                return v["voice_id"], v.get("voice_name", v["voice_id"])
    v = voices[0]
    return v["voice_id"], v.get("voice_name", v["voice_id"])


def has_security(prompt):
    return bool(re.search(r"^SECURITY\b", prompt or "", re.M))


def live_llm(x, state):
    """The agent's live LLM, after checking that the saved ids still describe that agent."""
    prev = state.get(x["id"])
    if not prev:
        sys.exit(f"{x['id']}: no saved ids in {STATE}")
    engine = call(f"get-agent/{prev['agent_id']}", method="GET").get("response_engine") or {}
    if engine.get("type") != "retell-llm" or engine.get("llm_id") != prev["llm_id"]:
        sys.exit(f"{x['id']}: the live agent no longer uses the saved LLM. Nothing changed.")
    return call(f"get-retell-llm/{prev['llm_id']}", method="GET")


def yn(flag):
    return "yes" if flag else "no"


def dry_run(agents, state):
    print(f"{'agent':13} {'doc':>6} {'live':>6} {'diff':>6}  {'SEC doc':7} {'SEC live':8} {'same':4}  {'llm version'}")
    for x in agents:
        llm = live_llm(x, state)
        live = llm.get("general_prompt") or ""
        status = "published" if llm.get("is_published") else "draft"
        print(f"{x['id']:13} {len(x['prompt']):>6} {len(live):>6} {len(x['prompt']) - len(live):>+6}  "
              f"{yn(has_security(x['prompt'])):7} {yn(has_security(live)):8} {yn(x['prompt'] == live):4}  "
              f"v{llm.get('version')} {status}")
    print(f"\n{len(agents)} agent(s) compared. GET requests only; nothing was changed.")


def update_prompt(x, state):
    """Replace general_prompt only: omitted fields stay as they are on the live LLM."""
    llm = live_llm(x, state)
    if llm.get("is_published"):
        sys.exit(f"{x['id']}: the LLM's latest version is published, so it is read-only. Nothing changed. "
                 "Create a new draft in the Retell dashboard, then run this again.")
    llm_id = state[x["id"]]["llm_id"]
    call(f"update-retell-llm/{llm_id}", {"general_prompt": x["prompt"]}, method="PATCH")
    live = call(f"get-retell-llm/{llm_id}", method="GET").get("general_prompt")
    if live != x["prompt"]:
        sys.exit(f"{x['id']}: the update returned OK, but the live prompt differs from the doc.")
    print(f"  updated  {x['id']:13} {len(llm.get('general_prompt') or '')} -> {len(live)} chars, "
          f"SECURITY {yn(has_security(live))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compare doc and live prompts; changes nothing")
    ap.add_argument("--only", help="single agent id, e.g. recovery")
    ap.add_argument("--update", action="store_true", help="replace the prompt of the existing LLM; needs --only")
    a = ap.parse_args()
    if a.update and not a.only and not a.dry_run:
        ap.error("--update needs --only <id>")

    agents = parse_doc()
    if a.only:
        agents = [x for x in agents if x["id"] == a.only] or sys.exit(f"no agent '{a.only}'")

    state = json.load(open(STATE)) if os.path.exists(STATE) else {}

    if a.dry_run:
        dry_run(agents, state)
        return

    if a.update:
        for x in agents:
            update_prompt(x, state)
        return

    voices = call("list-voices", method="GET")
    print(f"{len(voices)} voices available\n")

    for x in agents:
        vid, vname = pick_voice(x["id"], voices)
        llm_body = {
            "model": MODEL,
            "general_prompt": x["prompt"],
            "begin_message": x["begin"],
            "start_speaker": "agent",
            "general_tools": [{
                "type": "custom",
                "name": x["fn_name"],
                "description": x["fn_desc"],
                "url": x["fn_url"],
                "method": "POST",
                "parameters": x["fn_params"],
                "speak_during_execution": True,
                "execution_message_description": "One moment while I save that.",
            }, {"type": "end_call", "name": "end_call",
                "description": "End the call once everything is saved and the caller has no further questions."}],
        }
        llm = call("create-retell-llm", llm_body)
        agent = call("create-agent", {
            "response_engine": {"type": "retell-llm", "llm_id": llm["llm_id"]},
            "voice_id": vid,
            "agent_name": x["name"],
            "language": "en-US",
            "interruption_sensitivity": 0.8,
            "responsiveness": 1,
            "enable_backchannel": True,
            "max_call_duration_ms": 600000,
        })
        state[x["id"]] = {"llm_id": llm["llm_id"], "agent_id": agent["agent_id"],
                          "name": x["name"], "voice": vname}
        print(f"  created  {x['id']:13} {x['name']:34} voice={vname}")

    json.dump(state, open(STATE, "w"), indent=2)
    print(f"\nSaved ids -> {STATE}")
    print("Open retellai.com -> Agents. Hit 'Test Audio' on any of them.")


if __name__ == "__main__":
    main()
