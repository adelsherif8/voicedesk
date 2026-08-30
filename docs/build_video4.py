"""NordFrost video — support-console format (distinct from StoreRight's phone+dashboard split)."""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright
ROOT="/Users/adel/Desktop/GHAI/voicedesk"; OUT=f"{ROOT}/docs/vid_out"; FR=f"{ROOT}/docs/vid5/frames"
L=json.load(open(f"{ROOT}/docs/vid5/lines.json")); AUDIO=[]
def post(rec): urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/support",data=json.dumps(rec).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=20)
HANNAH={"name":"Hannah Brooks","phone":"+1 555 204 1180","email":"hannah.b@mail.com","intent":"Fridge not cooling","outcome":"Technician booked","appointment":"Thu 9–11 AM","summary":"Serial NF-RF28-4471 verified, in warranty (14 mo). Freezer OK, fridge warm → evaporator fan. Booked authorized tech Thu 9–11 AM, part pre-ordered, SMS sent.","product":"Refrigerator RF28","serial":"NF-RF28-4471","warranty":"In warranty · 14 of 24 mo","issue":"Fridge warm, freezer OK","resolution":"dispatch","part":"Evaporator fan DA31-00146","wait_secs":0,"csat":5}
GERALD={"name":"Gerald Okafor","phone":"+1 555 918 7734","intent":"Washer leaking — 3rd call","outcome":"Transferred to human","summary":"Third contact about WF45 leak, repaired twice. Frustration detected → warm transfer to senior agent Lena with full history; replacement request opened.","product":"Washer WF45","serial":"NF-WF45-0088","warranty":"In warranty · 9 of 24 mo","issue":"Leak, repeat repair","resolution":"transfer","transfer_to":"Lena (Tier 2)","sentiment":"frustrated","wait_secs":0}
async def main():
    os.makedirs(FR,exist_ok=True); shutil.rmtree(OUT,ignore_errors=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={"width":1920,"height":1080},record_video_dir=OUT,record_video_size={"width":1920,"height":1080})
        pg=await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage4.html")
        await pg.frame_locator("#frame").locator(".card").first.wait_for(timeout=15000); await pg.wait_for_timeout(500)
        t0=time.time(); now=lambda: time.time()-t0
        async def at(t):
            d=t-now()
            if d>0: await pg.wait_for_timeout(int(d*1000))
        async def api(c): await pg.evaluate(f"api.{c}")
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f,t): AUDIO.append((f"{ROOT}/{f}",t))
        dash=lambda: next(f for f in pg.frames if "/agent/" in f.url)
        async def tab(n): await dash().evaluate(f"document.querySelector('.tab[data-tab=\"{n}\"]').click()")
        # hook
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"],0.5)
        await at(5.2); await api("hook(2)"); await at(6.0); await shot("hook")
        # console + ring
        await at(7.0); await api("console()"); audio("docs/vid2/ring.mp3",7.3)
        await at(8.2); await shot("incoming")
        await at(9.2); await api("answer()")
        t=9.5; acts={1:("fa-magnifying-glass","Serial NF-RF28-4471 found","RF28 refrigerator · registered Jun 2025",""),2:("fa-shield-halved","Warranty verified — 14 of 24 months","no charge to the customer","ok"),3:("fa-screwdriver-wrench","Diagnosis: evaporator fan","warm fridge + cold freezer pattern",""),4:("fa-truck","Technician dispatched · Thu 9–11 AM","part DA31-00146 pre-ordered to the truck","ok")}
        for i,ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"],t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i in acts:
                ic,ti,su,cl=acts[i]; await at(t+1.2); await api(f"act({json.dumps(ic)},{json.dumps(ti)},{json.dumps(su)},{json.dumps(cl)})")
            if i==3: await at(t+3.0); await shot("call")
            t+=ln["dur"]+0.15
        T=t
        await at(T); await api("endCall()"); await api("act('fa-comment-sms','Confirmation texted','tech name + window · ticket #48211 closed','ok')"); audio("docs/vid2/ding.mp3",T+0.1)
        await api("cost()"); post(HANNAH); audio(L["narr"]["save"]["file"],T+0.4)
        await at(T+2.0); await shot("actions")
        # dashboard reveal full width
        await at(T+2.8); await api("dash()"); await at(T+3.3); await api("zoom(900,0,1.22)")
        await at(T+4.4); await api("callout('Ticket logged · tech dispatched · $1.18',1180,560)")
        await at(T+5.4); await shot("saved")
        # second call
        await at(T+6.6); await api("callout('')"); await api("back()"); await api("newCall('Gerald Okafor','+1 (555) 918-7734 · 3rd call this month','GO')"); audio(L["narr"]["xfer"]["file"],T+6.7); audio("docs/vid2/ring.mp3",T+8.0)
        await at(T+9.7); await api("answer()")
        t2=T+10.0
        for i,ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"],t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==0: await at(t2+2.6); await api("alert('Frustration detected — repeat issue, 3rd contact','escalating to a human · history attached')"); await api("act('fa-face-frown','Sentiment: frustrated · repeat repair','policy: do not argue — hand to a senior agent','red')")
            if i==1: await at(t2+2.5); await api("act('fa-people-arrows','Warm transfer → Lena (Tier 2)','full ticket history + replacement request opened','ok')"); await at(t2+4.0); await shot("xfer")
            t2+=ln["dur"]+0.15
        T2=t2
        await at(T2); await api("endCall()"); audio("docs/vid2/ding.mp3",T2+0.1); post(GERALD)
        await at(T2+0.8); await api("alert('')"); await api("dash()"); await tab("escal"); await api("zoom(700,0,1.22)")
        await at(T2+2.4); await api("callout('Escalation logged · human has the full story',1090,520)")
        await at(T2+3.3); await shot("xferlog")
        await at(T2+4.0); await api("end()"); audio(L["narr"]["cta"]["file"],T2+4.4)
        await at(T2+5.4); await shot("end"); await at(T2+7.4)
        total=now(); await ctx.close(); await b.close()
    json.dump({"audio":AUDIO,"total":total},open(f"{ROOT}/docs/vid5/timeline.json","w"),indent=1); print("recorded",round(total,1))
asyncio.run(main())
