"""Registry of demo voice-agent styles. Each is a different showcase agent that
feeds the same shared dashboard. Add a new one here and it appears automatically.
"""

AGENTS = [
    {"id": "receptionist", "name": "StoreRight Receptionist",
     "business": "StoreRight Self-Storage", "vertical": "storage",
     "desc": "Inbound storage calls — quotes units, qualifies, reserves & books tours.",
     "icon": "fa-warehouse", "color": "#f97316",
     # industry palette (see skill color-system.md): storage = orange accent, steel-blue secondary, warm charcoal
     "mode": "light", "bg": "#faf7f2", "accent": "#f97316", "accent2": "#2f5d8a",
     # live inventory the agent quotes from (available = total - reserved records)
     "inventory": [
         {"size": "5x5", "total": 20, "price": 45, "label": "Small · closet"},
         {"size": "10x10", "total": 30, "price": 110, "label": "Medium · 1-bed apt"},
         {"size": "10x20", "total": 15, "price": 190, "label": "Large · 3-bed house"},
         {"size": "10x10 CC", "total": 12, "price": 145, "label": "Climate-controlled"},
     ]},
    {"id": "support", "name": "NordFrost Support Line",
     "business": "NordFrost Appliances", "vertical": "appliance-support", "template": "support.html",
     "desc": "Inbound customer service — warranty lookup, troubleshooting, technician dispatch, parts orders, warm transfer.",
     "icon": "fa-snowflake", "color": "#1428a0",
     "mode": "light", "bg": "#f4f6fb", "accent": "#1428a0", "accent2": "#5b6b8c"},
    {"id": "sales", "name": "Riley — Speed-to-Lead Agent",
     "business": "Summit Heating & Air", "vertical": "home-services", "template": "sales.html",
     "desc": "Outbound — calls every new lead within 60s, qualifies, books the estimate, retries no-answers, flags hot ones.",
     "icon": "fa-fire-flame-simple", "color": "#f59e0b",
     "mode": "light", "bg": "#f6f8fb", "accent": "#f59e0b", "accent2": "#1e3a5f"},
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
