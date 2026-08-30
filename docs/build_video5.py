"""Blue Ridge Plumbing — kanban revenue-recovery board video format (cards move as the AI works)."""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright
ROOT="/Users/adel/Desktop/GHAI/voicedesk"; OUT=f"{ROOT}/docs/vid_out"; FR=f"{ROOT}/docs/vid6/frames"
L=json.load(open(f"{ROOT}/docs/vid6/lines.json")); AUDIO=[]
def post(rec): urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/recovery",data=json.dumps(rec).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=20)
MARIA={"name":"Maria Lopez","phone":"+1 555 402 8810","intent":"Kitchen sink backed up","outcome":"Booked · $89 dispatch","appointment":"Today 2–4 PM","summary":"Missed call 10:41 (crew under a sink). Text-back sent in 8s, AI called back in 52s. Sink fully blocked. Booked same-day 2–4 PM, $89 dispatch credited to repair.","flow":"missed","stage":"booked","callback_secs":52,"text_back_secs":8,"value":320,"source":"Google"}
TOM={"name":"Tom Brennan","phone":"+1 555 771 3302","intent":"Water heater estimate $2,400","outcome":"Estimate closed · $2,400","appointment":"Install Thu 9 AM","summary":"Estimate #2231 sent 3 days ago, no reply. AI follow-up: objection was price → offered 0% / 12 mo ($200/mo). Booked install Thursday 9 AM.","flow":"estimate","stage":"booked","estimate":2400,"value":2400,"days_open":3,"objection":"price","financing":"0% · 12 mo"}
CARDS=[{"col":"open","a":["kevin","Kevin Osei","Leaking spigot · missed 12:03","$180","missed"]},
       {"col":"open","a":["maria","Maria Lopez","Sink backed up · missed 10:41","$320","missed"]},
       {"col":"texted","a":["luis","Luis Ortega","Missed 9:12 · voicemail left","$450","missed"]},
       {"col":"called","a":["sandra","Sandra Wu","Repipe estimate · comparing quotes","$6,800","estimate"]},
       {"col":"called","a":["tom","Tom Brennan","Water heater est. · 3 days open","$2,400","estimate"]},
       {"col":"booked","a":["denise","Denise Park","Water heater flush · reactivated","$189","reactivation"]},
       {"col":"booked","a":["priya","Priya Raman","Sump pump check · reactivated","$149","reactivation"]}]
async def main():
    os.makedirs(FR,exist_ok=True); shutil.rmtree(OUT,ignore_errors=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={"width":1920,"height":1080},record_video_dir=OUT,record_video_size={"width":1920,"height":1080})
        pg=await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage5.html"); await pg.frame_locator("#frame").locator(".ticket").first.wait_for(timeout=15000); await pg.wait_for_timeout(600)
        t0=time.time(); now=lambda: time.time()-t0
        async def at(t):
            d=t-now()
            if d>0: await pg.wait_for_timeout(int(d*1000))
        async def api(c): await pg.evaluate(f"api.{c}")
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f,t): AUDIO.append((f"{ROOT}/{f}",t))
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"],0.5)
        await at(5.0); await api("hook(2)"); await at(5.8); await shot("hook")
        await at(7.6); await api(f"board({json.dumps(CARDS)})")
        await at(8.6); await shot("board")
        # missed call flow: maria open -> texted -> called
        await at(9.0); await api("move('maria','texted')"); await api("callout('Text-back sent · 8 s after the missed call',560,620)")
        await at(10.6); await api("callout('')"); await api("move('maria','called')"); await api("strip('Outbound · missed-call callback','Maria Lopez','+1 (555) 402-8810 · missed call 52 s ago')"); audio("docs/vid4/ringback.mp3",10.8)
        await at(12.6); await api("answer()")
        t=12.9
        for i,ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"],t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==2: await at(t+2.0); await shot("call")
            t+=ln["dur"]+0.05
        T=t
        await at(T); await api("endCall()"); audio("docs/vid2/ding.mp3",T+0.1); await api("move('maria','booked')"); await api("rev(320)"); post(MARIA)
        audio(L["narr"]["save"]["file"],T+0.4); await api("callout('Booked · $320 recovered · logged to GHL',1000,620)")
        await at(T+2.0); await shot("booked")
        await at(T+3.2); await api("callout('')"); await api("dash()"); await api("zoom(300,120,1.25)")
        await at(T+4.4); await api("callout('Slotted into Truck 1 · 2–4 PM · ticket stamped',560,640)")
        await at(T+5.4); await shot("dash-trucks")
        await at(T+6.6); await api("callout('')"); await api("back()"); await api("cool('maria')"); await api("hide()"); audio(L["narr"]["est"]["file"],T+6.7)
        # estimate flow: tom called -> booked
        await at(T+7.4); await api("strip('Outbound · unsold-estimate follow-up','Tom Brennan','+1 (555) 771-3302 · estimate #2231 · 3 days open')"); audio("docs/vid4/ringback.mp3",T+7.6)
        await at(T+9.4); await api("answer()")
        t2=T+9.7
        for i,ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"],t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==2: await at(t2+2.0); await shot("estimate")
            t2+=ln["dur"]+0.05
        T2=t2
        await at(T2); await api("endCall()"); audio("docs/vid2/ding.mp3",T2+0.1); await api("move('tom','booked')"); await api("rev(2400)"); post(TOM)
        await api("callout('Estimate closed · $2,400 · 0% financing',1000,620)")
        await at(T2+1.6); await shot("closed")
        await at(T2+2.6); await api("callout('')"); await api("dash()"); await api("zoom(900,760,1.25)")
        await at(T2+3.8); await api("callout('$2,400 recovered · logged to GoHighLevel',900,600)")
        await at(T2+4.8); await shot("dash-tickets")
        await at(T2+6.0); await api("end()"); audio(L["narr"]["cta"]["file"],T2+6.3)
        await at(T2+7.3); await shot("end"); await at(T2+10.2)
        total=now(); await ctx.close(); await b.close()
    json.dump({"audio":AUDIO,"total":total},open(f"{ROOT}/docs/vid6/timeline.json","w"),indent=1); print("recorded",round(total,1))
asyncio.run(main())
