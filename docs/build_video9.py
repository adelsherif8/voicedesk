"""Brightside Dental — calendar-centric format: the week grid fills as Mia books; caller as picture-in-picture."""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright
ROOT="/Users/adel/Desktop/GHAI/voicedesk"; OUT=f"{ROOT}/docs/vid_out"; FR=f"{ROOT}/docs/vid9/frames"
L=json.load(open(f"{ROOT}/docs/vid9/lines.json")); AUDIO=[]
def post(rec): urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/dental",data=json.dumps(rec).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=20)
TARA={"ins_payer":"Delta Dental PPO","ins_cov":["Preventive 100%","Basic 80%","$1,240 left"],"name":"Tara Boyd","phone":"+1 555 201 4478","email":"tara.b@mail.com","intent":"New patient · cleaning + exam","outcome":"Booked · new patient","appointment":"Thu 10:00 AM · Hygiene · Sam","summary":"New patient. Delta Dental verified (2 cleanings/yr covered). Booked Thursday 10 AM cleaning + exam with Sam; new-patient forms texted.","kind":"new","provider":"Hygiene · Sam","day":"Thu","slot":"10:00","status":"booked","value":180,"insurance":"Delta Dental · verified"}
JORGE={"name":"Jorge Ramos","phone":"+1 555 771 3320","intent":"Reminder · crown seat Wed 2:00","outcome":"Rescheduled → Fri 10:00","appointment":"Fri 10:00 AM · Dr. Nguyen","summary":"Reminder call: conflict tomorrow; AI moved the crown seat to Friday 10 AM with Dr. Nguyen and offered Wednesday 2 PM to the waitlist.","kind":"reminder","provider":"Dr. Nguyen","day":"Fri","slot":"10:00","status":"rescheduled","freed":"Wed 2:00","value":950}
AMINA={"name":"Amina Yusuf","phone":"+1 555 330 9987","email":"amina.y@mail.com","intent":"Waitlist → filled Wed 2:00","outcome":"Slot refilled · $950","appointment":"Wed 2:00 PM · Dr. Nguyen","summary":"Waitlist patient called by AI within 3 minutes of the Wednesday 2 PM opening; accepted crown prep slot. Chair time saved.","kind":"waitlist","provider":"Dr. Nguyen","day":"Wed","slot":"2:00","status":"booked","value":950}
async def main():
    os.makedirs(FR,exist_ok=True); shutil.rmtree(OUT,ignore_errors=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={"width":1920,"height":1080},record_video_dir=OUT,record_video_size={"width":1920,"height":1080})
        pg=await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage9.html"); await pg.frame_locator("#frame").locator(".ap").first.wait_for(timeout=15000); await pg.wait_for_timeout(600)
        t0=time.time(); now=lambda: time.time()-t0
        async def at(t):
            d=t-now()
            if d>0: await pg.wait_for_timeout(int(d*1000))
        async def api(c): await pg.evaluate(f"api.{c}")
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f,t): AUDIO.append((f"{ROOT}/{f}",t))
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"],0.5)
        await at(6.4); await api("hook(2)"); await at(7.2); await shot("hook")
        await at(8.8); await api("cal()"); await at(9.6); await shot("calendar")
        await at(10.0); await api("call('Incoming · new patient · answered in 2 s','Tara Boyd','+1 (555) 201-4478 · new patient','TB')"); audio("docs/vid2/ring.mp3",10.1)
        await at(11.8); await api("answer()")
        t=12.1; beats={1:[("chip(1)",1.5)],2:[("chip(2)",1.8),("ins()",2.0),("chip(3)",4.0)],4:[("chip(4)",0.3),("ins(false)",1.4),("chip(5)",2.2)]}
        for i,ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"],t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==3: await api("book('Hygiene · Sam','Thu','10:00','Tara · new patient')"); await api("kp('kB','3')")
            for c,off in beats.get(i,[]): await at(t+off); await api(c)
            if i==2: await at(t+4.4); await shot("call")
            t+=ln["dur"]+0.1
        T=t
        await at(T); await api("endCall()"); audio("docs/vid2/ding.mp3",T+0.1); post(TARA)
        audio(L["narr"]["save"]["file"],T+0.4); await api("callout('New patient booked · Delta Dental verified · $180 production added',70,700)")
        await at(T+2.2); await shot("booked")
        await at(T+4.4); await api("callout('')"); await api("hide()"); await api("dash()"); await api("zoom(900,0,1.18)")
        await at(T+5.6); await api("callout('Week schedule · confirmations · waitlist — live',1000,720)")
        await at(T+6.6); await shot("dash")
        await at(T+7.6); await api("callout('')"); await api("back()"); audio(L["narr"]["remind"]["file"],T+7.7)
        await api("chips([['fa-bell','Reminder call'],['fa-calendar-xmark','Conflict'],['fa-calendar-check','Rescheduled'],['fa-list-check','Slot → waitlist'],['fa-rotate','Chair refilled']])")
        await api("call('Outbound · reminder for tomorrow','Jorge Ramos','+1 (555) 771-3320 · crown seat Wed 2:00','JR')"); audio("docs/vid4/ringback.mp3",T+9.0)
        await at(T+10.8); await api("answer()")
        t2=T+11.1
        for i,ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"],t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==0: await at(t2+1.0); await api("chip(1)")
            if i==1: await at(t2+2.4); await api("chip(2)")
            if i==2: await at(t2+2.4); await api("chip(3)"); await api("book('Dr. Nguyen','Fri','10:00','Jorge · moved')"); await at(t2+4.4); await api("chip(4)"); await api("free('Dr. Nguyen','Wed','2:00 Jorge · crown')"); await shot("remind")
            t2+=ln["dur"]+0.1
        T2=t2
        await at(T2); await api("endCall()"); audio("docs/vid2/ding.mp3",T2+0.1); post(JORGE)
        await at(T2+1.6); post(AMINA); await api("chip(5)"); await api("book('Dr. Nguyen','Wed','2:00','Amina · waitlist')"); await api("kp('kD','$1,900')"); await api("callout('Waitlist patient took the slot in 3 minutes · $950 saved',70,700)")
        await at(T2+3.2); await shot("refilled")
        await at(T2+4.6); await api("end()"); audio(L["narr"]["cta"]["file"],T2+5.0)
        await at(T2+6.0); await shot("end"); await at(T2+8.8)
        total=now(); await ctx.close(); await b.close()
    json.dump({"audio":AUDIO,"total":total},open(f"{ROOT}/docs/vid9/timeline.json","w"),indent=1); print("recorded",round(total,1))
asyncio.run(main())
