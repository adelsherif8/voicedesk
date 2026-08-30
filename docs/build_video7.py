"""Lakeside Family Law — AI visual voicemail. Before/after split format + desk-phone screen + dashboard reveal."""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright
ROOT="/Users/adel/Desktop/GHAI/voicedesk"; OUT=f"{ROOT}/docs/vid_out"; FR=f"{ROOT}/docs/vid7/frames"
L=json.load(open(f"{ROOT}/docs/vid7/lines.json")); AUDIO=[]
def post(rec): urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/voicemail",data=json.dumps(rec).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=20)
RACHEL={"name":"Rachel Kim","phone":"+1 555 610 2284","email":"rachel.kim@mail.com","intent":"Court date moved — needs callback today","outcome":"Urgent · assigned to D. Okafor","appointment":"Callback by 3 PM","summary":"Custody hearing moved to Monday 9 AM; opposing counsel filed a motion. Needs attorney callback before 3 PM today.","priority":"urgent","matter":"Kim v. Kim · custody","assigned":"D. Okafor","duration":48,"transcript":"Hi, it's Rachel Kim. My custody hearing got moved to Monday at nine and the other side filed a motion. I need Daniel to call me before three today.","intent_type":"case update","status":"new"}
PRIYA={"name":"Priya Desai","phone":"+1 555 330 4410","email":"priya.d@mail.com","intent":"Invoice #2291 question","outcome":"Routine · routed to billing","summary":"Question about a filing fee on invoice #2291. Routed to billing; no attorney action needed.","priority":"low","matter":"Desai adoption","assigned":"Billing","duration":31,"transcript":"Hi, Priya Desai. I have a question about a filing fee on invoice 2291. No rush.","status":"read"}
async def main():
    os.makedirs(FR,exist_ok=True); shutil.rmtree(OUT,ignore_errors=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={"width":1920,"height":1080},record_video_dir=OUT,record_video_size={"width":1920,"height":1080})
        pg=await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage7.html"); await pg.frame_locator("#frame").locator(".row").first.wait_for(timeout=15000); await pg.wait_for_timeout(600)
        t0=time.time(); now=lambda: time.time()-t0
        async def at(t):
            d=t-now()
            if d>0: await pg.wait_for_timeout(int(d*1000))
        async def api(c): await pg.evaluate(f"api.{c}")
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f,t): AUDIO.append((f"{ROOT}/{f}",t))
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"],0.5)
        await at(4.6); await api("hook(2)"); await at(5.4); await shot("hook")
        await at(7.8); await api("split()"); audio("docs/vid2/ring.mp3",8.1)
        await at(9.0); await shot("split")
        await at(10.0); await api("answer()")
        t=10.3
        for i,ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"],t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==1: await at(t+3.0); await shot("call")
            t+=ln["dur"]+0.1
        T=t
        await at(T); await api("endCall()"); audio("docs/vid2/ding.mp3",T+0.1); await api("push('!! Rachel Kim - Court date moved','u')"); post(RACHEL)
        audio(L["narr"]["save"]["file"],T+0.4); await api("callout('On the desk phone in 41 s · Call back = one softkey',1000,760)")
        await at(T+2.4); await shot("phone")
        await at(T+5.0); await api("callout('')"); await api("dash()"); await api("zoom(900,0,1.18)")
        await at(T+6.2); await api("callout('Transcript · AI summary · matter · assigned · XML the phone receives',1080,700)")
        await at(T+7.2); await shot("inbox")
        await at(T+8.6); await api("callout('')"); await api("back()"); audio(L["narr"]["routine"]["file"],T+8.7)
        await api("newCall('Priya Desai','+1 (555) 330-4410 · incoming · Quinn answering','PD')"); audio("docs/vid2/ring.mp3",T+10.2)
        await at(T+12.0); await api("answer()")
        t2=T+12.3
        for i,ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"],t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==1: await at(t2+3.0); await shot("routine")
            t2+=ln["dur"]+0.1
        T2=t2
        await at(T2); await api("endCall()"); audio("docs/vid2/ding.mp3",T2+0.1); post(PRIYA); await api("callout('Routed to billing · not on the attorney phone',1000,760)")
        await at(T2+1.8); await shot("routed")
        await at(T2+3.4); await api("end()"); audio(L["narr"]["cta"]["file"],T2+3.8)
        await at(T2+4.8); await shot("end"); await at(T2+8.4)
        total=now(); await ctx.close(); await b.close()
    json.dump({"audio":AUDIO,"total":total},open(f"{ROOT}/docs/vid7/timeline.json","w"),indent=1); print("recorded",round(total,1))
asyncio.run(main())
