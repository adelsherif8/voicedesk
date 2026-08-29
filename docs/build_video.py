"""Marketing video v3 — number hook → rental call → save reveal → tenant gate call → CTA (~55 s).
Records docs/stage.html with Playwright, muxes narration + voices + sfx with ffmpeg, exports mp4 + gif + 15 s vertical.
Run: .venv/bin/python docs/build_video.py   (needs local VoiceDesk on :8099 with a clean DB)
"""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright

ROOT = "/Users/adel/Desktop/GHAI/voicedesk"
OUT = f"{ROOT}/docs/vid_out"
FRAMES = f"{ROOT}/docs/vid3/frames"
L = json.load(open(f"{ROOT}/docs/vid3/lines.json"))
AUDIO = []

def post(rec):
    urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/receptionist", data=json.dumps(rec).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=20)

JENNA = {"name": "Jenna Marlowe", "phone": "+1 555 412 7788", "email": "jenna@mail.com",
    "intent": "Store apartment items while traveling", "outcome": "Reserved 10x10", "appointment": "Tour Monday 2:00 PM",
    "summary": "Couch, bed, and ~15 boxes. Reserved a 10x10 unit, move-in Monday, tour booked, confirmation texted.",
    "call_type": "rental", "unit_size": "10x10", "move_in": "Monday", "monthly_price": 110}
MARK = {"name": "Mark Reyes", "phone": "+1 555 887 2210", "intent": "Gate code not working", "outcome": "Access restored",
    "summary": "Tenant locked out at the gate. Verified phone on account, issued new gate code 4 8 1 9, gate opened.",
    "call_type": "access", "unit": "D-12", "gate_code": "4 8 1 9"}

async def main():
    os.makedirs(FRAMES, exist_ok=True); shutil.rmtree(OUT, ignore_errors=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=OUT,
                                  record_video_size={"width": 1920, "height": 1080})
        pg = await ctx.new_page()
        await pg.goto(f"file://{ROOT}/docs/stage.html")
        await pg.frame_locator("#dash").locator(".card").first.wait_for(timeout=15000)
        await pg.wait_for_timeout(600)
        t0 = time.time()
        def now(): return time.time() - t0
        async def at(t):
            d = t - now()
            if d > 0: await pg.wait_for_timeout(int(d * 1000))
        async def api(call): await pg.evaluate(f"api.{call}")
        async def shot(name): await pg.screenshot(path=f"{FRAMES}/{name}.png")
        def audio(f, t): AUDIO.append((f"{ROOT}/{f}", t))
        dash = lambda: next(f for f in pg.frames if "/agent/" in f.url)
        async def tab(name): await dash().evaluate(f"document.querySelector('.tab[data-tab=\"{name}\"]').click()")

        # HOOK 0–7.9
        await at(0.4); await api("hook(1)"); audio(L["narr"]["hook"]["file"], 0.5)
        await at(4.2); await api("hook(2)")
        await at(5.2); await shot("hook")
        # SCENE + call 1 (rental)
        await at(6.8); await api("scene()")
        await at(7.0); await api("incoming()"); audio("docs/vid2/ring.mp3", 7.0)
        await at(7.9); await shot("incoming")
        await at(8.7); await api("answer()"); await api("caption('Answers on the first ring — 24/7','fa-phone-volume')")
        t = 9.0
        caps = {1: ("Qualifies the caller", "fa-user-check"), 2: ("Quotes from live inventory", "fa-warehouse"), 4: ("Reserves + books the tour, in-call", "fa-calendar-check")}
        for i, ln in enumerate(L["call1"]):
            await at(t); audio(ln["file"], t)
            await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i in caps: await api(f"caption({json.dumps(caps[i][0])},{json.dumps(caps[i][1])})")
            if i == 2: await at(t + 2.5); await shot("call")
            t += ln["dur"] + 0.25
        T = t  # ≈ 33.5
        await at(T); await api("endCall()"); await api("caption('')"); audio("docs/vid2/ding.mp3", T + 0.1)
        post(JENNA); audio(L["narr"]["save"]["file"], T + 0.4)
        await api("zoom(1180,330,1.45)")
        await at(T + 3.0); await api("callout('Saved + inventory updated — no human touched it',905,690)")
        await at(T + 4.0); await shot("saved")
        # call 2 (tenant / gate)
        await at(T + 4.9); await api("callout('')"); await api("zoom(0,0,null)")
        audio(L["narr"]["tenant"]["file"], T + 4.6)
        await api("newCall('Mark Reyes','+1 (555) 887-2210 · tenant · unit D-12')"); audio("docs/vid2/ring.mp3", T + 6.4)
        await at(T + 8.2); await api("answer()"); await api("caption('Existing tenants too — 3 of 4 callers','fa-key')")
        t2 = T + 8.9
        for i, ln in enumerate(L["call2"]):
            await at(t2); audio(ln["file"], t2)
            await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i == 1: await api("caption('Verifies identity · resets gate code · logs it','fa-shield-halved')"); await at(t2 + 3.0); await shot("tenant")
            t2 += ln["dur"] + 0.25
        T2 = t2
        await at(T2); await api("endCall('Gate code reset · gate open · logged')"); await api("caption('')"); audio("docs/vid2/ding.mp3", T2 + 0.1)
        post(MARK); await tab("tenants"); await api("zoom(800,430,1.45)")
        await at(T2 + 2.5); await api("callout('Tenant call logged · code issued',1090,470)")
        await at(T2 + 3.5); await shot("tenantlog")
        # END
        await at(T2 + 4.8); await api("end()"); audio(L["narr"]["cta"]["file"], T2 + 5.1)
        await at(T2 + 6.0); await shot("end")
        await at(T2 + 8.3)
        total = now()
        await ctx.close(); await b.close()
    webm = glob.glob(f"{OUT}/*.webm")[0]
    json.dump({"audio": AUDIO, "total": total}, open(f"{ROOT}/docs/vid3/timeline.json", "w"), indent=1)
    mux(webm, total)

def mux(webm, total):
    inputs, chains, tags = ["-i", webm], [], []
    for i, (f, t) in enumerate(AUDIO):
        inputs += ["-i", f]; chains.append(f"[{i+1}:a]adelay={int(t*1000)}|{int(t*1000)}[a{i}]"); tags.append(f"[a{i}]")
    fc = ";".join(chains) + f";{''.join(tags)}amix=inputs={len(AUDIO)}:normalize=0:dropout_transition=0,apad[aout]"
    mp4 = f"{ROOT}/docs/demo-storage.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", mp4], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf",
                    "fps=10,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5",
                    f"{ROOT}/docs/demo-storage.gif"], check=True)
    print("done", mp4, f"{total:.1f}s")

asyncio.run(main())
