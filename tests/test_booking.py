"""Live booking and handoff for the plumbing agent: the truck board, the availability check and replay."""

from datetime import datetime

import pytest

from app import db, main, scheduling, web_call
from tests.test_admin import client, retell_post  # noqa: F401  (fixture + signed webhook helper)

# Monday 2 Nov 2026, 9:00 in New York. Today's seed board leaves 12-2pm with one truck free,
# 2-4pm and 4-6pm with all three, and 10am-12pm full; 8-10am has already started.
NINE_AM = datetime(2026, 11, 2, 9, 0, tzinfo=scheduling.TZ).timestamp()


def book(window, day="today", name="Dana", ts=NINE_AM):
    return main.handle_tool("recovery", "book_appointment",
                            {"name": name, "intent": "Leak under sink", "day": day, "window": window}, created=ts)


def test_only_windows_with_a_free_truck_that_have_not_started_are_offered(client):
    assert scheduling.open_windows("recovery", "today", NINE_AM) == ["12-2pm", "2-4pm", "4-6pm"]
    assert scheduling.open_windows("recovery", "tomorrow", NINE_AM) == scheduling.WINDOWS
    text = main.handle_tool("recovery", "check_availability", {}, created=NINE_AM)
    assert "Today: 12-2pm, 2-4pm, 4-6pm." in text and "10am-12pm" not in text.split("Tomorrow")[0]


def test_a_booking_takes_the_slot_and_a_second_one_is_refused(client):
    before = db.count("recovery")
    assert book("12-2pm").startswith("Booked: today 12-2pm")
    refused = book("12-2pm", name="Lee")
    assert refused.startswith("Not booked: today 12-2pm is no longer free") and "2-4pm" in refused
    assert db.count("recovery") == before + 1
    row = next(r for r in db.list_records("recovery") if r["name"] == "Dana")
    assert row["outcome"] == "booked" and row["appointment"] == "Mon Nov 2, 12-2pm"
    assert row["meta"]["date"] == "2026-11-02" and row["meta"]["window"] == "12-2pm"
    slot = scheduling.board("recovery", "2026-11-02", NINE_AM)[0]["slots"][2]
    assert slot == {"ai": True, "name": "Dana", "job": "Leak under sink"}


@pytest.mark.parametrize("args", [{"day": "friday", "window": "2-4pm"}, {"day": "today", "window": "3pm"},
                                  {"day": "today", "window": "8-10am"}, {}])
def test_bad_or_past_windows_are_never_booked(client, args):
    before = db.count("recovery")
    assert main.handle_tool("recovery", "book_appointment", {"name": "X", **args}, created=NINE_AM).startswith("Not booked")
    assert db.count("recovery") == before


def test_three_trucks_means_three_bookings_per_open_window(client):
    for n in ("A", "B", "C"):
        assert book("2-4pm", day="tomorrow", name=n).startswith("Booked")
    assert book("2-4pm", day="tomorrow", name="D").startswith("Not booked")


def test_the_webhook_books_and_a_browser_transfer_becomes_a_callback(client):
    ok = retell_post(client, "/retell/recovery", {"name": "book_appointment", "call": {"call_id": "c1"},
                                                  "args": {"name": "Ana", "intent": "Burst pipe", "day": "tomorrow", "window": "8-10am"}})
    assert ok.json()["result"].startswith("Booked: tomorrow 8-10am")
    r = retell_post(client, "/retell/recovery", {"name": "transfer_to_human", "call": {"call_id": "c2", "call_type": "web_call"},
                                                 "args": {"name": "Ana", "intent": "Wants the owner"}})
    assert "call them back within 10 minutes" in r.json()["result"]
    row = next(x for x in db.list_records("recovery") if (x["meta"] or {}).get("_call") == "c2")
    assert row["outcome"] == "transfer requested"
    board = client.get("/api/board/recovery").json()
    assert set(board) == {"today", "tomorrow"} and len(board["tomorrow"]["trucks"]) == 3
    assert client.get("/api/board/dental").status_code == 404


def test_replay_rebuilds_bookings_oldest_first_with_the_same_checks(client, monkeypatch):
    monkeypatch.setattr(web_call, "agent_ids", lambda: {"recovery": "agent_x"})
    start = int(NINE_AM * 1000)
    calls = {f"call_{i}": {"start_timestamp": start + i * 60_000, "call_type": "web_call", "transcript_with_tool_calls": [
        {"role": "tool_call_invocation", "name": "book_appointment", "time_sec": 20,
         "arguments": f'{{"name":"P{i}","intent":"Leak","day":"today","window":"12-2pm"}}'}]} for i in (1, 2)}
    # Retell lists newest first: the replay must still give the slot to the earlier caller
    listing = {"items": [{"call_id": c, "tool_calls": [{"name": "book_appointment"}]} for c in ("call_2", "call_1")]}
    monkeypatch.setattr(web_call, "retell", lambda path, body=None, timeout=10.0:
                        listing if "list-calls" in path else calls[path.rsplit("/", 1)[1]])
    assert main.replay_from_retell() == 1
    booked = [r["name"] for r in db.list_records("recovery") if (r["meta"] or {}).get("window") == "12-2pm"]
    assert booked == ["P1"]
