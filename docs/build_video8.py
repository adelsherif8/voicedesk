"""Harbor & Vine Realty — listings-board format: qualification checklist fills, inquiry pins onto the listing, dashboard reveal."""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright
ROOT="/Users/adel/Desktop/GHAI/voicedesk"; OUT=f"{ROOT}/docs/vid_out"; FR=f"{ROOT}/docs/vid8/frames"
L=json.load(open(f"{ROOT}/docs/vid8/lines.json")); AUDIO=[]
def post(rec): urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/realty",data=json.dumps(rec).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=20)
OMAR={"name":"Omar Haddad","phone":"+1 555 771 4432","email":"omar.h@mail.com","intent":"Inquiry · 302 Vine St #5B","outcome":"Showing booked · Ben Carter","appointment":"Sat 11:00 AM","summary":"Zillow inquiry. Budget $450–500K, pre-approved (Chase), moving in 60 days. Showing booked Saturday 11 AM with Ben; details texted.","listing":"L2","source":"Zillow","budget":"$450–500K","preapproved":True,"lender":"Chase","timeline":"60 days","musts":"2BR, parking","score":88,"agent":"Ben Carter","kind":"buyer","response_secs":4}
SUSAN={"name":"Susan Park","phone":"+1 555 630 8810","email":"susan.p@mail.com","intent":"Seller · what is my home worth?","outcome":"CMA appointment · Ben Carter","appointment":"Tue 5:30 PM","summary":"Seller call: 3BR in Cedar Hills, thinking of listing in spring. Booked a comparative market analysis visit Tuesday 5:30 PM with Ben.","source":"Website","kind":"seller","address":"41 Cedar Hills Rd","timeline":"Spring","score":80,"agent":"Ben Carter","response_secs":4}
async def main():
    os.makedirs(FR,exist_ok=True); shutil.rmtree(OUT,ignore_errors=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={"width":1920,"height":1080},record_video_dir=OUT,record_video_size={"width":1920,"height":1080})
        pg=await ctx.new_page(); await pg.goto(f"file://{ROOT}/docs/stage8.html"); await pg.frame_locator("#frame").locator(".lst").first.wait_for(timeout=15000); await pg.wait_for_timeout(600)
        t0=time.time(); now=lambda: time.time()-t0
        async def at(t):
            d=t-now()
            if d>0: await pg.wait_for_timeout(int(d*1000))
        async def api(c): await pg.evaluate(f"api.{c}")
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f,t): AUDIO.append((f"{ROOT}/{f}",t))
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"],0.5)
        await at(4.8); await api("hook(2)"); await at(5.6); await shot("hook")
        await at(7.4); await api("board()"); await at(8.4); await shot("board")
        await at(8.8); await api("call('Incoming · Zillow inquiry · answered in 4 s','Omar Haddad','+1 (555) 771-4432 · 302 Vine St #5B')"); audio("docs/vid2/ring.mp3",8.9)
        await at(10.6); await api("answer()")
        t=10.9; beats={3:[("chk(1,'$450–500K')",1.2),("chk(2,'Chase')",2.6),("chk(3,'60 days')",4.2)],4:[("score(88,'strong fit · 302 Vine')",0.8)]}
        for i,ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"],t); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            for c,off in beats.get(i,[]): await at(t+off); await api(c)
            if i==3: await at(t+4.6); await shot("qualify")
            t+=ln["dur"]+0.1
        T=t
        await at(T); await api("endCall()"); audio("docs/vid2/ding.mp3",T+0.1); await api("chk(4,'Sat 11 AM · Ben')"); await api("pin('L2','booked','Omar · Sat 11 AM')"); await api("kp(4,2,1)"); post(OMAR)
        audio(L["narr"]["save"]["file"],T+0.4); await api("callout('Showing booked · pinned to the listing · notes to Follow Up Boss',620,560)")
        await at(T+2.4); await shot("pinned")
        await at(T+5.0); await api("callout('')"); await api("cool('L2')"); await api("hide()"); await api("dash()"); await api("zoom(900,0,1.18)")
        await at(T+6.2); await api("callout('Listings board · lead score · agent calendars — live',1000,700)")
        await at(T+7.2); await shot("dash")
        await at(T+8.4); await api("callout('')"); await api("back()"); audio(L["narr"]["seller"]["file"],T+8.5)
        await api("call('Incoming · seller · website','Susan Park','+1 (555) 630-8810 · 41 Cedar Hills Rd')"); audio("docs/vid2/ring.mp3",T+9.8)
        await at(T+11.6); await api("answer()")
        t2=T+11.9
        for i,ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"],t2); await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i==1: await at(t2+2.0); await api("chk(3,'Spring')"); await api("chk(4,'CMA · Tue 5:30 PM')"); await api("score(80,'listing appointment')"); await at(t2+3.4); await shot("seller")
            t2+=ln["dur"]+0.1
        T2=t2
        await at(T2); await api("endCall()"); audio("docs/vid2/ding.mp3",T2+0.1); await api("kp(5,2,2)"); post(SUSAN); await api("callout('Listing appointment on Ben\\'s calendar · CRM updated',620,560)")
        await at(T2+1.8); await shot("sellerbooked")
        await at(T2+3.2); await api("end()"); audio(L["narr"]["cta"]["file"],T2+3.6)
        await at(T2+4.6); await shot("end"); await at(T2+7.8)
        total=now(); await ctx.close(); await b.close()
    json.dump({"audio":AUDIO,"total":total},open(f"{ROOT}/docs/vid8/timeline.json","w"),indent=1); print("recorded",round(total,1))
asyncio.run(main())
