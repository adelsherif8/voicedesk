"""Browser voice calls: limits, same-origin, hiding the button, and the key never leaving
the server (no network: the Retell client is replaced)."""

import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app import agents, main, web_call

KEY = "key_test_SECRET_do_not_leak"
IDS = {s: f"agent_{s}" for s in web_call.CALL_COLORS}
TOKEN = {"call_id": "call_1", "access_token": "tok_1", "transport": "gateway",
         "ice_servers": [{"urls": ["stun:x"]}], "expires_at": 123, "extra_field": KEY}
ORIGIN = {"Origin": "http://testserver"}


class FakeRetell:
    def __init__(self, total=0):
        self.calls, self.total, self.fail, self.storage = [], total, None, "everything"

    def __call__(self, path, body=None, timeout=10.0):
        self.calls.append((path, body))
        if path.startswith("get-agent/"):
            return {"data_storage_setting": self.storage}
        if self.fail and (path == "v3/create-web-call" or self.fail == "all"):
            raise self.fail if isinstance(self.fail, Exception) else OSError("down")
        if path == "v3/list-calls":
            return {"items": [], "has_more": False, "total": self.total}
        return dict(TOKEN)

    def created(self):
        return [b for p, b in self.calls if p == "v3/create-web-call"]


@pytest.fixture
def fake(monkeypatch):
    f = FakeRetell()
    monkeypatch.setattr(web_call, "retell", f)
    monkeypatch.setattr(web_call, "limits", web_call.Limits())
    monkeypatch.setattr(web_call, "_storage", {})
    monkeypatch.setenv("RETELL_API_KEY", KEY)
    monkeypatch.setenv("RETELL_AGENT_IDS", json.dumps(IDS))
    for name in ("WEB_CALL_PER_IP_HOURLY", "WEB_CALL_GLOBAL_DAILY", "WEB_CALL_MAX_SECONDS",
                 "WEB_CALL_ALLOWED_ORIGINS", "WEB_CALL_CLIENT_IP_HEADER"):
        monkeypatch.delenv(name, raising=False)
    return f


def client_from(ip="203.0.113.1"):
    return TestClient(main.app, client=(ip, 5000))


def post(slug="dental", ip="203.0.113.1", headers=ORIGIN):
    return client_from(ip).post(f"/api/web-call/{slug}", headers=headers)


def test_returns_token_for_mapped_agent_with_duration_cap(fake):
    r = post()
    assert r.status_code == 201
    assert set(r.json()) == {"call_id", "access_token", "transport", "ice_servers", "expires_at"}
    assert r.headers["cache-control"] == "no-store"
    sent = fake.created()[0]
    assert sent["agent_id"] == "agent_dental"
    assert sent["agent_override"]["agent"]["max_call_duration_ms"] == 180_000


