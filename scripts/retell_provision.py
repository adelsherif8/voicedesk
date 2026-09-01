#!/usr/bin/env python3
"""Create every VoiceDesk agent on Retell from docs/RETELL-SETUP.md.

The markdown doc stays the single source of truth — edit a prompt there and
re-run with --update to push the change.

  export RETELL_API_KEY=...        (or put the key in ~/.retell_key)
  python3 scripts/retell_provision.py --dry-run     # parse + show, no API calls
  python3 scripts/retell_provision.py               # create everything
  python3 scripts/retell_provision.py --only recovery
  python3 scripts/retell_provision.py --update      # push prompt edits to existing
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
    k = os.environ.get("RETELL_API_KEY")
    if k:
        return k.strip()
    p = os.path.expanduser("~/.retell_key")
    if os.path.exists(p):
        return open(p).read().strip()
    sys.exit("No API key. Put it in ~/.retell_key or export RETELL_API_KEY.")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="single agent id, e.g. recovery")
    ap.add_argument("--update", action="store_true", help="update instead of create")
    a = ap.parse_args()

    agents = parse_doc()
    if a.only:
        agents = [x for x in agents if x["id"] == a.only] or sys.exit(f"no agent '{a.only}'")

    if a.dry_run:
        for x in agents:
            print(f"\n{'='*66}\n{x['id']:14} {x['name']}")
            print(f"  begin   : {x['begin'][:78]}...")
            print(f"  prompt  : {len(x['prompt'])} chars")
            print(f"  function: {x['fn_name']} -> {x['fn_url']}")
            print(f"  required: {x['fn_params'].get('required')}")
            print(f"  props   : {len(x['fn_params'].get('properties', {}))}")
        print(f"\n{len(agents)} agent(s) parsed cleanly. No API calls made.")
        return

    voices = call("list-voices", method="GET")
    print(f"{len(voices)} voices available\n")
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}

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
        prev = state.get(x["id"])
        if a.update and prev:
            call(f"update-retell-llm/{prev['llm_id']}", llm_body, method="PATCH")
            print(f"  updated  {x['id']:13} {x['name']}")
            continue

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
