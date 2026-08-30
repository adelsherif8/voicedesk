"""Project #2 video — Summit Heating & Air speed-to-lead (Riley). ~58 s.
Run: .venv/bin/python docs/build_video2.py   (local VoiceDesk on :8099, clean DB)
"""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright

ROOT = "/Users/adel/Desktop/GHAI/voicedesk"
OUT = f"{ROOT}/docs/vid_out"; FRAMES = f"{ROOT}/docs/vid4/frames"
L = json.load(open(f"{ROOT}/docs/vid4/lines.json")); AUDIO = []

def post(rec):
    urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/sales", data=json.dumps(rec).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=20)

DANA = {"name": "Dana Kowalski", "phone": "+1 555 640 2277", "email": "dana.k@mail.com", "intent": "AC blowing warm upstairs",
    "outcome": "Estimate booked", "appointment": "Tomorrow 10:00 AM",
    "summary": "Web form 2:14, called 2:15 (58s). Homeowner, AC blowing warm upstairs, 12-yr-old unit. Booked diagnostic + estimate tomorrow 10 AM, confirmation texted.",
    "source": "Website form", "issue": "AC not cooling", "urgency": "This week", "homeowner": True, "timeline": "ASAP",
    "response_secs": 58, "attempts": 1, "quote_range": "$180 diagnostic · $4.5k–8k if replacement", "booked": True}
AISHA = {"name": "Aisha Bello", "phone": "+1 555 771 2093", "intent": "Replace both systems + financing", "outcome": "Hot — handed to closer",
    "appointment": "Estimator visit Thu 2:00 PM", "summary": "Google LSA lead, called in 44s. Wants both systems replaced with financing. Flagged to Mike (closer); estimator visit Thursday 2 PM.",
    "source": "Google LSA", "issue": "System replacement", "urgency": "Within 2 weeks", "homeowner": True, "response_secs": 44, "attempts": 1,
    "quote_range": "$14k–22k (2 systems)", "hot": True, "closer": "Mike R.", "financing": True}

async def main():
    os.makedirs(FRAMES, exist_ok=True); shutil.rmtree(OUT, ignore_errors=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=OUT, record_video_size={"width": 1920, "height": 1080})
        pg = await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage2.html")
        await pg.frame_locator("#dash").locator(".card").first.wait_for(timeout=15000); await pg.wait_for_timeout(600)
        t0 = time.time(); now = lambda: time.time() - t0
        async def at(t):
            d = t - now()
            if d > 0: await pg.wait_for_timeout(int(d * 1000))
        async def api(call): await pg.evaluate(f"api.{call}")
        async def shot(n): await pg.screenshot(path=f"{FRAMES}/{n}.png")
        def audio(f, t): AUDIO.append((f"{ROOT}/{f}", t))
        dash = lambda: next(f for f in pg.frames if "/agent/" in f.url)
        async def tab(n): await dash().evaluate(f"document.querySelector('.tab[data-tab=\"{n}\"]').click()")

        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"], 0.5)
        await at(5.0); await api("hook(2)"); await at(5.8); await shot("hook")
        await at(7.6); await api("scene()")
        await at(8.0); await api("incoming()"); audio("docs/vid4/ringback.mp3", 8.1); audio("docs/vid4/ringback.mp3", 10.0)
        await at(9.0); await shot("dialing")
        await at(11.5); await api("answer()"); await api("caption('Calls the lead 58 s after the form — not 42 min','fa-stopwatch')")
        t = 11.8
        caps = {1: ("Qualifies: issue · urgency · homeowner", "fa-user-check"), 2: ("Books the estimate into your calendar", "fa-calendar-check"), 4: ("Texts the confirmation — no rep involved", "fa-comment-sms")}
        for i, ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"], t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i in caps: await api(f"caption({json.dumps(caps[i][0])},{json.dumps(caps[i][1])})")
            if i == 2: await at(t + 2.5); await shot("call")
            t += ln["dur"] + 0.15
        T = t
        await at(T); await api("endCall('Booked tomorrow 10 AM · confirmation texted')"); await api("caption('')"); audio("docs/vid2/ding.mp3", T + 0.1)
        post(DANA); audio(L["narr"]["save"]["file"], T + 0.4); await api("zoom(1180,330,1.45)")
        await at(T + 3.2); await api("callout('Booked + logged 58 s after the form',905,690)")
        await at(T + 4.2); await shot("saved")
        await at(T + 5.0); await api("callout('')"); await api("zoom(0,0,null)"); audio(L["narr"]["hot"]["file"], T + 5.1)
        await api("newCall('Aisha Bello','+1 (555) 771-2093 · Google LSA · form 44s ago')")
        await at(T + 6.9); await api("answer()"); await api("caption('Big ticket? Riley hands it to your closer — warm','fa-fire')")
        t2 = T + 7.2
        for i, ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"], t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i == 1: await at(t2 + 3.0); await shot("hot")
            t2 += ln["dur"] + 0.15
        T2 = t2
        await at(T2); await api("endCall('Flagged HOT → Mike · estimator Thu 2 PM')"); await api("caption('')"); audio("docs/vid2/ding.mp3", T2 + 0.1)
        post(AISHA); await tab("hot"); await api("zoom(800,430,1.45)")
        await at(T2 + 2.1); await api("callout('Hot lead → closer · $14k–22k · financing',1090,470)")
        await at(T2 + 3.0); await shot("hotlog")
        await at(T2 + 4.2); await api("end()"); audio(L["narr"]["cta"]["file"], T2 + 4.6)
        await at(T2 + 5.6); await shot("end")
        await at(T2 + 8.2)
        total = now(); await ctx.close(); await b.close()
    webm = glob.glob(f"{OUT}/*.webm")[0]
    json.dump({"audio": AUDIO, "total": total}, open(f"{ROOT}/docs/vid4/timeline.json", "w"), indent=1)
    print("recorded", round(total, 1))

asyncio.run(main())
