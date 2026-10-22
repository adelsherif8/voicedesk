"""Run-wide settings. Everything here can be overridden from the CLI."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # repo root
EVALS = ROOT / "evals"
AGENTS_DIR = EVALS / "agents"
SCENARIOS_DIR = EVALS / "scenarios"
BASELINES_DIR = EVALS / "baselines"
RESULTS_DIR = EVALS / "results"
RETELL_DOC = ROOT / "docs" / "RETELL-SETUP.md"

# Models. The agents run on gpt-4.1 in Retell; gpt-4o-mini is the cheap default for
# day-to-day runs, --prod-parity switches the agent-under-test to the production model.
AGENT_MODEL = "gpt-4o-mini"
PROD_MODEL = "gpt-4.1"
CALLER_MODEL = "gpt-4o-mini"
JUDGE_MODEL = "gpt-4.1-mini"   # 4o-mini ignored grading notes in testing (false hallucinations)
CALLER_TEMPERATURE = 0.8      # callers should vary between the k runs
JUDGE_TEMPERATURE = 0.0

# USD per 1M tokens: (input, cached input, output). Update when OpenAI changes prices.
PRICES = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4.1": (2.00, 0.50, 8.00),
}

MAX_COST_USD = 1.00           # hard cap per run; the run aborts when spend crosses it
DEFAULT_K = 3
WORKERS = 6                   # simulated calls in parallel

# Per-call token use (input, output) for the pre-run estimate. Calibrated on the dental
# runs of 2026-10-22 (actual: $0.0023/call on gpt-4o-mini, $0.0095 on gpt-4.1) and
# rounded up ~1.5x, since longer agents and angrier callers make longer calls.
EST_TOKENS_PER_CALL = {"agent": (5000, 350), "caller": (5000, 250), "judge": (3500, 250)}

# Where the OpenAI key comes from: the environment first (CI), then a local .env file.
ENV_FILE = Path(os.getenv("EVALS_ENV_FILE", Path.home() / "Desktop/GHAI/card-id-pricing/.env"))


def openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key.strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No OpenAI key: set OPENAI_API_KEY or EVALS_ENV_FILE.")
