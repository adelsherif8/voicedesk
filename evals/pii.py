"""PII detection and redaction for the eval suite.

Where it runs (see runner.run_call, publish.guard, app.main.evals_ingest):
  1. after the deterministic checks, before the transcript goes to the LLM judge
  2. before a result is stored in evals/results/ or sent to VoiceDesk
  3. as a publish guard: a run with detectable PII left in it is refused

Engines
  presidio  Microsoft Presidio analyzer + anonymizer (optional: `pip install -r
            requirements-security.txt`). Adds NER-based PERSON detection on top of the
            regex engine when a spaCy model loads; without one, Presidio's pattern
            recognizers still run.
  regex     always on, no models: US and Egyptian phone numbers (including numbers read
            out digit by digit), emails, card numbers that pass a Luhn check, street
            addresses, and a dictionary of known names (the scenario personas and the
            fixture customers). This is what CI and the publish guard use, so the gate
            is deterministic.

Values become typed placeholders, numbered in order of first appearance and consistent
within one Redactor (one simulated call): <PERSON_1>, <PHONE_1>, <EMAIL_1>, <CARD_1>,
<ADDRESS_1>. Business names (the agent's own name, providers, the company) are allowed
through so the judge can still check grounding against the prompt.
"""

import copy
import json
import re
import threading
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"<(?:PERSON|PHONE|EMAIL|CARD|ADDRESS)_\d+>")

# ---- regex engine -----------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 13-19 digits with optional single spaces/dashes; confirmed with Luhn below
_CARD = re.compile(r"(?<![\d])(?:\d[ -]?){12,18}\d(?![\d])")
# US/NANP: 555 340 7718, (555) 238-6610, 555.238.6610, +1 555 123 4567, 5552386610
_PHONE_US = re.compile(r"(?<![\d-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?![\d-])")
# a number read out one digit at a time: "5 5 5, 3 4 0, 7 7 1 8"
_PHONE_SPOKEN = re.compile(r"(?<!\d)\d(?:[ ,.-]{1,2}\d){9}(?!\d)")
# Egypt: 010/011/012/015 + 8 digits, with or without +20 / 0020
_PHONE_EG = re.compile(r"(?<!\d)(?:\+?20[\s-]?|0020[\s-]?|0)1[0125](?:[\s-]?\d){8}(?!\d)")
_STREET = ("Street|St|Avenue|Ave|Road|Rd|Row|Way|Lane|Ln|Drive|Dr|Boulevard|Blvd|Court|Ct|Place|Pl|"
           "Terrace|Ter|Circle|Cir|Trail|Trl|Parkway|Pkwy|Highway|Hwy|Square|Sq")
_ADDRESS = re.compile(r"\b\d{1,5}\s+(?:[A-Z][A-Za-z']+\s+){1,3}(?:" + _STREET + r")\b"
                      r"(?:,?\s+(?i:apt|apartment|suite|ste|unit|#)\.?\s*[\w-]+)?")

# words that happen to be first names in the fixtures but are too common to redact alone
_NAME_STOP = {"may", "will", "grace", "rose", "hope", "joy", "mark", "bill", "sue", "art", "jack", "june"}


def luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def norm_phone(s: str) -> str:
    d = _digits(s)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if d.startswith("0020"):
        d = d[2:]
    if len(d) == 11 and d.startswith("01"):   # Egyptian national format -> international
        d = "20" + d[1:]
    return d


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type: str
    value: str
    source: str = "regex"


def _name_patterns(names, allow) -> list[tuple[re.Pattern, str]]:
    """(pattern, canonical full name) for every known name and its distinctive parts."""
    allowed = {a.lower() for a in allow}
    out, seen = [], set()
    for full in names:
        full = " ".join(str(full or "").split())
        if not full or full.lower() in seen:
            continue
        seen.add(full.lower())
        parts = [p for p in re.findall(r"[A-Za-z][A-Za-z'-]+", full)]
        if not parts:
            continue
        out.append((re.compile(r"\b" + r"\s+".join(re.escape(p) for p in parts) + r"\b", re.I), full))
        for p in parts:
            if len(p) >= 3 and p.lower() not in allowed and p.lower() not in _NAME_STOP:
                # one part alone is case-sensitive: "Fields" is a surname, "fields" is a word
                cap = p[0].upper() + p[1:]
                out.append((re.compile(r"\b(?:" + re.escape(cap) + "|" + re.escape(p.upper()) + r")\b"), full))
    return out


