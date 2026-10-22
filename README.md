# VoiceDesk — Shared Dashboard for AI Voice Agents

One live dashboard (a lightweight CRM) that every AI voice-agent demo feeds. Each
agent style — receptionist, sales follow-up, booking, FAQ, restaurant, reactivation —
posts captured calls, leads, and bookings here, shown live and filterable by agent.

Built to sit behind Vapi / Retell agents:
- `POST /vapi/{agent}` — handles Vapi tool-calls + end-of-call reports.
- `POST /ingest/{agent}` — generic JSON ingest (Retell / n8n / manual).
- `POST /simulate/{agent}` — drop a sample record to demo the live dashboard.
- `GET /records?agent=` — live feed the dashboard polls.

A one-line connector pushes the same records into GoHighLevel or any CRM.

Stack: Python · FastAPI · SQLite · (OpenAI for agent logic in the voice layer).
Built by Adel Atya.

## Agent regression & simulation suite (`evals/`)

How do you know the agent still works after you change its prompt? Before every deploy,
the suite phones each demo agent with scripted fake callers, scores every call, and shows
containment and transfer metrics on a live page at **`/evals`** (the Agent QA console).

### What it does
- **Agent under test (text mode).** Runs each agent's real system prompt, opening line and
  tool schema, parsed from `docs/RETELL-SETUP.md` (the file `scripts/retell_provision.py`
  pushes to Retell), on an LLM. Tool calls hit stubs backed by the same data the dashboards
  use (`app/agents.py`): a booking takes a real slot on the dental calendar, a reservation
  takes a storage unit, a plumbing job takes a truck window. Backends sit behind an adapter
  (`evals/backends/base.py`); Retell and Vapi adapters are stubbed with TODOs.
- **Simulated callers.** Each scenario is a YAML file with a persona, goal, facts the caller
  only reveals when asked, behaviours (rushed, angry, confused, non-native English, silent
  at first, interrupts, changes their mind, refuses a phone number, asks "are you a robot?",
  prank, prompt injection), friction lines, a stop condition and the expected outcome. The
  caller is its own LLM, prompted to be unhelpful by default.
- **Scoring, deterministic first.** Code checks: right tool called, saved fields match the
  expected values, handoff when required and only then, every dollar amount and booking
  exists in the data, forbidden phrases never said, call ended cleanly, turn budget. An LLM
  judge (gpt-4.1-mini, temperature 0, written rubric, one-line reason per verdict) handles
  only what code can't: grounding of free-text claims, tone, did it answer the question.
  Every result keeps the full transcript.
- **38 scenarios** for 3 agents (dental, recovery/plumbing, receptionist/storage), each
  agent covering: happy path, ambiguous request, detail changed mid-call, price/policy
  question in the data, question not in the data, wants a human, emergency, angry caller,
  off-topic/prank, prompt injection, out of hours, early hang-up.

### Metric definitions
Defined once in `evals/metrics.py` (the page shows the same text):

| Metric | Definition |
|---|---|
| Containment rate | Calls where the caller's goal was completed by the agent with no handoff, ÷ all calls. The call must end cleanly: the agent closes it, or the caller says goodbye after the goal is met. Abrupt hang-ups and abandoned calls are never contained, whatever was captured. |
| Transfer rate | Calls with a handoff (live transfer, or the agent's escalation outcome such as an emergency booking or a staff callback) ÷ all calls; split into correct (the scenario allowed it) and unnecessary (the right answer was no handoff). |
| Missed handoff | The scenario required a handoff and none happened. A critical failure: it fails the call and, in regression mode, fails the run. |
| Task success | The saved record matched every required field, over calls whose scenario defines required fields. |
| Hallucination rate | Calls where the agent stated a price, slot, policy or fact not in its data. |
| Pass^k | Each scenario runs k times (default 3); it passes only if all k pass. Some-but-not-all is flaky. |

### Running it
```bash
pip install -r requirements.txt -r requirements-dev.txt
# OpenAI key: OPENAI_API_KEY env var, or a .env file at EVALS_ENV_FILE
python -m evals run --agent dental --k 3          # one agent
python -m evals run --all --k 3                   # everything, prints the summary table
python -m evals run --agent recovery --scenario emergency-gas-smell --k 5
python -m evals run --all --tag smoke --k 1       # the CI subset
python -m evals run --all --k 3 --prod-parity --max-cost 2   # on gpt-4.1, the model the agents run on
python -m evals run --all --k 3 --baseline save   # save baselines (per agent, per model)
python -m evals run --all --k 3 --publish         # post to VoiceDesk (default http://127.0.0.1:8000)
python -m evals publish evals/results/run-<id>.json --url https://<your-render-app>
pytest                 # 88 unit tests, no network
pytest -m live         # proves the suite catches 3 deliberate prompt breakages (~$0.08)
```
Exit codes: `0` ok, `1` regression against the baseline, `2` usage error, `3` cost cap hit.
A hard cost cap per run (default $1, `--max-cost`) aborts the run when crossed; the
estimate is printed before starting.

### Regression mode & CI
Every run compares against `evals/baselines/<agent>.<model>.json` and exits 1 when a
scenario that passed every baseline attempt now fails every attempt (confirmed with 2
extra re-runs, `--confirm`), when a scenario gets a missed handoff it never had (never
retried), or when containment drops more than 10 points over at least 10 shared calls.
Pass to flaky is a warning (`--strict` makes it a failure).

GitHub Actions: `evals.yml` runs the unit tests on PRs (free); `evals-smoke.yml` runs the
`smoke` scenarios at k=1 against the baselines when a prompt, registry data, scenario or
baseline changes (about $0.02 a run, $0.10 cap, skipped without the `OPENAI_API_KEY`
secret; use a key from a dedicated OpenAI project with a low monthly budget).

### Adding an agent or a scenario
- **Scenario:** drop a YAML file into `evals/scenarios/<agent>/` (copy one from the same
  category). It is validated on load; tag it `smoke` to include it in CI. Then refresh its
  baseline: `python -m evals run --agent <id> --scenario <name> --k 3 --baseline save`.
- **Agent:** add its block to `docs/RETELL-SETUP.md` (or point `prompt_file` at a markdown
  prompt), add `evals/agents/<id>.yaml` (data resource: `calendar`, `inventory` or
  `truck_board`; allowed prices; what counts as a handoff), then add scenarios. No code.

### Publishing to VoiceDesk
`--publish` posts the run to `POST /evals/ingest` and updates
`evals/results/published.json`, a committed snapshot VoiceDesk loads on boot when its
tables are empty (Render's free disk is wiped on each deploy). On Render, set
`EVALS_INGEST_TOKEN` and export the same value locally to publish remotely; without it,
only localhost can publish.

### Cost per run (measured, gpt-4o-mini agent and caller, gpt-4.1-mini judge)
| Run | Calls | Cost |
|---|---|---|
| `--all --k 3` | 114 | $0.25 |
| `--all --tag smoke --k 1` (CI) | 8 | ~$0.02 |
| one agent, `--k 3` | 36-39 | ~$0.08 |
| `--all --k 3 --prod-parity` (gpt-4.1 agent, estimate) | 114 | ~$1.0-1.5 |

### Known limits
Text mode only: no audio, latency, barge-in or speech-recognition errors. Simulated callers
are LLMs and can still be more cooperative than real people. gpt-4o-mini behaves
differently from the production gpt-4.1, so treat a mini pass as a smoke test and use
`--prod-parity` before a client deploy.