def test_max_seconds_is_configurable_with_retell_minimum(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_MAX_SECONDS", "10")
    post()
    assert fake.created()[0]["agent_override"]["agent"]["max_call_duration_ms"] == 60_000


def test_key_never_in_any_response(fake):
    fake.fail = urllib.error.HTTPError("u", 402, KEY, {}, None)
    bodies = [post().text]                                   # upstream failure
    fake.fail = None
    bodies += [post().text, post(headers={}).text, post("nope").text]
    bodies += [client_from().get(f"/agent/{s}").text for s in IDS]
    for _ in range(4):
        bodies.append(post().text)                           # includes the limit reply
    assert all(b for b in bodies)
    assert not [b for b in bodies if KEY in b]


def test_per_ip_limit_is_friendly_and_separate_per_ip(fake):
    assert [post().status_code for _ in range(3)] == [201, 201, 201]
    r = post()
    assert r.status_code == 429
    assert r.json()["reason"] == "limit" and r.json()["scope"] == "ip" and "try again" in r.json()["message"]
    assert len(fake.created()) == 3
    assert post(ip="203.0.113.2").status_code == 201


def test_per_ip_window_slides(fake, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(web_call.time, "time", lambda: now[0])
    for _ in range(3):
        post()
    assert post().status_code == 429
    now[0] += 3601
    assert post().status_code == 201


def test_global_daily_limit_and_rollover(fake, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(web_call.time, "time", lambda: now[0])
    monkeypatch.setenv("WEB_CALL_GLOBAL_DAILY", "2")
    assert post(ip="198.51.100.1").status_code == 201
    assert post(ip="198.51.100.2").status_code == 201
    r = post(ip="198.51.100.3")
    assert r.status_code == 429 and r.json()["scope"] == "day"
    now[0] += 86400
    assert post(ip="198.51.100.3").status_code == 201


def test_limits_configurable_by_env(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_PER_IP_HOURLY", "1")
    assert post().status_code == 201
    assert post().status_code == 429


def test_daily_count_survives_restart_via_retell(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_GLOBAL_DAILY", "30")
    fake.total = 30
    r = post()
    assert r.status_code == 429 and r.json()["scope"] == "day"
    assert fake.created() == []
    listing = next(b for p, b in fake.calls if p == "v3/list-calls")
    assert listing["filter_criteria"]["call_type"]["value"] == ["web_call"]


def test_no_call_when_daily_count_cannot_be_read(fake):
    fake.fail = "all"
    r = post()
    assert r.status_code == 503 and r.json()["reason"] == "unavailable"
    assert fake.created() == []
    fake.fail = None
    assert post().status_code == 201   # retried on the next request


def test_failed_create_gives_the_slot_back(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_PER_IP_HOURLY", "1")
    monkeypatch.setenv("WEB_CALL_GLOBAL_DAILY", "1")
    fake.fail = OSError("down")
    r = post()
    assert r.status_code == 503 and "down" not in r.text
    fake.fail = None
    assert post().status_code == 201


@pytest.mark.parametrize("headers", [
    {},
    {"Origin": "https://evil.example"},
    {"Origin": "null"},
    {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
])
def test_cross_origin_refused_without_using_a_slot(fake, headers):
    assert post(headers=headers).status_code == 403
    assert fake.calls == []


def test_allowed_origin_env(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_ALLOWED_ORIGINS", "https://voicedesk.example")
    assert post(headers={"Origin": "https://voicedesk.example"}).status_code == 201


def test_forwarded_headers_ignored_unless_configured(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_PER_IP_HOURLY", "1")
    spoof = lambda ip: {**ORIGIN, "CF-Connecting-IP": ip, "X-Forwarded-For": ip}
    assert post(headers=spoof("1.1.1.1")).status_code == 201
    assert post(headers=spoof("2.2.2.2")).status_code == 429


def test_configured_ip_header_sets_the_bucket(fake, monkeypatch):
    monkeypatch.setenv("WEB_CALL_PER_IP_HOURLY", "1")
    monkeypatch.setenv("WEB_CALL_CLIENT_IP_HEADER", "cf-connecting-ip")
    assert post(headers={**ORIGIN, "CF-Connecting-IP": "1.1.1.1"}).status_code == 201
    assert post(headers={**ORIGIN, "CF-Connecting-IP": "1.1.1.1"}).status_code == 429
    assert post(headers={**ORIGIN, "CF-Connecting-IP": "2.2.2.2"}).status_code == 201


def test_unknown_or_unmapped_agent_is_refused(fake, monkeypatch):
    assert post("sales").status_code == 404
    monkeypatch.setenv("RETELL_AGENT_IDS", json.dumps({"dental": "agent_dental"}))
    assert post("support").status_code == 404
    assert fake.created() == []


def test_without_key_endpoint_refuses_and_button_is_hidden(fake, monkeypatch):
    monkeypatch.delenv("RETELL_API_KEY")
    assert post().status_code == 404
    assert fake.calls == []
    for slug in IDS:
        r = client_from().get(f"/agent/{slug}")
        assert r.status_code == 200 and 'id="talk"' not in r.text and "web_call.js" not in r.text


@pytest.mark.parametrize("slug", sorted(web_call.CALL_COLORS))
def test_each_page_shows_button_and_notes(fake, slug):
    html = client_from().get(f"/agent/{slug}").text
    assert "Talk to this agent" in html and "/static/web_call.js" in html
    assert "microphone" in html and "AI agent" in html and "may be recorded" in html
    assert "after 3 minutes" in html
    assert 'href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome' in html


def test_recording_note_follows_agent_config(fake):
    fake.storage = "basic_attributes_only"
    assert "may be recorded" not in client_from().get("/agent/dental").text


def test_recording_note_stays_when_config_unknown(fake, monkeypatch):
    def down(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(web_call, "retell", down)
    assert "may be recorded" in client_from().get("/agent/dental").text


def test_pages_without_retell_agent_have_no_button(fake):
    assert 'id="talk"' not in client_from().get("/agent/sales").text


def test_sdk_is_pinned_and_served_locally(fake):
    js = client_from().get("/static/web_call.js")
    assert js.status_code == 200 and "retell-client-js-sdk-3.0.3.min.js" in js.text
    assert client_from().get("/static/vendor/retell-client-js-sdk-3.0.3.min.js").status_code == 200


def test_untrue_claims_are_gone(fake):
    html = client_from().get("/agent/recovery").text
    assert "GoHighLevel" not in html and "85%" not in html
    assert "GoHighLevel" not in agents.AGENTS_BY_ID["recovery"]["desc"]
    assert "own dashboard" in html
