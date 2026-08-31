"""Luca's Trattoria — floor plan + kitchen ticket printer format; ticket prints line by line as the order is taken."""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright
ROOT="/Users/adel/Desktop/GHAI/voicedesk"; OUT=f"{ROOT}/docs/vid_out"; FR=f"{ROOT}/docs/vid10/frames"
L=json.load(open(f"{ROOT}/docs/vid10/lines.json")); AUDIO=[]
def post(rec): urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/restaurant",data=json.dumps(rec).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=20)
SAM={"eighty_six":"asked for Branzino → offered rigatoni / margherita","ready":True,"minutes":9,"name":"Sam Ortega","phone":"+1 555 402 1180","intent":"Takeout · 2 pizzas + salad + tiramisu","outcome":"Order to kitchen · $48.50","appointment":"Pickup 7:15 PM","summary":"Takeout: 2× Margherita (one no basil), 1× Caesar, 1× Tiramisu (upsold). Tree-nut allergy flagged to kitchen. Read back total $48.50; paid by card; ticket printed.","kind":"order","items":[["Margherita pizza",2,32.0],["Caesar salad",1,9.5],["Tiramisu",1,7.0]],"total":48.5,"pickup":"7:15 PM","upsell":"Tiramisu","allergy":"Tree nuts — flagged to kitchen","paid":True}
DANA={"name":"Dana Whitfield","phone":"+1 555 620 4410","intent":"Reservation · 4 · 7:30 PM","outcome":"Table T4 · confirmed","appointment":"Tonight 7:30 PM · party of 4","summary":"Anniversary dinner for four at 7:30. Seated at T4 (window), note added: anniversary — comp dessert. Confirmation texted.","kind":"reservation","party":4,"time":"7:30 PM","table":"T4","occasion":"Anniversary","source":"phone"}
async def main():
    os.makedirs(FR,exist_ok=True); shutil.rmtree(OUT,ignore_errors=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={"width":1920,"height":1080},record_video_dir=OUT,record_video_size={"width":1920,"height":1080})
        pg=await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage10.html"); await pg.frame_locator("#frame").locator(".tbl").first.wait_for(timeout=15000); await pg.wait_for_timeout(600)
        t0=time.time(); now=lambda: time.time()-t0
        async def at(t):
            d=t-now()
            if d>0: await pg.wait_for_timeout(int(d*1000))
        async def api(c): await pg.evaluate(f"api.{c}")
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f,t): AUDIO.append((f"{ROOT}/{f}",t))
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"],0.5)
        await at(5.4); await api("hook(2)"); await at(6.2); await shot("hook")
        await at(9.0); await api("svc()"); await at(9.8); await shot("service")
        await at(10.2); await api("call('Incoming · 7:12 PM · answered in 1 s','Sam Ortega','+1 (555) 402-1180')"); audio("docs/vid2/ring.mp3",10.3)
        await at(11.8); await api("answer()")
        t=12.1
        L1=L["call1"]
        beats={1:[("eb()",1.2)],
               2:[("ticket('Sam O.','7:15 PM')",0.8),("line('<div class=\"eb86\">86: asked for branzino → offered rigatoni / margherita</div>')",1.6)],
               3:[("line('<div class=\"li\"><span>2× Margherita pizza</span><span>$32.00</span></div>')",1.2),("line('<div class=\"mod\">↳ one no basil</div>')",2.4),("line('<div class=\"li\"><span>1× Caesar salad</span><span>$9.50</span></div>')",3.4)],
               4:[("line('<div class=\"al\">!! ALLERGY: TREE NUTS</div>')",2.6),("kp('kD','3')",2.7)],
               5:[("line('<div class=\"li\"><span>1× Tiramisu</span><span>$7.00</span></div>')",0.4),("line('<div class=\"up\">↳ upsold by Gia</div>')",0.8)],
               6:[("line('<div class=\"tot\"><span>TOTAL · PAID</span><span>$48.50</span></div>')",1.2),("line('<div class=\"ft\">read back to caller ✓ · receipt texted</div>')",2.6),("kp('kB','$128.00')",1.4),("tmin(1)",3.0)]}
        for i,ln in enumerate(L1):
            await at(t); audio(ln["file"],t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            for c,off in beats.get(i,[]): await at(t+off); await api(c)
            if i==2: await at(t+1.6); await shot("eb")
            if i==4: await at(t+3.0); await shot("order")
            t+=ln["dur"]+0.1
        T=t
        await at(T); await api("endCall()"); audio("docs/vid2/ding.mp3",T+0.1); post(SAM)
        audio(L["narr"]["save"]["file"],T+0.4); await api("callout('86 swap · allergy flagged · $7 upsell · ticket with timer',1200,300)")
        await at(T+2.4); await api("tmin(4)"); await shot("ticket")
        await at(T+4.6); await api("tmin(9)"); await api("readyNow()"); await api("callout('Kitchen bumps it → customer texted: ready for pickup',1200,300)")
        await at(T+5.8); await shot("ready")
        await at(T+7.4); await api("callout('')"); await api("hide()"); await api("dash()"); await api("zoom(900,0,1.18)")
        await at(T+8.6); await api("callout('Floor plan · 86 board · covers by the hour · KDS tickets — live',1000,740)")
        await at(T+9.6); await shot("dash")
        await at(T+10.8); await api("callout('')"); await api("back()"); audio(L["narr"]["res"]["file"],T+10.9)
        await api("call('Incoming · 7:14 PM · answered in 1 s','Dana Whitfield','+1 (555) 620-4410')"); audio("docs/vid2/ring.mp3",T+12.4)
        await at(T+14.2); await api("answer()")
        t2=T+14.5
        for i,ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"],t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==1: await at(t2+2.2); await api("reserve('T4','Dana · 7:30 · anniversary')"); await api("kp('kC','16')"); await api("wave('7',20)"); await at(t2+3.4); await shot("reserve")
            t2+=ln["dur"]+0.1
        T2=t2
        await at(T2); await api("endCall()"); audio("docs/vid2/ding.mp3",T2+0.1); post(DANA); await api("callout('T4 at 7:30 · anniversary note for the team · confirmation texted',340,748)")
        await at(T2+1.8); await shot("reserved")
        await at(T2+3.2); await api("end()"); audio(L["narr"]["cta"]["file"],T2+3.6)
        await at(T2+4.6); await shot("end"); await at(T2+7.8)
        total=now(); await ctx.close(); await b.close()
    json.dump({"audio":AUDIO,"total":total},open(f"{ROOT}/docs/vid10/timeline.json","w"),indent=1); print("recorded",round(total,1))
asyncio.run(main())
