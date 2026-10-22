"""Retell backend: not implemented yet.

TODO: drive the deployed Retell LLM (ids in docs/retell_created.json, key in
~/.retell_key) turn by turn instead of a local copy of its prompt, so the suite also
catches drift between docs/RETELL-SETUP.md and what is live. Tool calls must still be
answered by evals.stubs.ToolRuntime, not the production webhook, so test runs never
write to the live dashboard. Implement start() -> Session per evals/backends/base.py.
"""


class RetellBackend:
    name = "retell"

    def start(self, spec, tools, meter, model):
        raise NotImplementedError("Retell backend is a TODO; use --backend openai-text")
