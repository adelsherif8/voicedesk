"""Registry of demo voice-agent styles. Each is a different showcase agent that
feeds the same shared dashboard. Add a new one here and it appears automatically.
"""

AGENTS = [
    {"id": "receptionist", "name": "StoreRight Receptionist",
     "business": "StoreRight Self-Storage", "vertical": "storage",
     "desc": "Inbound storage calls — quotes units, qualifies, reserves & books tours.",
     "icon": "fa-warehouse", "color": "#f97316",
     # industry palette (see skill color-system.md): storage = orange accent, steel-blue secondary, warm charcoal
     "bg": "#12151b", "accent": "#f97316", "accent2": "#7ea2cf"},
    {"id": "sales", "name": "Sales Follow-Up Agent",
     "desc": "Outbound — calls new leads, qualifies, and hands off hot ones.",
     "icon": "fa-phone-volume", "color": "#0e9488"},
    {"id": "booking", "name": "Appointment Booking Agent",
     "desc": "Books, reschedules, and confirms appointments by voice.",
     "icon": "fa-calendar-check", "color": "#e08600"},
    {"id": "faq", "name": "FAQ / Support Agent",
     "desc": "Answers questions from the business's knowledge base (voice + RAG).",
     "icon": "fa-circle-question", "color": "#9333ea"},
    {"id": "restaurant", "name": "Restaurant Order Agent",
     "desc": "Takes phone orders and reservations, reads back the total.",
     "icon": "fa-utensils", "color": "#be123c"},
    {"id": "reactivation", "name": "Lead Reactivation Agent",
     "desc": "Re-engages old/cold leads and gets them re-booked.",
     "icon": "fa-rotate-left", "color": "#2563eb"},
]

AGENTS_BY_ID = {a["id"]: a for a in AGENTS}


def agent_name(aid: str) -> str:
    a = AGENTS_BY_ID.get(aid)
    return a["name"] if a else aid
