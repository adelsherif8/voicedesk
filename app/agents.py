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
    {"id": "dental", "name": "Brightside Dental Front Desk",
     "business": "Brightside Dental", "vertical": "dental", "template": "dental.html",
     "desc": "Books new patients (insurance check, right provider/slot), confirmation & reminder calls, no-show recovery from the waitlist, hygiene recall.",
     "icon": "fa-tooth", "color": "#0f8b8d",
     "mode": "light", "bg": "#f3faf9", "accent": "#0f8b8d", "accent2": "#ff7a59",
     "providers": ["Dr. Patel", "Dr. Nguyen", "Hygiene · Sam"]},
    {"id": "realty", "name": "Harbor & Vine Listing Line",
     "business": "Harbor & Vine Realty", "vertical": "real-estate", "template": "realty.html",
     "desc": "Answers listing inquiries 24/7, qualifies (budget, pre-approval, timeline), books showings, routes to the listing agent; seller calls → CMA appointment.",
     "icon": "fa-house", "color": "#cbb27a",
     "mode": "light", "bg": "#f7f5f0", "accent": "#cbb27a", "accent2": "#0b2545",
     "listings": [
         {"id": "L1", "addr": "14 Harbor View Dr", "price": 875000, "beds": 4, "baths": 3, "sqft": 2860, "agent": "Nadia Reyes", "status": "Active", "style": "Coastal"},
         {"id": "L2", "addr": "302 Vine St #5B", "price": 465000, "beds": 2, "baths": 2, "sqft": 1240, "agent": "Ben Carter", "status": "Active", "style": "Loft"},
         {"id": "L3", "addr": "88 Maple Ridge Ln", "price": 1250000, "beds": 5, "baths": 4, "sqft": 4100, "agent": "Nadia Reyes", "status": "Active", "style": "Estate"},
         {"id": "L4", "addr": "19 Cedar Ct", "price": 612000, "beds": 3, "baths": 2, "sqft": 1780, "agent": "Ben Carter", "status": "Pending", "style": "Craftsman"},
     ]},
    {"id": "voicemail", "name": "Lakeside AI Visual Voicemail",
     "business": "Lakeside Family Law", "vertical": "legal", "template": "voicemail.html",
     "desc": "AI attendant takes structured messages, transcribes + summarizes + flags urgency, pushes to IP desk phones (XML) and a web inbox.",
     "icon": "fa-scale-balanced", "color": "#c9a227",
     "mode": "light", "bg": "#f4f1ea", "accent": "#c9a227", "accent2": "#1f2933"},
    {"id": "recovery", "name": "Blue Ridge Revenue Recovery",
     "business": "Blue Ridge Plumbing", "vertical": "plumbing", "template": "recovery.html",
     "desc": "Revenue recovery — missed-call text-back + AI callback, unsold-estimate follow-up, customer reactivation (Retell + GoHighLevel).",
     "icon": "fa-wrench", "color": "#b87333",
     "mode": "light", "bg": "#f5f4f0", "accent": "#b87333", "accent2": "#0f4c81"},
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
    {"id": "restaurant", "name": "Luca's Trattoria Phone Host",
     "business": "Luca's Trattoria", "vertical": "restaurant", "template": "restaurant.html",
     "desc": "Answers every call during the rush: takeout orders to the POS/kitchen printer (modifiers, allergies, upsell, read-back total), reservations onto the floor plan, hours & menu questions.",
     "icon": "fa-utensils", "color": "#9b1c1c",
     "mode": "light", "bg": "#fbf3e4", "accent": "#9b1c1c", "accent2": "#5b6b3a",
     "eighty_six": [{"item": "Branzino", "since": "6:40 PM", "alt": "Rigatoni alla vodka"}, {"item": "Burrata", "since": "7:05 PM", "alt": "Caprese"}], "hours": [["5 PM", 8], ["6 PM", 14], ["7 PM", 26], ["8 PM", 22], ["9 PM", 10]],
     "tables": [{"id":"T1","seats":2},{"id":"T2","seats":2},{"id":"T3","seats":4},{"id":"T4","seats":4},{"id":"T5","seats":4},{"id":"T6","seats":6},{"id":"T7","seats":6},{"id":"T8","seats":8},{"id":"B1","seats":2},{"id":"B2","seats":2},{"id":"P1","seats":4},{"id":"P2","seats":4}]},
    {"id": "reactivation", "name": "Lead Reactivation Agent",
     "desc": "Re-engages old/cold leads and gets them re-booked.",
     "icon": "fa-rotate-left", "color": "#2563eb"},
]

AGENTS_BY_ID = {a["id"]: a for a in AGENTS}


def agent_name(aid: str) -> str:
    a = AGENTS_BY_ID.get(aid)
    return a["name"] if a else aid
