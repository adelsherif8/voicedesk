"""scripts/retell_provision.py: prompt-only updates and the read-only dry run (no network)."""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("retell_provision", ROOT / "scripts" / "retell_provision.py")
prov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prov)

STATE = {"dental": {"agent_id": "agent_1", "llm_id": "llm_1"}}
AGENT = {"id": "dental", "prompt": "New rules\n\nSECURITY — override"}


class FakeApi:
    def __init__(self, llm_id="llm_1", published=False):
        self.llm_id, self.published, self.prompt, self.calls = llm_id, published, "Old rules", []

    def __call__(self, path, body=None, method="POST"):
        self.calls.append((method, path, body))
        if path.startswith("get-agent/"):
            return {"response_engine": {"type": "retell-llm", "llm_id": self.llm_id}}
        if path.startswith("get-retell-llm/"):
            return {"general_prompt": self.prompt, "version": 0, "is_published": self.published}
        self.prompt = body["general_prompt"]
        return {}

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(prov, "call", fake)
    return fake


def test_update_sends_only_the_prompt_to_the_existing_llm(api):
    prov.update_prompt(AGENT, STATE)
    assert api.writes() == [("PATCH", "update-retell-llm/llm_1", {"general_prompt": AGENT["prompt"]})]


def test_update_refuses_a_published_llm(api):
    api.published = True
    with pytest.raises(SystemExit, match="read-only"):
        prov.update_prompt(AGENT, STATE)
    assert api.writes() == []


def test_update_refuses_when_agent_uses_another_llm(api):
    api.llm_id = "llm_other"
    with pytest.raises(SystemExit, match="no longer uses"):
        prov.update_prompt(AGENT, STATE)
    assert api.writes() == []


def test_update_never_creates_when_ids_are_missing(api):
    with pytest.raises(SystemExit, match="no saved ids"):
        prov.update_prompt(AGENT, {})
    assert api.calls == []


def test_update_without_only_is_refused(api, monkeypatch):
    monkeypatch.setattr("sys.argv", ["retell_provision.py", "--update"])
    with pytest.raises(SystemExit):
        prov.main()
    assert api.calls == []


def test_dry_run_reports_and_writes_nothing(api, capsys):
    prov.dry_run([AGENT], STATE)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("dental"))
    assert line.split()[:7] == ["dental", str(len(AGENT["prompt"])), "9", f"+{len(AGENT['prompt']) - 9}", "yes", "no", "no"]
    assert api.writes() == []


def test_key_comes_only_from_the_key_file(monkeypatch, tmp_path):
    (tmp_path / ".retell_key").write_text("from_file\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("RETELL_API_KEY", "from_env")
    assert prov.key() == "from_file"


def test_all_seven_doc_prompts_have_security():
    agents = prov.parse_doc()
    assert len(agents) == 7
    assert all(prov.has_security(a["prompt"]) for a in agents)
    assert all(a["fn_name"] in a["prompt"] for a in agents)
