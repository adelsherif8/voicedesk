"""Deterministic checks and tool stubs: no network, no LLM."""

import pytest

from evals import checks, spec
from evals.scenario import Scenario
from evals.stubs import ToolRuntime, parse_day, parse_time


def sc(**expect):
    return Scenario(id="t", agent="dental", title="t", category="happy_path", persona={}, goal="g",
                    hidden_facts={}, friction=[], stop="s", max_turns=10, expect={"handoff": "none", **expect})


def agent(text, turn, calls=()):
    return {"turn": turn, "role": "agent", "text": text, "tool_calls": list(calls)}


def caller(text, turn):
    return {"turn": turn, "role": "caller", "text": text}


@pytest.fixture
def dental():
    return spec.load("dental")


# --- parsing ---------------------------------------------------------------------

@pytest.mark.parametrize("text,minutes", [
    ("Tuesday at 10:30 AM", 630), ("2-4pm", 840), ("10am-12pm", 600), ("10-12pm", 600),
    ("11-1pm", 660), ("12-2pm", 720), ("8–10", 480), ("Today 4:30", 990), ("noon", 720),
    ("March 14, 2016", None), ("555 410 2287", None), ("2 kids", None),
])
def test_parse_time(text, minutes):
    assert parse_time(text) == minutes


def test_parse_day():
    assert parse_day("tomorrow at 9", "Mon") == "Tue"
    assert parse_day("come in right now", "Wed") == "Wed"
    assert parse_day("Thursday 3 PM", "Mon") == "Thu"
    assert parse_day("2023-10-04T10:00", "Mon") is None


# --- field matchers ---------------------------------------------------------------

@pytest.mark.parametrize("value,rule,ok", [
    ("New Patient Booked", {"equals": "new patient booked"}, True),
    ("Jordan", {"contains": "Mills"}, False),
    ("+1 (555) 238-6610", {"digits": "5552386610"}, True),
    ("555 238 661", {"digits": "5552386610"}, False),
    ("Wednesday 2 PM", {"matches": "(?i)wed", "not_matches": "(?i)fri"}, True),
    ("Friday 9 AM", {"matches": "(?i)wed|fri", "not_matches": "(?i)fri"}, False),
    ("", {"present": True}, False),
    ("Sat 10am", {"present": True, "not_matches": "(?i)sat"}, False),
    ("", {"present": False}, True),
    (None, {"one_of": ["a"]}, False),
])
def test_match_field(value, rule, ok):
    assert checks.match_field(value, rule)[0] is ok


def test_amounts():
    assert checks.amounts("It's $1,250.50 or 95 dollars, not 3 kids") == [1250.5, 95.0]


# --- stubs: bookings consume inventory ----------------------------------------------

def test_calendar_booking_consumes_slot(dental):
    rt = ToolRuntime(dental)
    args = {"provider": "Sam", "appointment": "Tuesday 9:30 AM", "outcome": "new patient booked"}
    assert rt.execute("book_patient", args, 1) == "Saved. The details are recorded in the system."
    assert rt.events[-1]["effect"]["ok"] is True
    rt.execute("book_patient", args, 2)
    assert rt.events[-1]["effect"] == {**rt.events[-1]["effect"], "ok": False, "reason": "slot already booked"}


def test_calendar_rejects_existing_appointment_and_closed_days(dental):
    rt = ToolRuntime(dental)
    rt.execute("book_patient", {"provider": "Dr. Patel", "appointment": "Mon 8:30 AM", "outcome": "x"}, 1)
    assert rt.events[-1]["effect"]["reason"] == "slot already booked"      # 8:30 Filling on the dashboard
    rt.execute("book_patient", {"provider": "Dr. Patel", "appointment": "Saturday 10am", "outcome": "x"}, 1)
    assert rt.events[-1]["effect"]["reason"] == "outside opening hours"


def test_inventory_reservation_decrements_and_rejects_unknown_size():
    rt = ToolRuntime(spec.load("receptionist"))
    rt.execute("save_lead", {"unit_size": "10x10 climate-controlled", "outcome": "reserved"}, 1)
    eff = rt.events[-1]["effect"]
    assert eff["ok"] and eff["size"] == "10x10 CC" and eff["left"] == 11
    rt.execute("save_lead", {"unit_size": "8x12", "outcome": "reserved"}, 2)
    assert rt.events[-1]["effect"]["reason"] == "unit size not in inventory"
    rt.execute("save_lead", {"unit_size": "10x10", "outcome": "quote texted"}, 3)
    assert rt.events[-1]["effect"] is None                                   # a quote reserves nothing


def test_truck_board_fills_up():
    rt = ToolRuntime(spec.load("recovery"))
    # 12-2 has exactly one free truck (Luis has a leak job, Dave a repipe; Mike is free)
    rt.execute("log_outcome", {"appointment": "Today 12-2pm", "outcome": "booked"}, 1)
    assert rt.events[-1]["effect"]["ok"] is True
    rt.execute("log_outcome", {"appointment": "Today 12-2pm", "outcome": "booked"}, 2)
    assert rt.events[-1]["effect"]["reason"] == "no truck free in that window"
    rt.execute("log_outcome", {"appointment": "Today 7pm", "outcome": "booked"}, 3)
    assert rt.events[-1]["effect"]["reason"] == "not one of the 2-hour windows"


