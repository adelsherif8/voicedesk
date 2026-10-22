from evals.backends.openai_text import OpenAITextBackend
from evals.backends.retell import RetellBackend
from evals.backends.vapi import VapiBackend

BACKENDS = {b.name: b for b in (OpenAITextBackend, RetellBackend, VapiBackend)}
