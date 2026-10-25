"""AgentSpec: everything needed to run one agent under test.

The prompt, opening line and tool schema come from docs/RETELL-SETUP.md, the same
file scripts/retell_provision.py pushes to Retell, so the suite tests exactly what is
deployed. evals/agents/<id>.yaml adds what the doc doesn't hold: which data the tool
stubs are backed by, what counts as a handoff, and the model settings. An agent that
isn't in the doc can point `prompt_file` at a markdown prompt instead.
"""

import copy
import importlib.util
from dataclasses import dataclass, field, replace

import yaml

from app.agents import AGENTS_BY_ID
from evals import config

# Retell adds this built-in tool to every agent (see scripts/retell_provision.py).
END_CALL_TOOL = {"type": "function", "function": {
    "name": "end_call",
    "description": "End the call once everything is saved and the caller has no further questions.",
    "parameters": {"type": "object", "properties": {}}}}


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    prompt: str
    begin: str                 # opening line; empty when the caller speaks first
    tools: list                # OpenAI tool schemas, end_call included
    save_tool: str
    temperature: float
    model: str | None          # None -> run default
    resource: dict             # stub backing data config (see stubs.py)
    handoff: list              # ordered rules, first match wins (see checks.detect_handoff)
    allowed_prices: list       # dollar amounts the agent may say
    judge_notes: str           # agent-specific grading notes, e.g. known gaps tracked elsewhere
    registry: dict = field(repr=False, default_factory=dict)  # app/agents.py entry
    security: dict = field(default_factory=dict)   # e.g. transfer_allowlist (see checks.security_checks)
    patches: tuple = ()        # descriptions of deliberate breakages applied

    def without(self, text: str, note: str) -> "AgentSpec":
        """Copy of this spec with `text` removed from the prompt (for breakage tests)."""
        if text not in self.prompt:
            raise ValueError(f"patch target not found in {self.id} prompt: {text[:60]!r}")
        return replace(self, prompt=self.prompt.replace(text, ""), patches=self.patches + (note,))

    def without_in_tool(self, param: str, text: str, note: str) -> "AgentSpec":
        """Copy with `text` removed from the save tool's `param` description."""
        tools = copy.deepcopy(self.tools)
        props = next(t for t in tools if t["function"]["name"] == self.save_tool)["function"]["parameters"]["properties"]
        if text not in props[param]["description"]:
            raise ValueError(f"patch target not found in {self.save_tool}.{param}: {text!r}")
        props[param]["description"] = props[param]["description"].replace(text, "")
        return replace(self, tools=tools, patches=self.patches + (note,))


def _parse_retell_doc() -> dict:
    path = config.ROOT / "scripts" / "retell_provision.py"
    spec = importlib.util.spec_from_file_location("retell_provision", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {a["id"]: a for a in mod.parse_doc()}


def available() -> list[str]:
    return sorted(p.stem for p in config.AGENTS_DIR.glob("*.yaml"))


def load(agent_id: str) -> AgentSpec:
    cfg_path = config.AGENTS_DIR / f"{agent_id}.yaml"
    if not cfg_path.exists():
        raise SystemExit(f"no agent config {cfg_path.relative_to(config.ROOT)}")
    cfg = yaml.safe_load(cfg_path.read_text())

    if cfg.get("prompt_file"):
        prompt = (config.AGENTS_DIR / cfg["prompt_file"]).read_text().strip()
        begin = cfg.get("begin", "")
        save_fn = {"type": "function", "function": cfg["save_tool_schema"]}
    else:
        doc = _parse_retell_doc()[agent_id]
        prompt, begin = doc["prompt"], doc["begin"]
        save_fn = {"type": "function", "function": {
            "name": doc["fn_name"], "description": doc["fn_desc"], "parameters": doc["fn_params"]}}

    tools = [save_fn] + [copy.deepcopy(t) for t in cfg.get("extra_tools", [])] + [END_CALL_TOOL]
    return AgentSpec(
        id=agent_id,
        name=AGENTS_BY_ID.get(agent_id, {}).get("name", agent_id),
        prompt=prompt,
        begin=begin if cfg.get("speaks_first", True) else "",
        tools=tools,
        save_tool=save_fn["function"]["name"],
        temperature=float(cfg.get("temperature", 0)),
        model=cfg.get("model"),
        resource=cfg.get("resource", {}),
        handoff=cfg.get("handoff", []),
        allowed_prices=[float(p) for p in cfg.get("allowed_prices", [])],
        judge_notes=(cfg.get("judge_notes") or "").strip(),
        registry=AGENTS_BY_ID.get(agent_id, {}),
        security=cfg.get("security") or {},
    )
