"""Vapi backend: not implemented.

No Vapi API key was found locally and the current demo agents run on Retell, so this
stays a stub. TODO: when a client agent lives on Vapi, implement start() -> Session
per evals/backends/base.py using Vapi's chat API against the assistant id, answering
tool calls with evals.stubs.ToolRuntime.
"""


class VapiBackend:
    name = "vapi"

    def start(self, spec, tools, meter, model):
        raise NotImplementedError("Vapi backend is a TODO (no key found); use --backend openai-text")
