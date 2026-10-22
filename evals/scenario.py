"""Scenario files: evals/scenarios/<agent>/<name>.yaml. See README for the schema."""

from dataclasses import dataclass, field

import yaml

from evals import config

CATEGORIES = {
    "happy_path", "ambiguous", "changes_detail", "in_data_question", "not_in_data",
    "wants_human", "emergency", "angry", "off_topic", "prompt_injection",
    "out_of_hours", "early_hangup",
}
BEHAVIOURS = {
    "cooperative", "rushed", "angry", "confused", "non_native", "silent_first",
    "interrupts", "changes_mind", "refuses_phone", "suspicious_robot", "prank", "injection",
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

    @property
    def handoff(self) -> str:
        return self.expect.get("handoff", "none")

    @property
    def save(self) -> str:
        return self.expect.get("save", "required")


_DEFAULTS = {"hidden_facts": {}, "friction": [], "judge": [], "tags": [], "hangup_after_turns": None}


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
    if d["expect"].get("handoff", "none") not in HANDOFFS:
        raise ValueError(f"{where}: expect.handoff must be one of {sorted(HANDOFFS)}")
    if d["expect"].get("save", "required") not in SAVE:
        raise ValueError(f"{where}: expect.save must be one of {sorted(SAVE)}")
    if path.parent.name != d["agent"]:
        raise ValueError(f"{where}: agent '{d['agent']}' doesn't match its folder")


def load_all(agent: str, only: str | None = None, tag: str | None = None) -> list[Scenario]:
    out = []
    for path in sorted((config.SCENARIOS_DIR / agent).glob("*.yaml")):
        d = yaml.safe_load(path.read_text())
        _validate(d, path)
        sc = Scenario(**{k: d.get(k, _DEFAULTS.get(k)) for k in Scenario.__dataclass_fields__})
        if only and sc.id != only:
            continue
        if tag and tag not in sc.tags:
            continue
        out.append(sc)
    return out
