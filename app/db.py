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
        ("restaurant", "Marcus Bell", "+1 555 771 0098", "", "Takeout · 2 pizzas + salad",
         "Order to kitchen · $48.50", "Pickup 7:15 PM", "Takeout: 2× Margherita (one no basil), 1× Caesar, 1× Tiramisu (upsold). Read back total $48.50; paid by card; ticket printed to kitchen.",
         {"kind": "order", "items": [["Margherita pizza", 2, 32.0], ["Caesar salad", 1, 9.5], ["Tiramisu", 1, 7.0]], "total": 48.5, "pickup": "7:15 PM", "upsell": "Tiramisu", "allergy": "", "paid": True, "ready": True, "minutes": 14}, now - 3300),
        ("restaurant", "Priya Nair", "+1 555 301 7745", "", "Takeout · gluten-free pasta",
         "Order to kitchen · $31.00", "Pickup 6:50 PM", "Takeout: 1× Rigatoni alla vodka (gluten-free pasta — allergy flagged to kitchen), 1× Garlic bread. Total $31.00.",
         {"kind": "order", "items": [["Rigatoni alla vodka (GF)", 1, 22.0], ["Garlic bread", 1, 9.0]], "total": 31.0, "pickup": "6:50 PM", "allergy": "Gluten — flagged to kitchen", "paid": True, "ready": True, "minutes": 11, "eighty_six": "asked for Branzino → offered rigatoni"}, now - 5400),
        ("restaurant", "Tom Alvarez", "+1 555 118 3321", "", "Reservation · 8 · Saturday 8 PM",
         "Table T8 · deposit taken", "Sat 8:00 PM · party of 8", "Birthday party of eight Saturday 8 PM. T8 held with $50 card deposit per policy; high chair requested.",
         {"kind": "reservation", "party": 8, "time": "Sat 8:00 PM", "table": "T8", "occasion": "Birthday", "deposit": 50, "source": "phone"}, now - 9000),
        ("restaurant", "Elena Voss", "+1 555 245 6610", "", "Are you open Monday? Parking?",
         "Answered · FAQ", "", "Asked about Monday hours (closed) and parking (lot behind building). Answered from restaurant info; offered to book Tuesday.",
         {"kind": "faq"}, now - 12000),
        ("dental", "Karen Ellis", "+1 555 204 7781", "", "Confirmation call · cleaning Tue 9:00",
         "Confirmed", "Tue 9:00 AM · Hygiene · Sam", "Reminder call the day before: confirmed hygiene visit Tuesday 9 AM; reminded to arrive 10 min early with insurance card.",
         {"kind": "reminder", "provider": "Hygiene · Sam", "day": "Tue", "slot": "9:00", "status": "confirmed", "value": 180}, now - 1900),
        ("dental", "Ben Okafor", "+1 555 118 4402", "", "Hygiene recall · 7 months overdue",
         "Recall booked", "Thu 3:00 PM · Hygiene · Sam", "Overdue hygiene recall: AI called, booked Thursday 3 PM cleaning + exam, sent insurance-on-file confirmation.",
         {"kind": "recall", "provider": "Hygiene · Sam", "day": "Thu", "slot": "3:00", "status": "booked", "value": 180, "overdue_months": 7}, now - 7900),
        ("dental", "Lena Hoffmann", "+1 555 909 1120", "", "Tooth pain — same day?",
         "Emergency · same day", "Mon 4:30 PM · Dr. Patel", "Severe pain, swelling. Triaged as urgent; booked same-day 4:30 PM with Dr. Patel; on-call line notified.",
         {"kind": "emergency", "provider": "Dr. Patel", "day": "Mon", "slot": "4:30", "status": "booked", "value": 320, "insurance": "Delta Dental · verified"}, now - 12000),
        ("realty", "Grace Lin", "+1 555 909 3311", "", "Inquiry · 88 Maple Ridge Ln",
         "Qualified · routed to Nadia", "Nadia calling back today", "Yard-sign call. Budget up to $1.3M, cash buyer, wants a showing this week. Hot — routed to Nadia with notes.",
         {"listing": "L3", "source": "Yard sign", "budget": "up to $1.3M", "preapproved": True, "lender": "Cash", "timeline": "This week", "musts": "Home office, pool", "score": 95, "agent": "Nadia Reyes", "kind": "buyer", "hot": True, "response_secs": 3}, now - 5100),
        ("realty", "Daniel Osei", "+1 555 118 2277", "d.osei@mail.com", "Inquiry · 14 Harbor View Dr",
         "Nurture · not pre-approved", "", "Realtor.com inquiry. Budget $800K but not pre-approved yet; 6+ months out. Sent lender intro + listing alerts; follow-up in 2 weeks.",
         {"listing": "L1", "source": "Realtor.com", "budget": "$800K", "preapproved": False, "timeline": "6+ months", "musts": "Water view", "score": 42, "agent": "Nadia Reyes", "kind": "buyer", "nurture": True, "response_secs": 5}, now - 9000),
        ("realty", "Leo Marin", "+1 555 245 9034", "", "Inquiry · 19 Cedar Ct",
         "Pending — offered alternatives", "", "Asked about 19 Cedar Ct (pending). AI explained status and suggested 302 Vine St; caller wants photos first. Alerts set.",
         {"listing": "L4", "source": "Google", "budget": "$600K", "preapproved": True, "lender": "Wells Fargo", "timeline": "90 days", "score": 61, "agent": "Ben Carter", "kind": "buyer", "response_secs": 4}, now - 17000),
        ("voicemail", "Marcus Bell", "+1 555 771 0098", "", "New client — divorce consultation",
         "New lead · intake", "Consult Thu 11 AM", "Prospective client seeking divorce consultation; owns a business, two children. AI booked intake consult Thursday 11 AM and sent the intake form by SMS.",
         {"priority": "high", "matter": "New matter · divorce", "assigned": "Intake", "duration": 62, "transcript": "Hi, my name's Marcus Bell. I'm looking for a lawyer for a divorce. We own a business together and have two kids, so it's complicated. I'd like to talk to someone this week.", "intent": "new client", "status": "new"}, now - 2700),
        ("voicemail", "Unknown caller", "+1 555 909 7734", "", "Hang-up — no message",
         "Captured · text sent", "", "Caller hung up at the greeting. AI sent a text: 'Sorry we missed you — reply here or book a callback.' Awaiting reply.",
         {"priority": "low", "matter": "—", "assigned": "—", "duration": 0, "transcript": "", "intent": "hang-up", "status": "read", "hangup": True}, now - 8000),
        ("voicemail", "Tom Alvarez", "+1 555 118 3321", "", "Signed documents ready for pickup?",
         "Routine · assigned to paralegal", "", "Asking whether the signed settlement documents are ready for pickup. Assigned to paralegal J. Ruiz.",
         {"priority": "medium", "matter": "Alvarez settlement", "assigned": "J. Ruiz", "duration": 22, "transcript": "Hey, Tom Alvarez here. Just checking if the settlement paperwork is ready for me to pick up. Thanks.", "intent": "status check", "status": "read"}, now - 14000),
        ("voicemail", "Elena Voss", "+1 555 245 6610", "elena.v@mail.com", "Mediation rescheduling request",
         "Medium · assigned to D. Okafor", "", "Asks to move Friday mediation to next week due to travel. Needs attorney confirmation; not urgent.",
         {"priority": "medium", "matter": "Voss v. Voss · mediation", "assigned": "D. Okafor", "duration": 35, "transcript": "Hi, Elena Voss. I'm traveling Friday, can we push the mediation to next week? Let me know what works.", "intent": "scheduling", "status": "read"}, now - 20000),
        ("recovery", "Ana Ruiz", "+1 555 212 9034", "", "Toilet won't stop running",
         "Missed · text-back sending", "", "Missed call 12:20 (crew on a job). Text-back queued; AI callback scheduled in 60s.",
         {"flow": "missed", "stage": "open", "value": 220, "source": "Google"}, now - 60),
        ("recovery", "Denise Park", "+1 555 630 1188", "", "Annual water heater flush",
         "Reactivated · $189", "Tue 11 AM", "Last visit 14 months ago (water heater install). Reactivation call: booked annual flush + inspection, $189; offered $12/mo maintenance plan.",
         {"flow": "reactivation", "stage": "booked", "last_visit_months": 14, "value": 189, "plan": "Maintenance plan offered"}, now - 5400),
        ("recovery", "Kevin Osei", "+1 555 118 7745", "", "Leaking outdoor spigot",
         "Texted · awaiting reply", "", "Missed call 12:03. Text-back sent in 6s; callback rang out, voicemail left. Second attempt scheduled 3:00 PM.",
         {"flow": "missed", "stage": "texted", "text_back_secs": 6, "callback_secs": 58, "attempts": 1, "next_attempt": "3:00 PM", "value": 180, "source": "Yelp"}, now - 7200),
        ("recovery", "Sandra Wu", "+1 555 909 2210", "sandra.w@mail.com", "Repipe estimate $6,800",
         "Follow-up · deciding", "", "Estimate #2219, 6 days open. AI follow-up: comparing with another quote; sent itemized breakdown + warranty terms by SMS. Callback Friday.",
         {"flow": "estimate", "stage": "called", "estimate": 6800, "value": 6800, "days_open": 6, "objection": "comparing quotes", "next_attempt": "Fri 10 AM"}, now - 9800),
        ("recovery", "Luis Ortega", "+1 555 545 6621", "", "Missed call · no answer on callback",
         "Called back · voicemail", "", "Missed call 9:12. Text-back in 7s; AI callback 49s later went to voicemail; message + booking link left.",
         {"flow": "missed", "stage": "called", "text_back_secs": 7, "callback_secs": 49, "attempts": 1, "next_attempt": "Tomorrow 9 AM", "value": 450, "source": "Website"}, now - 14000),
        ("recovery", "Priya Raman", "+1 555 330 4471", "", "Sump pump check before storms",
         "Reactivated · $149", "Wed 3 PM", "Last visit 18 months ago. Reactivation: storm-season sump pump check booked Wed 3 PM, $149.",
         {"flow": "reactivation", "stage": "booked", "last_visit_months": 18, "value": 149}, now - 20000),
        ("support", "Olivia Chen", "+1 555 204 3391", "olivia.c@mail.com", "Fridge not cooling",
         "Technician booked", "Thu 9–11 AM", "Serial NF-RF28-4471 verified, in warranty (14 mo). Freezer OK, fridge warm → likely evaporator fan. Booked authorized tech Thu 9–11 AM, part pre-ordered, SMS sent.",
         {"product": "Refrigerator RF28", "serial": "NF-RF28-4471", "warranty": "In warranty · 14 of 24 mo", "issue": "Fridge warm, freezer OK", "resolution": "dispatch", "part": "Evaporator fan DA31-00146", "wait_secs": 0, "csat": 5}, now - 1800),
        ("support", "Devon Price", "+1 555 771 6620", "", "Dishwasher error code 4C",
         "Resolved by phone", "", "Error 4C = water supply. Walked caller through inlet valve + hose kink check; hose was kinked. Cycle restarted, resolved. No visit needed.",
         {"product": "Dishwasher DW80", "serial": "NF-DW80-9012", "warranty": "Out of warranty", "issue": "Error 4C", "resolution": "resolved", "wait_secs": 0, "csat": 5}, now - 3300),
        ("support", "Maria Santos", "+1 555 330 4471", "", "Water filter order",
         "Part ordered · $49", "", "Ordered genuine filter HAF-CIN for RF28, $49 paid by card, 2-day shipping. Enrolled in 6-month filter reminder.",
         {"product": "Refrigerator RF28", "serial": "NF-RF28-2210", "warranty": "In warranty · 6 of 24 mo", "issue": "Filter replacement", "resolution": "parts", "part": "Water filter HAF-CIN", "amount": 49, "wait_secs": 0, "csat": 4}, now - 5200),
        ("support", "Ray Coleman", "+1 555 918 2260", "", "Washer leaking — 3rd call",
         "Transferred to human", "", "Third contact about WF45 leak, repair failed twice. Frustration detected → warm transfer to senior agent Lena with full history; replacement request opened.",
         {"product": "Washer WF45", "serial": "NF-WF45-0088", "warranty": "In warranty · 9 of 24 mo", "issue": "Leak, repeat repair", "resolution": "transfer", "transfer_to": "Lena (Tier 2)", "sentiment": "frustrated", "wait_secs": 0}, now - 7600),
        ("support", "Aiko Tanaka", "+1 555 645 2231", "aiko.t@mail.com", "Oven not heating",
         "Technician booked", "Fri 1–3 PM", "Serial verified, extended warranty. Bake element failure symptoms. Tech booked Fri 1–3 PM, element pre-ordered.",
         {"product": "Range NE63", "serial": "NF-NE63-5567", "warranty": "Extended · 31 of 60 mo", "issue": "No heat", "resolution": "dispatch", "part": "Bake element DG47-00038", "wait_secs": 0, "csat": 5}, now - 11000),
        ("support", "Sam Whitfield", "+1 555 118 9902", "", "Ice maker slow",
         "Resolved by phone", "", "Ice maker producing slowly. Guided reset + freezer temp to -18°C; explained 24h recovery. Resolved.",
         {"product": "Refrigerator RF28", "serial": "NF-RF28-7781", "warranty": "Out of warranty", "issue": "Ice maker slow", "resolution": "resolved", "wait_secs": 0, "csat": 4}, now - 14500),
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
