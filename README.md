# VoiceDesk — Shared Dashboard for AI Voice Agents

One live dashboard (a lightweight CRM) that every AI voice-agent demo feeds. Each
agent style — receptionist, sales follow-up, booking, FAQ, restaurant, reactivation —
posts captured calls, leads, and bookings here, shown live and filterable by agent.

Built to sit behind Vapi / Retell agents:
- `POST /vapi/{agent}` — handles Vapi tool-calls + end-of-call reports.
- `POST /ingest/{agent}` — generic JSON ingest (Retell / n8n / manual).
- `POST /simulate/{agent}` — drop a sample record to demo the live dashboard.
- `GET /records?agent=` — live feed the dashboard polls.

A one-line connector pushes the same records into GoHighLevel or any CRM.

Stack: Python · FastAPI · SQLite · (OpenAI for agent logic in the voice layer).
Built by Adel Atya.