class RegexEngine:
    name = "regex"

    def __init__(self, names=(), allow=()):
        self.names = _name_patterns(names, allow)

    def detect(self, text: str) -> list[Span]:
        if not text:
            return []
        spans = []
        for m in _EMAIL.finditer(text):
            spans.append(Span(m.start(), m.end(), "EMAIL", m.group(0)))
        for m in _CARD.finditer(text):
            d = _digits(m.group(0))
            if 13 <= len(d) <= 19 and luhn_ok(d):
                spans.append(Span(m.start(), m.end(), "CARD", m.group(0)))
        for rx in (_PHONE_EG, _PHONE_US, _PHONE_SPOKEN):
            for m in rx.finditer(text):
                spans.append(Span(m.start(), m.end(), "PHONE", m.group(0)))
        for m in _ADDRESS.finditer(text):
            spans.append(Span(m.start(), m.end(), "ADDRESS", m.group(0)))
        for rx, full in self.names:
            for m in rx.finditer(text):
                spans.append(Span(m.start(), m.end(), "PERSON", full))
        return spans


# ---- Presidio engine (optional) -----------------------------------------------------

_PRESIDIO_TYPES = {"PERSON": "PERSON", "PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL", "CREDIT_CARD": "CARD"}
_presidio_lock = threading.Lock()
_TITLE_WORD = re.compile(r"[A-Z][a-z]+(?:['-][A-Za-z][a-z]*)*(?:[A-Z][a-z]+)?[.,;:!?]*")   # Mia, O'Neil, McIntosh; not VD, CANARY
_presidio = None          # (analyzer, anonymizer, has_ner) or False once probed


def _load_presidio():
    """Build Presidio once per process. Returns None when it isn't installed."""
    global _presidio
    with _presidio_lock:
        if _presidio is not None:
            return _presidio or None
        import logging
        logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)   # unmapped spaCy labels are expected
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine
        except ImportError:
            _presidio = False
            return None
        nlp, has_ner = None, False
        try:
            import spacy.util
            installed = [m for m in ("en_core_web_lg", "en_core_web_md", "en_core_web_sm") if spacy.util.is_package(m)]
        except Exception:
            installed = []
        for model in installed:   # only models already installed: Presidio would otherwise download one
            try:
                nlp = NlpEngineProvider(nlp_configuration={
                    "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": model}]}).create_engine()
                has_ner = True
                break
            except Exception:   # incompatible model build: fall through to pattern-only
                nlp = None
        if nlp is None:
            nlp = _NoNerEngine()
        try:
            analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
            _presidio = (analyzer, AnonymizerEngine(), has_ner)
        except Exception:
            _presidio = False
            return None
        return _presidio


def _no_ner_engine_class():
    from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine

    class NoNerEngine(NlpEngine):
        """Presidio needs an NLP engine; this one tokenizes on whitespace and finds no
        entities, so only the pattern recognizers (phone, email, card, ...) run."""

        def load(self):
            pass

        def is_loaded(self):
            return True

        def process_text(self, text, language):
            tokens = text.split()
            return NlpArtifacts(entities=[], tokens=tokens, tokens_indices=[], lemmas=[w.lower() for w in tokens],
                                nlp_engine=self, language=language)

        def process_batch(self, texts, language, **kw):
            return [(t, self.process_text(t, language)) for t in texts]

        def is_stopword(self, word, language):
            return False

        def is_punct(self, word, language):
            return not any(ch.isalnum() for ch in word)

        def get_supported_entities(self):
            return []

        def get_supported_languages(self):
            return ["en"]

    return NoNerEngine


def _NoNerEngine():
    return _no_ner_engine_class()()


