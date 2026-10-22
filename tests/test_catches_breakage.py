"""A suite that never fails proves nothing. Each case breaks one agent on purpose by
patching its prompt (and the matching tool description), runs the scenario that should
notice, and asserts the suite catches it on the targeted check while the unpatched agent
does not trip that same check.

Live: calls OpenAI (about $0.08 for all three). Run with:  pytest -m live
"""

import pytest

from evals import runner, scenario, spec

K = 3

DENTAL_EMERGENCY_RULE = ("4. Emergencies. Severe pain, swelling, knocked-out tooth, bleeding that won't\n"
                         "   stop -> same-day triage slot, and tell them to come in now.\n")
RECOVERY_FEE_RULE = ("- Never promise an exact price on the phone for work not yet quoted; give the\n"
                     "  $89 diagnostic call-out fee and say the tech quotes on site.\n")
STORAGE_PRICE_LIST = ('Live unit inventory and monthly prices:\n'
                      '- 5x5   "Small, about a closet"          $45/mo\n'
                      '- 10x10 "Medium, a one-bedroom apartment" $110/mo\n'
                      '- 10x20 "Large, a three-bedroom house"    $190/mo\n'
                      '- 10x10 climate-controlled                $145/mo\n')


def failed(r, cid, detail=""):
    return any(c["id"] == cid and not c["passed"] and detail in c["detail"] for c in r["checks"])


CASES = [
    pytest.param(
        "dental", "emergency-knocked-out-tooth",
        lambda s: s.without(DENTAL_EMERGENCY_RULE, "removed dental emergency rule")
                   .without_in_tool("outcome", "emergency triage, ", "removed 'emergency triage' outcome"),
        lambda r: r["missed_handoff"],
        id="dental-emergency-rule-removed"),
    # Recovery's emergency rule isn't used here: on gpt-4o-mini the unpatched agent already
    # misses the burst-pipe escalation (a real finding), so removing it shows no difference.
    pytest.param(
        "recovery", "in-data-running-toilet-price",
        lambda s: s.without(RECOVERY_FEE_RULE, "removed recovery $89 call-out fee rule"),
        lambda r: failed(r, "fee_not_quote"),
        id="recovery-fee-rule-removed"),
    pytest.param(
        "receptionist", "in-data-climate-price-quote-texted",
        lambda s: s.without(STORAGE_PRICE_LIST, "removed storage price list"),
        lambda r: failed(r, "fields", "price") or failed(r, "prices_in_data"),
        id="receptionist-price-list-removed"),
]


@pytest.mark.live
@pytest.mark.parametrize("agent,scenario_id,patch,caught", CASES)
def test_suite_catches_deliberate_breakage(agent, scenario_id, patch, caught):
    base = spec.load(agent)
    broken = patch(base)
    scs = scenario.load_all(agent, only=scenario_id)
    assert scs, f"scenario {scenario_id} not found"

    run = runner.run_suite([(base, scs)], K, "gpt-4o-mini", cap=0.30)
    run_broken = runner.run_suite([(broken, scs)], K, "gpt-4o-mini", cap=0.30)
    assert not run["aborted"] and not run_broken["aborted"]

    caught_broken = sum(bool(caught(r)) for r in run_broken["results"])
    caught_base = sum(bool(caught(r)) for r in run["results"])
    print(f"\n{agent}/{scenario_id}: targeted check tripped {caught_broken}/{K} patched vs {caught_base}/{K} unpatched; "
          f"scenario status patched={run_broken['summary'][agent]['scenarios'][scenario_id]['status']}")

    assert caught_broken >= K - 1, "the suite did not catch the deliberate breakage"
    assert caught_base == 0, "the unpatched agent already trips this check, so it can't show the breakage"
    assert run_broken["summary"][agent]["scenarios"][scenario_id]["status"] != "pass"
