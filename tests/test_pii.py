"""PII redaction: the regex engine (always on, what CI and the publish guard use), the
labelled set with precision/recall, structure redaction, and Presidio when installed."""

import json

import pytest

from evals import pii, publish

NAMES = ["Alex Brandt", "Roger Deleon", "Priya Nair"]
ALLOW = ["Patel", "Nguyen", "Sam", "Mia", "Ava", "Brightside Dental"]

# (text, [(type, value)]) : what must be found, and nothing else
LABELLED = [
    ("My number is 555 340 7718.", [("PHONE", "555 340 7718")]),
    ("Call (555) 238-6610 after five.", [("PHONE", "(555) 238-6610")]),
    ("It's +1 555 123 4567, mobile.", [("PHONE", "+1 555 123 4567")]),
    ("Reading it back: 5 5 5, 3 4 0, 7 7 1 8.", [("PHONE", "5553407718")]),
    ("Egyptian mobile 01012345678 works too.", [("PHONE", "01012345678")]),
    ("Or +20 10 1234 5678 on WhatsApp.", [("PHONE", "+20 10 1234 5678")]),
    ("Email me at jordan.mills@example.com please.", [("EMAIL", "jordan.mills@example.com")]),
    ("Card 4111 1111 1111 1111, expiry 08/28.", [("CARD", "4111 1111 1111 1111")]),
    ("Visa 4012-8888-8888-1881 ending 1881.", [("CARD", "4012-8888-8888-1881")]),
    ("I live at 3 Aspen Row.", [("ADDRESS", "3 Aspen Row")]),
    ("Service address is 14 Harbor View Dr, apt 2.", [("ADDRESS", "14 Harbor View Dr, apt 2")]),
    ("61 Willow Way, the blue house.", [("ADDRESS", "61 Willow Way")]),
    ("This is Alex Brandt calling.", [("PERSON", "Alex Brandt")]),
    ("Thanks Alex, you're booked.", [("PERSON", "Alex Brandt")]),
    ("Roger Deleon, (212) 555-0125, roger.deleon@example.com", [("PERSON", "Roger Deleon"), ("PHONE", "(212) 555-0125"), ("EMAIL", "roger.deleon@example.com")]),
    ("Priya Nair paid $110 for unit B-14.", [("PERSON", "Priya Nair")]),
    # false-positive traps: nothing here is PII
    ("The exam is $95 and the cleaning is $1,250.50.", []),
    ("Estimate #2219 is $6,800 and holds for 30 days.", []),
    ("Tuesday at 10:30 AM with Dr. Patel, or 2-4pm.", []),
    ("Member ID DD4471902, Delta Dental.", []),
    ("Order 1234 5678 9012 3456 shipped.", []),            # 16 digits, fails Luhn
    ("The 10x20 is $190/mo and the 10x10 is $110/mo.", []),
    ("Date of birth April 21, 1993, and the year 2026.", []),
    ("Sam does cleanings; Mia and Ava answer the phones.", []),
    ("Windows are 8-10am, 10am-12pm, 12-2pm, 2-4pm, 4-6pm.", []),
    ("Run 20261022-110136 cost $0.2511 over 114 calls.", []),
]

METRICS = {}   # filled by the tests, printed by conftest's terminal summary


def _report(name, engine):
    m = pii.precision_recall(engine, LABELLED)
    METRICS[name] = m
    print(f"\nPII redaction [{name}] on {len(LABELLED)} labelled strings: precision {m['precision']:.2f} recall {m['recall']:.2f} "
          f"(tp {m['tp']} fp {m['fp']} fn {m['fn']})")
    if m["misses"]:
        print("  missed:", m["misses"])
    if m["extras"]:
        print("  extra:", m["extras"])
    return m


def test_regex_engine_precision_and_recall():
    m = _report("regex", pii.RegexEngine(NAMES, ALLOW))
    assert m["precision"] >= 0.95 and m["recall"] >= 0.95, (m["misses"], m["extras"])


def test_placeholders_are_typed_and_consistent_within_a_redactor():
    rd = pii.Redactor(NAMES, ALLOW, engine="regex")
    a = rd.redact("Alex Brandt, 555 340 7718, alex@example.com")
    b = rd.redact("Thanks Alex. Confirming 5 5 5, 3 4 0, 7 7 1 8 and 555 219 4410.")
    assert a == "<PERSON_1>, <PHONE_1>, <EMAIL_1>"
    assert b == "Thanks <PERSON_1>. Confirming <PHONE_1> and <PHONE_2>."
    fresh = pii.Redactor(NAMES, ALLOW, engine="regex")
    assert fresh.redact("555 219 4410") == "<PHONE_1>"       # numbering restarts per redactor