class PresidioEngine:
    """Presidio detections merged with the regex engine (Presidio has no Egyptian phone
    pattern and no dictionary of the fixture names). PERSON is only produced when a spaCy
    model loaded; the allow list keeps business names out."""

    def __init__(self, names=(), allow=()):
        loaded = _load_presidio()
        if not loaded:
            raise RuntimeError("presidio not installed")
        self.analyzer, self.anonymizer, self.has_ner = loaded
        self.regex = RegexEngine(names, allow)
        self.allow = list(allow)
        self.allow_tokens = {w.lower() for a in allow for w in re.findall(r"[A-Za-z]+", a)}
        self.name = "presidio+ner" if self.has_ner else "presidio-patterns"

    def detect(self, text: str) -> list[Span]:
        spans = self.regex.detect(text)
        if not text:
            return spans
        with _presidio_lock:
            results = self.analyzer.analyze(text=text, language="en", entities=list(_PRESIDIO_TYPES),
                                            allow_list=self.allow or None, score_threshold=0.5)
        for r in results:
            t = _PRESIDIO_TYPES[r.entity_type]
            if t == "PERSON":
                frag = text[r.start:r.end]
                words = re.findall(r"[A-Za-z]+", frag)
                # spaCy spans are loose ("Mia speaking", "[insert date"): keep only capitalised
                # names that contain no business name and aren't placeholder text
                # single words ("Drive safely", "See you") are left to the name dictionary
                if (r.score < 0.7 or len(words) < 2 or not frag[0].isupper() or "<" in frag or "[" in frag
                        or any(ch.isdigit() for ch in frag)
                        or not all(_TITLE_WORD.fullmatch(w) for w in frag.replace("’", "'").split())
                        or any(w.lower() in self.allow_tokens for w in words)):
                    continue
            spans.append(Span(r.start, r.end, t, text[r.start:r.end], "presidio"))
        return spans


# ---- the redactor ----------------------------------------------------------------------

def resolve(spans: list[Span]) -> list[Span]:
    """Longest span wins where two overlap; returns them in text order."""
    out = []
    for s in sorted(spans, key=lambda s: (s.start, -(s.end - s.start))):
        if out and s.start < out[-1].end:
            continue
        out.append(s)
    return out


class Redactor:
    def __init__(self, names=(), allow=(), engine: str = "auto"):
        if engine == "auto":
            try:
                self.engine = PresidioEngine(names, allow)
            except RuntimeError:
                self.engine = RegexEngine(names, allow)
        elif engine == "presidio":
            self.engine = PresidioEngine(names, allow)
        elif engine == "regex":
            self.engine = RegexEngine(names, allow)
        else:
            raise ValueError(f"unknown engine {engine!r}")
        self.map: dict[tuple[str, str], str] = {}     # (type, normalized value) -> placeholder
        self.counts: dict[str, int] = {}
        self._lock = threading.Lock()

    @property
    def engine_name(self) -> str:
        return self.engine.name

    def _key(self, span: Span) -> str:
        if span.type in ("PHONE", "CARD"):
            return norm_phone(span.value) if span.type == "PHONE" else _digits(span.value)
        return " ".join(span.value.lower().split())

    def placeholder(self, span: Span) -> str:
        key = (span.type, self._key(span))
        with self._lock:
            if key not in self.map:
                self.counts[span.type] = self.counts.get(span.type, 0) + 1
                self.map[key] = f"<{span.type}_{self.counts[span.type]}>"
            return self.map[key]

    def detect(self, text: str) -> list[Span]:
        return resolve(self.engine.detect(text))

    def redact(self, text) -> str:
        if not isinstance(text, str) or not text:
            return text
        spans = self.detect(text)
        if not spans:
            return text
        if isinstance(self.engine, PresidioEngine):
            return self._anonymize_with_presidio(text, spans)
        out, pos = [], 0
        for s in spans:
            out.append(text[pos:s.start])
            out.append(self.placeholder(s))
            pos = s.end
        out.append(text[pos:])
        return "".join(out)

    def _anonymize_with_presidio(self, text: str, spans: list[Span]) -> str:
        from presidio_analyzer import RecognizerResult
        from presidio_anonymizer.entities import OperatorConfig
        # one operator per entity type; the lambda hands out our consistent placeholders
        by_type = {}
        for s in spans:
            by_type.setdefault(s.type, {})[text[s.start:s.end]] = self.placeholder(s)
        results = [RecognizerResult(entity_type=s.type, start=s.start, end=s.end, score=1.0) for s in spans]
        operators = {t: OperatorConfig("custom", {"lambda": (lambda v, m=m: m.get(v, next(iter(m.values()))))})
                     for t, m in by_type.items()}
        return self.engine.anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text

    # ---- structures ----
    def redact_obj(self, obj):
        """Deep copy with every string redacted (dict keys untouched)."""
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {k: self.redact_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.redact_obj(v) for v in obj]
        return copy.deepcopy(obj)

    def redact_transcript(self, transcript: list) -> list:
        return self.redact_obj(transcript)


