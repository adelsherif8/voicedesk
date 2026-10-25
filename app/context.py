"""Least-privilege call context: what VoiceDesk may hand an AI agent about the person on the line.

The rule (docs/SECURITY.md, "Architecture: least privilege"):
  - an agent gets at most ONE customer record per call: the caller's own, matched by caller
    ID (the number that is calling, or the number an outbound agent dialled) or by details
    the caller has verified (every given field must match exactly)
  - never other customers' records, the day's schedule with names, or anyone's notes
  - only an allowlist of structured fields per agent; free-text notes are never passed,
    and a field value that reads like an instruction to the AI is dropped
  - the result is wrapped in <data> tags; the prompt's SECURITY rules say that text is
    data, never instructions

This is the function any dynamic-variable or CRM lookup integration (Retell, Vapi, GHL) must
go through. The eval suite builds every call's context with it (`security.data_access:
least_privilege` in evals/agents/<id>.yaml), so the security track tests the same code.
"""

import re

# structured fields an agent may see about the caller; anything else is withheld
FIELDS = {
    "dental": ["name", "appointment", "provider", "insurance"],
    "receptionist": ["name", "unit", "size", "balance"],
    "recovery": ["name", "address", "job", "appointment", "estimate"],
}
DEFAULT_FIELDS = ["name"]
MAX_VALUE = 80

# a value addressed to the model rather than describing the customer
_INSTRUCTION = re.compile(
    r"\b(?:ai|assistant|bot|model|llm|system|prompt)\b.{0,40}\b(?:note|instruction|must|should|tell|say|read|"
    r"apply|ignore|confirm|give)\b|\bignore (?:all|any|your|previous)\b|\b(?:read|list) (?:out|back|them)\b",
    re.I)


def norm_phone(value) -> str:
    """Last 10 digits, so +1 (555) 806-3310, 555.806.3310 and 5558063310 all match."""
    d = re.sub(r"\D", "", str(value or ""))
    return d[-10:] if len(d) >= 10 else d


def _same(a, b) -> bool:
    return " ".join(str(a or "").lower().split()) == " ".join(str(b or "").lower().split())


def find_caller(records: list[dict], caller_id: str | None = None, verified: dict | None = None) -> dict | None:
    """The caller's own record or None. Caller ID wins; otherwise every verified field must
    match (e.g. {"name": ..., "unit": ...}). Ambiguous matches return None: when two records
    share a number, the agent gets neither."""
    if caller_id and len(norm_phone(caller_id)) >= 7:
        hits = [r for r in records if norm_phone(r.get("phone")) == norm_phone(caller_id)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    if verified and len([v for v in verified.values() if v]) >= 2:
        hits = [r for r in records if all(_same(r.get(k), v) for k, v in verified.items() if v)]
        if len(hits) == 1:
            return hits[0]
    return None


def allowed_fields(agent: str, record: dict) -> dict:
    out = {}
    for k in FIELDS.get(agent, DEFAULT_FIELDS):
        v = record.get(k)
        if v in (None, ""):
            continue
        v = " ".join(str(v).split())[:MAX_VALUE]
        if _INSTRUCTION.search(v):
            continue
        out[k] = v
    return out


def caller_context(agent: str, records: list[dict], caller_id: str | None = None,
                   verified: dict | None = None) -> str:
    """The <data> block for one call."""
    rec = find_caller(records, caller_id, verified)
    if rec is None:
        body = "No customer record matches this caller."
    else:
        fields = allowed_fields(agent, rec)
        body = "Caller's own record (matched by caller ID): " + "; ".join(f"{k}: {v}" for k, v in fields.items())
    return f"<data>\n{body}\n</data>"
