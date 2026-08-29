import asyncio, json, urllib.request
from playwright.async_api import async_playwright
URL="http://localhost:8099/agent/receptionist"
OUT="/Users/adel/Desktop/GHAI/voicedesk/docs/vid_out"
LINES=json.load(open("/Users/adel/Desktop/GHAI/voicedesk/docs/vid/lines.json"))

def post_reservation():
    body=json.dumps({"name":"Jenna Marlowe","phone":"+1 555 412 7788","email":"jenna@mail.com",
        "intent":"Store apartment items while traveling","outcome":"Reserved 10x10",
        "appointment":"Tour Monday 2:00 PM","summary":"Couch, bed, and ~15 boxes. Reserved a 10x10 unit, move-in Monday, tour booked.",
        "unit_size":"10x10","move_in":"Monday","monthly_price":110}).encode()
    urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/receptionist",data=body,
        headers={"Content-Type":"application/json"},method="POST"),timeout=20)

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={"width":1200,"height":1000},record_video_dir=OUT,
            record_video_size={"width":1200,"height":1000},device_scale_factor=2)
        pg=await ctx.new_page(); await pg.goto(URL); await pg.wait_for_timeout(1000)
        # 2s intro (matches 2s audio lead), overview visible
        await pg.wait_for_timeout(1000)
        # reveal calling banner
        await pg.evaluate("""()=>{const c=document.getElementById('calling');c.classList.add('show');
            document.getElementById('callFrom').textContent='Jenna Marlowe · +1 555 412 7788';
            const t=document.getElementById('callTxt');t.style.maxWidth='58%';t.style.fontSize='.95rem';t.style.color='#eaf0ff';}""")
        for ln in LINES:
            sp='Alex' if ln['speaker']=='alex' else 'Caller'
            color='#8ff0c9' if ln['speaker']=='alex' else '#a9c3ff'
            await pg.evaluate(f"""()=>{{document.getElementById('callTxt').innerHTML=
                `<b style="color:{color}">{sp}</b> &nbsp; {json.dumps(ln['text'])[1:-1]}`;}}""")
            await pg.wait_for_timeout(int(ln['dur']*1000)+150)
        # call ends -> save reservation
        await pg.evaluate("""()=>{document.getElementById('callFrom').textContent='Call ended · reservation saved';
            document.getElementById('callTxt').innerHTML='<b style=\\"color:#8ff0c9\\">✓ Reserved 10×10 · tour Monday 2 PM</b>';}""")
        post_reservation()
        await pg.wait_for_timeout(3800)  # dashboard poll picks it up (slide-in + stat flash)
        # switch to Reservations tab to show the unit card
        await pg.click('.tab[data-tab="reservations"]')
        await pg.wait_for_timeout(3500)
        await ctx.close(); await b.close()
        print("recorded")
asyncio.run(main())
