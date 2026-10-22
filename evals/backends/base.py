"""The adapter interface. Scenarios, checks and metrics only ever see AgentTurn and the
ToolRuntime event log, so a new backend (Retell, Vapi) plugs in without touching them."""

from dataclasses import dataclass, field
from typing import Protocol

from evals.llm import Meter, Usage
from evals.spec import AgentSpec
from evals.stubs import ToolRuntime


@dataclass
class ToolCall:
    name: str
    args: dict
    result: str


@dataclass
class AgentTurn:
    text: str                                       # what the agent said out loud
    tool_calls: list[ToolCall] = field(default_factory=list)  # already executed
    ended: bool = False                             # end_call fired
    usage: list[Usage] = field(default_factory=list)


class Session(Protocol):
    def opening(self) -> AgentTurn | None:
        """The agent's first line when it speaks first (Retell begin message), else None."""

    def respond(self, caller_text: str) -> AgentTurn:
        """Feed one caller utterance; runs any tool calls internally and returns the reply."""


class AgentBackend(Protocol):
    name: str

    def start(self, spec: AgentSpec, tools: ToolRuntime, meter: Meter, model: str) -> Session:
        ...
