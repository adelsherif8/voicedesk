"""SQLite storage for captured voice-agent records (leads, calls, bookings)."""

import os
import json
import sqlite3
import time
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("VOICEDESK_DB", os.path.join(_HERE, "data", "voicedesk.db"))


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT, name TEXT, phone TEXT, email TEXT,
            intent TEXT, outcome TEXT, appointment TEXT,
            summary TEXT, transcript TEXT, created REAL )""")
    if count() == 0:
        _seed()


def add(rec: dict) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO records (agent,name,phone,email,intent,outcome,appointment,summary,transcript,created)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rec.get("agent", "receptionist"), rec.get("name", ""), rec.get("phone", ""),
             rec.get("email", ""), rec.get("intent", ""), rec.get("outcome", "captured"),
             rec.get("appointment", ""), rec.get("summary", ""), rec.get("transcript", ""),
             rec.get("created", time.time())))
        return cur.lastrowid


def list_records(agent: str | None = None, limit: int = 200) -> list[dict]:
    q = "SELECT * FROM records"
    args = []
    if agent and agent != "all":
        q += " WHERE agent = ?"; args.append(agent)
    q += " ORDER BY created DESC LIMIT ?"; args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def count(agent: str | None = None) -> int:
    with _conn() as c:
        if agent and agent != "all":
            return c.execute("SELECT COUNT(*) FROM records WHERE agent=?", (agent,)).fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM records").fetchone()[0]


def stats() -> dict:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        booked = c.execute("SELECT COUNT(*) FROM records WHERE outcome='booked'").fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM records WHERE created > ?",
                          (time.time() - 86400,)).fetchone()[0]
        per = {r["agent"]: r["n"] for r in c.execute(
            "SELECT agent, COUNT(*) n FROM records GROUP BY agent").fetchall()}
    return {"total": total, "booked": booked, "today": today, "per_agent": per}


def _seed():
    now = time.time()
    demo = [
        ("receptionist", "Sarah Johnson", "+1 555 123 4567", "sarah@mail.com", "new patient",
         "booked", "Mon Jul 21, 2:00 PM", "New patient, teeth cleaning. Booked afternoon slot.", "", now - 1800),
        ("receptionist", "Mark Reyes", "+1 555 887 2210", "", "existing patient",
         "transferred", "", "Existing patient asking about a bill — warm-transferred to front desk.", "", now - 5400),
        ("sales", "Daniel Okoro", "+1 555 662 9931", "d.okoro@acme.co", "enterprise inquiry",
         "qualified", "", "200-seat team, wants pricing + SSO. Hot lead, flagged for closer.", "", now - 3600),
        ("sales", "Lisa Grant", "+1 555 220 1187", "", "not interested",
         "disqualified", "", "Not a fit — no budget this quarter. Marked disqualified.", "", now - 9000),
        ("booking", "Omar Haddad", "+1 555 771 4432", "omar@mail.com", "reschedule",
         "booked", "Wed Jul 23, 11:30 AM", "Moved appointment from Thursday to Wednesday morning.", "", now - 7200),
        ("faq", "Grace Kim", "+1 555 909 3311", "", "question: refund policy",
         "answered", "", "Asked about the refund window; answered from KB (30-day money-back).", "", now - 2400),
        ("restaurant", "Ben Carter", "+1 555 818 2020", "", "takeout order",
         "order placed", "Pickup 7:15 PM", "2x margherita, 1x caesar, 1x tiramisu. Total $48.50.", "", now - 1200),
        ("reactivation", "Hannah Weiss", "+1 555 656 1200", "hannah@lumen.io", "cold lead re-engaged",
         "booked", "Fri Jul 25, 4:00 PM", "Enquired 3 months ago, never followed up. Re-booked a consult.", "", now - 600),
    ]
    with _conn() as c:
        for (agent, name, phone, email, intent, outcome, appt, summary, transcript, created) in demo:
            c.execute(
                """INSERT INTO records (agent,name,phone,email,intent,outcome,appointment,summary,transcript,created)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (agent, name, phone, email, intent, outcome, appt, summary, transcript, created))
