"""Default backend: the agent's real system prompt and tool schemas run on the OpenAI
chat API in text mode. Cheap, no phone, no Retell credits."""

import json

from evals import llm
from evals.backends.base import AgentTurn, ToolCall

MAX_TOOL_ROUNDS = 4   # tool call -> result -> reply; guards against a model looping on tools


class OpenAITextSession:
    def __init__(self, spec, tools, meter, model):
        self.spec, self.tools, self.meter, self.model = spec, tools, meter, model
        self.messages = [{"role": "system", "content": spec.prompt}]
        self.turn = 0

    def opening(self):
        if not self.spec.begin:
            return None
        self.messages.append({"role": "assistant", "content": self.spec.begin})
        return AgentTurn(text=self.spec.begin)

    def respond(self, caller_text):
        self.turn += 1
        self.messages.append({"role": "user", "content": caller_text})
        out = AgentTurn(text="")
        spoken = []
        for _ in range(MAX_TOOL_ROUNDS):
            msg, usage = llm.chat(self.meter, "agent", self.model, self.messages,
                                  tools=self.spec.tools, temperature=self.spec.temperature)
            out.usage.append(usage)
            if msg.content:
                spoken.append(msg.content.strip())
            if not msg.tool_calls:
                self.messages.append({"role": "assistant", "content": msg.content or ""})
                break
            self.messages.append({"role": "assistant", "content": msg.content,
                                  "tool_calls": [{"id": tc.id, "type": "function", "function": {
                                      "name": tc.function.name, "arguments": tc.function.arguments}}
                                      for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_unparsed": tc.function.arguments}
                result = self.tools.execute(tc.function.name, args, self.turn)
                out.tool_calls.append(ToolCall(tc.function.name, args, result))
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            if self.tools.ended:
                # Retell hangs up as soon as end_call fires; nothing more is said.
                out.ended = True
                break
        out.text = " ".join(spoken)
        return out


class OpenAITextBackend:
    name = "openai-text"

    def start(self, spec, tools, meter, model):
        return OpenAITextSession(spec, tools, meter, model)