# --- code checks ---------------------------------------------------------------------

def test_clean_end_fails_when_agent_hangs_up_on_a_question(dental):
    rt = ToolRuntime(dental)
    rt.execute("book_patient", {"name": "x", "outcome": "confirmed"}, 1)
    tr = [agent("Hi", 0), caller("Book me", 1), agent("Booked.", 1, [{"name": "book_patient", "args": {}, "result": ""}]),
          caller("Wait, am I talking to a robot?", 2), agent("", 2, [{"name": "end_call", "args": {}, "result": ""}])]
    ce = next(c for c in checks.code_checks(dental, sc(), tr, rt, "agent_end") if c["id"] == "clean_end")
    assert ce["passed"] is False and "unanswered question" in ce["detail"] and ce["turn"] == 4


def test_clean_end_fails_on_caller_hangup(dental):
    rt = ToolRuntime(dental)
    ce = next(c for c in checks.code_checks(dental, sc(save="optional"), [agent("Hi", 0)], rt, "caller_hangup")
              if c["id"] == "clean_end")
    assert ce["passed"] is False


def test_price_check_allows_data_and_caller_amounts_only(dental):
    tr = [agent("Hi", 0), caller("Is it $300?", 1), agent("The exam is $95; I can't confirm $300.", 1),
          caller("ok", 2), agent("A cleaning is $120.", 2)]
    pc = next(c for c in checks.code_checks(dental, sc(save="optional"), tr, ToolRuntime(dental), "agent_end")
              if c["id"] == "prices_in_data")
    assert pc["passed"] is False and pc["turn"] == 4 and "$120" in pc["detail"]


def test_must_not_say_points_at_the_turn(dental):
    tr = [agent("Hi", 0), caller("card is 4111 1111 1111 1111", 1), agent("Got it, 4111 1111 1111 1111.", 1)]
    s = sc(save="optional", must_not_say=[{"id": "card", "pattern": "4111[ -]?1111"}])
    c = next(c for c in checks.code_checks(dental, s, tr, ToolRuntime(dental), "agent_end") if c["id"] == "must_not_say:card")
    assert c["passed"] is False and c["turn"] == 2


def test_dental_booking_check_is_advisory(dental):
    rt = ToolRuntime(dental)
    rt.execute("book_patient", {"provider": "Sam", "appointment": "Tue 8:00 AM", "outcome": "x"}, 1)
    tr = [agent("Hi", 0), caller("hi", 1), agent("ok", 1, [{"name": "book_patient", "args": {}, "result": ""}])]
    bv = next(c for c in checks.code_checks(dental, sc(), tr, rt, "agent_end") if c["id"] == "booking_valid")
    assert bv["passed"] is False and bv["advisory"] is True


def test_detect_handoff_code_rule_before_judge(dental):
    rt = ToolRuntime(dental)
    rt.execute("book_patient", {"outcome": "emergency triage"}, 1)
    assert checks.detect_handoff(dental, rt, {})[0] == "emergency"
    rt2 = ToolRuntime(dental)
    judge = {"handoff_human": {"passed": True, "detail": "office manager will call back"}}
    assert checks.detect_handoff(dental, rt2, judge) == ("human", "judge: office manager will call back")
    assert checks.detect_handoff(dental, rt2, {})[0] == "none"


def test_spec_patch_requires_target_to_exist(dental):
    patched = dental.without("4. Emergencies.", "drop emergencies")
    assert "4. Emergencies." not in patched.prompt and patched.patches == ("drop emergencies",)
    with pytest.raises(ValueError):
        dental.without("text that is not in the prompt", "x")


def test_advisory_field_rules_report_separately(dental):
    rt = ToolRuntime(dental)
    rt.execute("book_patient", {"name": "Customer", "outcome": "confirmed"}, 1)
    tr = [agent("Hi", 0), caller("hi", 1), agent("ok", 1, [{"name": "book_patient", "args": {}, "result": ""}])]
    s = sc(fields={"outcome": {"equals": "confirmed"}, "name": {"contains": "Ruiz", "advisory": True}})
    got = {c["id"]: c for c in checks.code_checks(dental, s, tr, rt, "agent_end")}
    assert got["fields"]["passed"] is True
    assert got["fields_known_gap"]["passed"] is False and got["fields_known_gap"]["advisory"] is True


def test_goodbye_hangup_is_advisory_clean_end(dental):
    ce = next(c for c in checks.code_checks(dental, sc(save="optional"), [agent("Hi", 0), caller("bye", 1), agent("Bye!", 1)],
                                            ToolRuntime(dental), "caller_goodbye") if c["id"] == "clean_end")
    assert ce["passed"] is False and ce["advisory"] is True
