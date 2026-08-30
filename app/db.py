"""SQLite storage for captured voice-agent records (leads, calls, bookings).
`meta` holds use-case-specific structured fields (e.g. storage unit_size/price)."""

import os
import json
import sqlite3
import time

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
            summary TEXT, transcript TEXT, meta TEXT, created REAL )""")
        try:
            c.execute("ALTER TABLE records ADD COLUMN meta TEXT")
        except sqlite3.OperationalError:
            pass
    if count() == 0:
        _seed()


def reset():
    with _conn() as c:
        c.execute("DELETE FROM records")
    _seed()


def add(rec: dict) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO records (agent,name,phone,email,intent,outcome,appointment,summary,transcript,meta,created)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (rec.get("agent", "receptionist"), rec.get("name", ""), rec.get("phone", ""),
             rec.get("email", ""), rec.get("intent", ""), rec.get("outcome", "captured"),
             rec.get("appointment", ""), rec.get("summary", ""), rec.get("transcript", ""),
             json.dumps(rec.get("meta") or {}), rec.get("created", time.time())))
        return cur.lastrowid


def _row(r) -> dict:
    d = dict(r)
    try:
        d["meta"] = json.loads(d.get("meta") or "{}")
    except Exception:
        d["meta"] = {}
    return d


def list_records(agent: str | None = None, limit: int = 200) -> list[dict]:
    q, args = "SELECT * FROM records", []
    if agent and agent != "all":
        q += " WHERE agent = ?"; args.append(agent)
    q += " ORDER BY created DESC LIMIT ?"; args.append(limit)
    with _conn() as c:
        return [_row(r) for r in c.execute(q, args).fetchall()]


def count(agent: str | None = None) -> int:
    with _conn() as c:
        if agent and agent != "all":
            return c.execute("SELECT COUNT(*) FROM records WHERE agent=?", (agent,)).fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM records").fetchone()[0]


def stats(agent: str | None = None) -> dict:
    with _conn() as c:
        where = " WHERE agent=?" if (agent and agent != "all") else ""
        a = (agent,) if where else ()
        total = c.execute("SELECT COUNT(*) FROM records" + where, a).fetchone()[0]
        booked = c.execute("SELECT COUNT(*) FROM records" + (where + " AND" if where else " WHERE") +
                           " (outcome LIKE '%book%' OR outcome LIKE '%reserv%' OR outcome LIKE '%order%' OR outcome LIKE '%qualif%')", a).fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM records" + (where + " AND" if where else " WHERE") +
                          " created > ?", a + (time.time() - 86400,)).fetchone()[0]
        per = {r["agent"]: r["n"] for r in c.execute(
            "SELECT agent, COUNT(*) n FROM records GROUP BY agent").fetchall()}
    return {"total": total, "booked": booked, "today": today, "per_agent": per}


def _seed():
    now = time.time()
    demo = [
        ("receptionist", "Sarah Johnson", "+1 555 123 4567", "sarah@mail.com", "Rent a storage unit",
         "Reserved 10x10", "Tour Mon Jul 21, 2:00 PM", "Moving apartments — boxes and furniture. Reserved a 10x10 and booked a tour.",
         {"call_type": "rental", "unit_size": "10x10", "move_in": "Monday", "monthly_price": 110}, now - 1500),
        ("receptionist", "Priya Nair", "+1 555 301 7745", "", "Pay monthly bill",
         "Payment collected", "", "Existing tenant, unit B-14. Paid $110 by card over the phone; enrolled in autopay.",
         {"call_type": "payment", "unit": "B-14", "amount": 110, "autopay": True}, now - 2600),
        ("receptionist", "Tom Alvarez", "+1 555 887 2210", "", "Climate-control pricing question",
         "Follow-up sent", "", "Comparing 10x20 vs climate-controlled; not ready to book. Quote texted, follow-up in 2 days.",
         {"call_type": "rental", "unit_size": "10x20", "monthly_price": 190, "followup": "SMS quote sent"}, now - 5200),
        ("receptionist", "Dana Whitfield", "+1 555 620 4410", "", "Gate code not working",
         "Access restored", "", "Tenant locked out at the gate. Verified phone on account, issued new gate code, gate opened.",
         {"call_type": "access", "unit": "C-07", "gate_code": "7 3 2 6"}, now - 6900),
        ("receptionist", "Elena Petrova", "+1 555 442 8890", "elena@mail.com", "Small unit for documents",
         "Reserved 5x5", "Move-in Saturday", "Needs a small unit for business documents. Reserved a 5x5, moving in Saturday.",
         {"call_type": "rental", "unit_size": "5x5", "move_in": "Saturday", "monthly_price": 45}, now - 9000),
        ("receptionist", "Luis Ortega", "+1 555 118 9021", "", "Office hours & truck rental",
         "Answered", "", "Asked about office hours and whether a moving truck is available. Answered from facility FAQ.",
         {"call_type": "general"}, now - 12000),
        ("receptionist", "Grace Lee", "+1 555 777 0198", "", "Pay overdue balance",
         "Payment collected", "", "Unit A-22, balance $190 overdue 6 days. Paid by card; late fee waived per policy.",
         {"call_type": "payment", "unit": "A-22", "amount": 190}, now - 15000),
        ("sales", "Carlos Mendez", "+1 555 204 8811", "carlos.m@mail.com", "AC not cooling — upstairs",
         "Estimate booked", "Tomorrow 10:00 AM", "Web form 9:41, called 9:42 (58s). Homeowner, AC blowing warm upstairs, 12-yr-old unit. Booked diagnostic + estimate tomorrow 10 AM, confirmation texted.",
         {"source": "Website form", "issue": "AC not cooling", "urgency": "This week", "homeowner": True, "timeline": "ASAP",
          "response_secs": 58, "attempts": 1, "quote_range": "$180 diagnostic · $4.5k–8k if replacement", "booked": True}, now - 2400),
        ("sales", "Marcus Lee", "+1 555 512 7730", "", "Full system replacement quote",
         "Hot — handed to closer", "Estimator visit Thu 2:00 PM", "Google LSA lead. 3,200 sq ft home, 2 systems, wants financing options. Flagged to Mike (closer); estimator visit Thursday 2 PM.",
         {"source": "Google LSA", "issue": "System replacement", "urgency": "Within 2 weeks", "homeowner": True, "timeline": "2 weeks",
          "response_secs": 44, "attempts": 1, "quote_range": "$14k–22k (2 systems)", "hot": True, "closer": "Mike R.", "financing": True}, now - 5400),
        ("sales", "Tom Whitaker", "+1 555 330 6472", "", "Furnace tune-up",
         "Retry scheduled", "", "No answer on attempts 1–2 (voicemail + SMS sent). Next call 4:30 PM, then tomorrow 9 AM. 6-attempt cadence.",
         {"source": "Facebook ad", "issue": "Furnace tune-up", "urgency": "Flexible", "response_secs": 61, "attempts": 2,
          "next_attempt": "Today 4:30 PM", "sms_sent": True}, now - 7200),
        ("sales", "Priya Raman", "+1 555 918 4450", "priya.r@mail.com", "Water heater leaking",
         "Estimate booked", "Today 3:30 PM", "Angi lead. Leak under water heater, urgent. Booked same-day visit 3:30 PM; texted tech ETA.",
         {"source": "Angi", "issue": "Water heater leak", "urgency": "Today", "homeowner": True, "timeline": "Today",
          "response_secs": 39, "attempts": 1, "quote_range": "$1.2k–2.4k", "booked": True}, now - 9600),
        ("sales", "Greg Olsen", "+1 555 645 1187", "", "Price shopping — mini-split",
         "Not now — nurture", "", "Renter, landlord decides. Not a fit now; added to 30-day nurture SMS sequence.",
         {"source": "Website form", "issue": "Mini-split install", "urgency": "Just researching", "homeowner": False,
          "response_secs": 52, "attempts": 1, "nurture": True}, now - 14000),
        ("booking", "Omar Haddad", "+1 555 771 4432", "omar@mail.com", "reschedule",
         "booked", "Wed Jul 23, 11:30 AM", "Moved appointment to Wednesday morning.", {}, now - 7200),
        ("faq", "Grace Kim", "+1 555 909 3311", "", "question: refund policy",
         "answered", "", "Asked about the refund window; answered from KB (30-day money-back).", {}, now - 2400),
        ("restaurant", "Ben Carter", "+1 555 818 2020", "", "takeout order",
         "order placed", "Pickup 7:15 PM", "2x margherita, 1x caesar, 1x tiramisu. Total $48.50.", {}, now - 1200),
        ("reactivation", "Hannah Weiss", "+1 555 656 1200", "hannah@lumen.io", "cold lead re-engaged",
         "booked", "Fri Jul 25, 4:00 PM", "Enquired 3 months ago, never followed up. Re-booked a consult.", {}, now - 600),
    ]
    with _conn() as c:
        for (agent, name, phone, email, intent, outcome, appt, summary, meta, created) in demo:
            c.execute(
                """INSERT INTO records (agent,name,phone,email,intent,outcome,appointment,summary,transcript,meta,created)
                   VALUES (?,?,?,?,?,?,?,?,'',?,?)""",
                (agent, name, phone, email, intent, outcome, appt, summary, json.dumps(meta), created))
