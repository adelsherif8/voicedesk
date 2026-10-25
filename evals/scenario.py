"""Scenario files: evals/scenarios/<agent>/<name>.yaml. See README for the schema."""

from dataclasses import dataclass, field

import yaml

from evals import config

CATEGORIES = {
    "happy_path", "ambiguous", "changes_detail", "in_data_question", "not_in_data",
    "wants_human", "emergency", "angry", "off_topic", "prompt_injection",
    "out_of_hours", "early_hangup", "security",
}
BEHAVIOURS = {
    "cooperative", "rushed", "angry", "confused", "non_native", "silent_first",
    "interrupts", "changes_mind", "refuses_phone", "suspicious_robot", "prank", "injection", "persistent",
}
HANDOFFS = {"none", "human", "emergency", "safety"}
SAVE = {"required", "optional", "forbidden"}


@dataclass(frozen=True)
class Scenario:
    id: str
    agent: str
    title: str
    category: str
    persona: dict
    goal: str
    hidden_facts: dict
    friction: list
    stop: str
    max_turns: int
    expect: dict
    judge: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    hangup_after_turns: int | None = None   # caller hangs up after N of their turns, no matter what
    tool_results: dict = field(default_factory=dict)   # tool name -> what the stub answers ({records} = fixtures)
    context: str = ""                                  # data_access: all -- raw text loaded into the prompt ({records} = fixtures)
    crm_record: dict = field(default_factory=dict)     # data_access: least_privilege -- the caller's own CRM record
    owasp: list = field(default_factory=list)          # security scenarios: OWASP LLM Top 10 2025 ids, e.g. [LLM01]

    @property
    def handoffs(self) -> list[str]:
        """Acceptable handoff outcomes; a scenario may allow several (e.g. [none, human])."""
        h = self.expect.get("handoff", "none")
        return [h] if isinstance(h, str) else list(h)

    @property
    def handoff(self) -> str:
        return "|".join(self.handoffs)

    @property
    def save(self) -> str:
        return self.expect.get("save", "required")


_DEFAULTS = {"hidden_facts": {}, "friction": [], "judge": [], "tags": [], "hangup_after_turns": None,
             "tool_results": {}, "owasp": [], "context": "", "crm_record": {}}
OWASP_IDS = {"LLM01", "LLM02", "LLM03", "LLM04", "LLM05", "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"}


def _validate(d: dict, path) -> None:
    where = path.relative_to(config.ROOT)
    for key in ("id", "agent", "title", "category", "persona", "goal", "stop", "max_turns", "expect"):
        if key not in d:
            raise ValueError(f"{where}: missing '{key}'")
    if d["category"] not in CATEGORIES:
        raise ValueError(f"{where}: category '{d['category']}' not in {sorted(CATEGORIES)}")
    bad = set(d["persona"].get("behaviour", [])) - BEHAVIOURS
    if bad:
        raise ValueError(f"{where}: unknown behaviour {sorted(bad)}; allowed {sorted(BEHAVIOURS)}")
    h = d["expect"].get("handoff", "none")
    if not set([h] if isinstance(h, str) else h) <= HANDOFFS:
        raise ValueError(f"{where}: expect.handoff must be one of {sorted(HANDOFFS)}")
    if d["expect"].get("save", "required") not in SAVE:
        raise ValueError(f"{where}: expect.save must be one of {sorted(SAVE)}")
    if path.parent.name != d["agent"]:
        raise ValueError(f"{where}: agent '{d['agent']}' doesn't match its folder")
    tr = d.get("tool_results") or {}
    if not isinstance(tr, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tr.items()):
        raise ValueError(f"{where}: tool_results must map tool names to strings")
    if not isinstance(d.get("context", ""), str):
        raise ValueError(f"{where}: context must be a string")
    if not isinstance(d.get("crm_record") or {}, dict):
        raise ValueError(f"{where}: crm_record must be a mapping")
    bad = set(d.get("owasp") or []) - OWASP_IDS
    if bad:
        raise ValueError(f"{where}: unknown OWASP ids {sorted(bad)}")
    if d["category"] == "security" and not d.get("owasp"):
        raise ValueError(f"{where}: security scenarios must list the OWASP LLM Top 10 ids they test (owasp: [LLM01])")


def load_all(agent: str, only: str | None = None, tag: str | None = None) -> list[Scenario]:
    out = []
    for path in sorted((config.SCENARIOS_DIR / agent).glob("*.yaml")):
        try:
            d = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise ValueError(f"{path.relative_to(config.ROOT)}: invalid YAML: {e}") from None
        _validate(d, path)
        sc = Scenario(**{k: d.get(k, _DEFAULTS.get(k)) for k in Scenario.__dataclass_fields__})
        if only and sc.id != only:
            continue
        if tag and tag not in sc.tags:
            continue
        out.append(sc)
    return out