# ---- helpers used by the runner ------------------------------------------------------------

def names_for(scenario, others=()) -> list[str]:
    """Names to treat as PII in one call: the caller's and the fixture customers'."""
    names = [scenario.persona.get("name", "")]
    for k in ("full_name", "name"):
        if scenario.hidden_facts.get(k):
            names.append(str(scenario.hidden_facts[k]))
    names += [o["name"] for o in others]
    return [n for n in names if n]


def allow_for(spec) -> list[str]:
    """Business names the agent may say: its own name, providers, the company."""
    allow = set()
    for m in re.finditer(r"\bthis is (\w+)", (spec.begin or "") + " " + spec.prompt, re.I):
        allow.add(m.group(1))
    allow.add(spec.name)
    for p in spec.registry.get("providers", []):
        for w in re.findall(r"[A-Za-z]{3,}", p):
            if w.lower() not in ("hygiene",):
                allow.add(w)
    if spec.registry.get("business"):
        allow.add(spec.registry["business"])
    return sorted(allow)


def scan(obj, names=(), allow=()) -> list[dict]:
    """Deterministic (regex engine) scan of any JSON-like structure. Returns findings
    [{type, value, path}], empty when the structure is clean. Used by the publish guard."""
    eng = RegexEngine(names, allow)
    found = []

    def walk(o, path):
        if isinstance(o, str):
            for s in resolve(eng.detect(o)):
                found.append({"type": s.type, "value": s.value, "path": path})
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")

    walk(obj, "$")
    return found


def scan_run(run: dict, names=()) -> list[dict]:
    """The publish guard's view of a run: every result's transcript, events, checks and
    scenario definition. Summary numbers can't hold PII and are skipped."""
    found = []
    for i, r in enumerate(run.get("results") or []):
        for key in ("transcript", "events", "checks", "scenario_def", "title"):
            found += [{**f, "path": f"results[{i}].{key}" + f["path"][1:]} for f in scan(r.get(key), names)]
    return found


def known_names() -> list[str]:
    """Every persona name in the scenario files plus every fixture customer: the
    dictionary the publish guard redacts against."""
    import yaml

    from evals import config
    from evals.fixtures import all_names
    names = set(all_names())
    for path in config.SCENARIOS_DIR.glob("*/*.yaml"):
        try:
            d = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        for v in (d.get("persona", {}).get("name"), d.get("hidden_facts", {}).get("full_name")):
            if v:
                names.add(str(v))
    return sorted(names)


def precision_recall(engine, labelled: list[tuple[str, list[tuple[str, str]]]]) -> dict:
    """Entity-level precision/recall of `engine` on [(text, [(type, value), ...]), ...].
    A prediction matches when type and normalized value agree."""
    def norm(t, v):
        return (t, norm_phone(v) if t in ("PHONE", "CARD") else " ".join(v.lower().split()))
    tp = fp = fn = 0
    misses, extras = [], []
    for text, gold in labelled:
        want = {norm(t, v) for t, v in gold}
        got = {norm(s.type, s.value if s.type != "PERSON" else text[s.start:s.end]) for s in resolve(engine.detect(text))}
        # a PERSON hit on part of a name counts when it belongs to a gold name
        got_persons = {g for g in got if g[0] == "PERSON"}
        for g in list(got_persons):
            full = next((w for w in want if w[0] == "PERSON" and g[1] in w[1]), None)
            if full:
                got.discard(g)
                got.add(full)
        tp += len(want & got)
        fp += len(got - want)
        fn += len(want - got)
        misses += [(text, m) for m in want - got]
        extras += [(text, e) for e in got - want]
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"precision": p, "recall": r, "tp": tp, "fp": fp, "fn": fn, "misses": misses, "extras": extras}


if __name__ == "__main__":   # python -m evals.pii "text ..."  -> show what would be redacted
    import sys
    rd = Redactor(names=known_names())
    text = " ".join(sys.argv[1:]) or sys.stdin.read()
    print(f"engine: {rd.engine_name}")
    for s in rd.detect(text):
        print(f"  {s.type:8} {s.value!r}  ({s.source})")
    print(rd.redact(text))
