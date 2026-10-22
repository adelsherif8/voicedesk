"""The metric definitions, pinned down. These are what the README and /evals page promise."""

import pytest

from evals.metrics import scenario_status, score_call, summarize


def chk(id, passed=True, advisory=False, kind="code"):
    return {"id": id, "kind": kind, "passed": passed, "advisory": advisory, "detail": "", "turn": None}


GOOD = [chk("save_called"), chk("fields"), chk("prices_in_data"), chk("clean_end"),
        chk("handoff"), chk("grounded", kind="judge"), chk("answered", kind="judge")]


def call(agent="a", scenario="s", checks=GOOD, handoff="none", expected="none", end="agent_end", error=None, **extra):
    return {"agent": agent, "scenario": scenario, "cost_usd": 0.01,
            **score_call(checks, handoff, expected, end, error), **extra}


# --- containment -------------------------------------------------------------

def test_completed_call_ended_by_agent_is_contained():
    assert call()["contained"] is True


def test_hangup_is_never_contained_even_when_everything_was_captured():
    # the goal checks all passed, but the caller hung up instead of the agent closing the call
    r = call(end="caller_hangup")
    assert r["goal_met"] is True
    assert r["contained"] is False


def test_abandoned_call_is_not_contained():
    assert call(end="max_turns")["contained"] is False


def test_transferred_call_is_not_contained_even_if_goal_met():
    assert call(handoff="human", expected="human")["contained"] is False


def test_call_expected_to_escalate_is_not_contained():
    assert call(handoff="none", expected="emergency")["contained"] is False


def test_goal_not_met_is_not_contained():
    checks = [c if c["id"] != "fields" else chk("fields", False) for c in GOOD]
    assert call(checks=checks)["contained"] is False


def test_errored_call_is_not_contained_and_not_passed():
    r = call(end="error", error="Timeout")
    assert r["contained"] is False and r["passed"] is False


def test_advisory_failure_does_not_block_pass_or_containment():
    r = call(checks=GOOD + [chk("booking_valid", False, advisory=True)])
    assert r["passed"] and r["contained"] and not r["hallucinated"]


# --- handoffs ------------------------------------------------------------------

def test_missed_handoff_is_flagged_and_fails_the_call():
    r = call(handoff="none", expected="emergency")
    assert r["missed_handoff"] is True and r["passed"] is False


def test_unnecessary_handoff_is_flagged_and_fails_the_call():
    r = call(handoff="human", expected="none")
    assert r["unnecessary_handoff"] is True and r["transferred"] is True and r["passed"] is False


def test_correct_handoff_passes():
    r = call(handoff="emergency", expected="emergency")
    assert r["transferred"] and not r["missed_handoff"] and not r["unnecessary_handoff"] and r["passed"]


def test_wrong_kind_of_handoff_fails_but_is_not_missed():
    r = call(handoff="emergency", expected="safety")
    assert r["passed"] is False and r["missed_handoff"] is False


# --- task success / hallucination ------------------------------------------------

def test_task_success_is_none_when_no_fields_expected():
    assert call(checks=[c for c in GOOD if c["id"] != "fields"])["task_success"] is None


def test_hallucination_from_price_check():
    checks = [c if c["id"] != "prices_in_data" else chk("prices_in_data", False) for c in GOOD]
    assert call(checks=checks)["hallucinated"] is True


def test_hallucination_from_judge_grounding():
    checks = [c if c["id"] != "grounded" else chk("grounded", False, kind="judge") for c in GOOD]
    assert call(checks=checks)["hallucinated"] is True


def test_hallucination_from_strict_booking_check_only():
    assert call(checks=GOOD + [chk("booking_valid", False)])["hallucinated"] is True


def test_classify_items_never_fail_a_call():
    assert call(checks=GOOD + [chk("handoff_human", False, advisory=True, kind="classify")])["passed"]


# --- per-agent summary -------------------------------------------------------------

def test_rates_are_over_all_calls_including_hangups():
    rs = [call(scenario="ok"), call(scenario="ok"), call(scenario="gone", end="caller_hangup"),
          call(scenario="esc", handoff="emergency", expected="emergency")]
    m = summarize(rs)["a"]
    assert m["calls"] == 4
    assert m["containment_rate"] == pytest.approx(2 / 4)
    assert m["transfer_rate"] == pytest.approx(1 / 4)
    assert m["correct_transfers"] == 1 and m["unnecessary_transfers"] == 0


def test_missed_handoffs_counted_in_summary():
    m = summarize([call(handoff="none", expected="emergency"), call()])["a"]
    assert m["missed_handoffs"] == 1 and m["missed_handoff_rate"] == pytest.approx(0.5)


def test_pass_k_requires_all_k_attempts_and_reports_flaky():
    bad = [c if c["id"] != "fields" else chk("fields", False) for c in GOOD]
    rs = ([call(scenario="steady")] * 3 +
          [call(scenario="wobbly"), call(scenario="wobbly"), call(scenario="wobbly", checks=bad)] +
          [call(scenario="broken", checks=bad)] * 3)
    m = summarize(rs)["a"]
    assert m["scenarios"]["steady"]["status"] == "pass"
    assert m["scenarios"]["wobbly"]["status"] == "flaky"
    assert m["scenarios"]["broken"]["status"] == "fail"
    assert m["pass_k"] == pytest.approx(1 / 3)
    assert m["flaky"] == ["wobbly"] and m["failing"] == ["broken"]


def test_scenario_status():
    assert (scenario_status(3, 3), scenario_status(1, 3), scenario_status(0, 3)) == ("pass", "flaky", "fail")


def test_task_success_rate_ignores_calls_without_field_expectations():
    no_fields = [c for c in GOOD if c["id"] != "fields"]
    bad = [c if c["id"] != "fields" else chk("fields", False) for c in GOOD]
    m = summarize([call(), call(checks=bad), call(checks=no_fields)])["a"]
    assert m["task_success_rate"] == pytest.approx(1 / 2)


def test_empty_denominator_is_none_not_zero():
    m = summarize([call(checks=[c for c in GOOD if c["id"] != "fields"])])["a"]
    assert m["task_success_rate"] is None


# --- scenarios that accept more than one outcome ----------------------------------------

def test_acceptable_set_allows_either_outcome():
    assert call(handoff="none", expected="none|human")["passed"]
    assert call(handoff="human", expected="none|human")["passed"]
    assert call(handoff="none", expected=["none", "human"])["contained"] is True


def test_handoff_inside_acceptable_set_is_not_unnecessary_and_not_contained():
    r = call(handoff="human", expected="none|human")
    assert r["unnecessary_handoff"] is False and r["contained"] is False


def test_handoff_outside_acceptable_set_with_none_allowed_is_unnecessary():
    r = call(handoff="emergency", expected="none|human")
    assert r["unnecessary_handoff"] is True and r["passed"] is False


def test_wrong_kind_is_not_a_correct_transfer_in_summary():
    m = summarize([call(handoff="human", expected="safety"), call(handoff="safety", expected="safety")])["a"]
    assert m["correct_transfers"] == 1 and m["missed_handoffs"] == 0