def test_luhn():
    assert pii.luhn_ok("4111111111111111") and pii.luhn_ok("4012888888881881")
    assert not pii.luhn_ok("1234567890123456")


def test_business_names_are_allowed_through():
    rd = pii.Redactor(["Sam Patel"], ALLOW, engine="regex")
    assert rd.redact("Sam will see you; Dr. Patel is out.") == "Sam will see you; Dr. Patel is out."


def test_redact_transcript_covers_text_tool_args_and_results():
    rd = pii.Redactor(NAMES, ALLOW, engine="regex")
    tr = [{"turn": 1, "role": "caller", "text": "I'm Alex Brandt, 555 340 7718"},
          {"turn": 1, "role": "agent", "text": "Thanks Alex.", "tool_calls": [
              {"name": "book_patient", "args": {"name": "Alex Brandt", "phone": "5553407718", "outcome": "booked"},
               "result": "Saved. Records: Roger Deleon, (212) 555-0125"}]}]
    out = rd.redact_transcript(tr)
    assert out[0]["text"] == "I'm <PERSON_1>, <PHONE_1>"
    assert out[1]["tool_calls"][0]["args"] == {"name": "<PERSON_1>", "phone": "<PHONE_1>", "outcome": "booked"}
    assert out[1]["tool_calls"][0]["result"] == "Saved. Records: <PERSON_2>, <PHONE_2>"
    assert tr[0]["text"].startswith("I'm Alex")                        # the original is untouched
    assert not pii.scan(out, NAMES)


def test_scan_and_publish_guard():
    run = {"results": [{"transcript": [{"role": "agent", "text": "Call 555 340 7718"}], "events": [], "checks": [], "scenario_def": {}}]}
    found = pii.scan_run(run)
    assert found and found[0]["type"] == "PHONE" and found[0]["path"].startswith("results[0].transcript")
    with pytest.raises(publish.PIIDetected):
        publish.guard(run)
    clean = {"results": [{"transcript": [{"role": "agent", "text": "Call <PHONE_1>"}], "events": [], "checks": [], "scenario_def": {}}]}
    publish.guard(clean)


def test_known_names_include_personas_and_fixtures():
    names = pii.known_names()
    assert "Alex Brandt" in names and "Roger Deleon" in names


def test_names_for_and_allow_for_a_real_agent():
    from evals import scenario, spec
    d = spec.load("dental")
    sc = scenario.load_all("dental", only="happy-new-patient-cleaning")[0]
    names = pii.names_for(sc, [{"name": "Roger Deleon"}])
    assert "Jordan Mills" in names and "Roger Deleon" in names
    allow = pii.allow_for(d)
    assert {"Mia", "Patel", "Nguyen", "Sam"} <= set(allow)


presidio = pytest.importorskip("presidio_analyzer", reason="Presidio not installed (optional, requirements-security.txt)")


def test_presidio_engine_matches_or_beats_regex_on_the_labelled_set():
    try:
        eng = pii.PresidioEngine(NAMES, ALLOW)
    except RuntimeError:
        pytest.skip("Presidio did not initialise")
    m = _report(eng.name, eng)
    assert m["recall"] >= 0.95, m["misses"]
    assert m["precision"] >= 0.9, m["extras"]
    rd = pii.Redactor(NAMES, ALLOW, engine="presidio")
    out = rd.redact("Jordan Mills is booked Tuesday with Sam; call 555 238 6610.")
    assert "<PHONE_1>" in out and "Sam" in out
    if eng.has_ner:
        assert "Jordan Mills" not in out            # a name not in the dictionary, found by NER


def test_presidio_drops_loose_spans_and_business_names():
    try:
        eng = pii.PresidioEngine([], ["Mia", "Patel", "Sam", "Brightside Dental"])
    except RuntimeError:
        pytest.skip("Presidio did not initialise")
    text = "Good morning, Brightside Dental, this is Mia speaking. Booked [insert date and time] with Sam."
    assert [s for s in pii.resolve(eng.detect(text)) if s.type == "PERSON"] == []
