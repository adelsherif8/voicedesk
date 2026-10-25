"""Regression gating rules (pure function, no I/O)."""

from evals.baseline import compare


def sc(status, passes, runs, contained=0, missed=0):
    return {"status": status, "passes": passes, "runs": runs, "contained": contained, "missed_handoffs": missed}


def base(**scenarios):
    return {"run_id": "b", "k": 3, "scenarios": scenarios}


def now(**scenarios):
    return {"scenarios": scenarios}


def test_pass_to_fail_is_a_regression():
    r = compare(base(a=sc("pass", 3, 3)), now(a=sc("fail", 0, 1)))
    assert len(r["regressions"]) == 1 and "a: passed 3/3" in r["regressions"][0]


def test_already_failing_scenario_failing_again_is_not_a_regression():
    assert compare(base(a=sc("fail", 0, 3)), now(a=sc("fail", 0, 3)))["regressions"] == []


def test_pass_to_flaky_is_a_warning_unless_strict():
    b, n = base(a=sc("pass", 3, 3)), now(a=sc("flaky", 2, 3))
    assert compare(b, n)["regressions"] == [] and any("now flaky" in w for w in compare(b, n)["warnings"])
    assert len(compare(b, n, strict=True)["regressions"]) == 1


def test_new_missed_handoff_is_critical_even_on_a_failing_scenario():
    r = compare(base(e=sc("fail", 0, 3, missed=0)), now(e=sc("fail", 0, 3, missed=2)))
    assert any("[critical]" in x for x in r["regressions"])


def test_containment_drop_over_threshold_is_a_regression_with_enough_calls():
    b = base(**{f"s{i}": sc("pass", 3, 3, contained=3) for i in range(4)})     # 12/12 contained
    n = now(**{f"s{i}": sc("pass", 3, 3, contained=2) for i in range(4)})      # 8/12
    r = compare(b, n, threshold=0.10)
    assert any("containment dropped" in x for x in r["regressions"])
    assert compare(b, n, threshold=0.50)["regressions"] == []


def test_containment_not_gated_on_small_samples():
    r = compare(base(a=sc("pass", 3, 3, contained=3)), now(a=sc("pass", 1, 1, contained=0)))
    assert r["regressions"] == [] and any("not gated" in w for w in r["warnings"])


def test_only_shared_scenarios_compared_and_new_ones_listed():
    r = compare(base(a=sc("pass", 3, 3), gone=sc("pass", 3, 3)), now(a=sc("pass", 1, 1), extra=sc("fail", 0, 1)))
    assert r["shared"] == 1 and r["new"] == ["extra"] and r["regressions"] == []


def test_improvement_reported():
    assert compare(base(a=sc("fail", 0, 3)), now(a=sc("pass", 3, 3)))["improvements"]


def test_partial_save_keeps_the_full_baseline_run(tmp_path, monkeypatch):
    from evals import baseline, config
    monkeypatch.setattr(config, "BASELINES_DIR", tmp_path)
    def run(rid, scen, selection):
        return {"id": rid, "agent_model": "m", "k": 3, "git_sha": "x", "selection": selection,
                "summary": {"a": {"scenarios": {s: sc("pass", 3, 3) for s in scen}}}}
    baseline.save(run("full", ["s1", "s2"], {}))
    baseline.save(run("part", ["s2"], {"scenario": "s2"}))
    d = baseline.load("a", "m")
    assert d["run_id"] == "full" and d["updates"] == ["part"] and set(d["scenarios"]) == {"s1", "s2"}


def test_security_critical_is_always_a_regression_even_for_a_new_scenario():
    n = now(a={**sc("pass", 3, 3), "criticals": 0}, newsec={**sc("fail", 0, 3), "criticals": 1})
    r = compare(base(a=sc("pass", 3, 3)), n)
    assert any("newsec: security critical" in x and "[critical]" in x for x in r["regressions"])
    clean = compare(base(a=sc("pass", 3, 3)), now(a={**sc("pass", 3, 3), "criticals": 0}))
    assert clean["regressions"] == []


def test_baseline_save_leaves_out_security_critical_scenarios(tmp_path, monkeypatch):
    from evals import baseline, config
    monkeypatch.setattr(config, "BASELINES_DIR", tmp_path)
    run = {"id": "r", "agent_model": "m", "k": 3, "git_sha": "x", "selection": {},
           "summary": {"a": {"scenarios": {"ok": {**sc("pass", 3, 3), "criticals": 0},
                                           "leaky": {**sc("fail", 0, 3), "criticals": 2}}}}}
    baseline.save(run)
    d = baseline.load("a", "m")
    assert set(d["scenarios"]) == {"ok"} and d["excluded_security_critical"] == ["leaky"]
