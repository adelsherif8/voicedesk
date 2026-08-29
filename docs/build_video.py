"""Marketing video v2 — hook → phone call + live dashboard → zoomed reveal → CTA.
Records docs/stage.html with Playwright, then muxes narration + agent voice + sfx with ffmpeg.
Run: .venv/bin/python docs/build_video.py   (needs local VoiceDesk on :8099 with a clean DB)
"""
import asyncio, json, os, subprocess, time, urllib.request, glob, shutil
from playwright.async_api import async_playwright

ROOT = "/Users/adel/Desktop/GHAI/voicedesk"
OUT = f"{ROOT}/docs/vid_out"
FRAMES = f"{ROOT}/docs/vid2/frames"
LINES = json.load(open(f"{ROOT}/docs/vid/lines.json"))
NARR = json.load(open(f"{ROOT}/docs/vid2/narr.json"))
AUDIO = []   # (file, start_seconds)
SHOTS = {}   # name -> time (screenshots for tuning)

def post_reservation():
    body = json.dumps({"name": "Jenna Marlowe", "phone": "+1 555 412 7788", "email": "jenna@mail.com",
        "intent": "Store apartment items while traveling", "outcome": "Reserved 10x10",
        "appointment": "Tour Monday 2:00 PM",
        "summary": "Couch, bed, and ~15 boxes. Reserved a 10x10 unit, move-in Monday, tour booked.",
        "unit_size": "10x10", "move_in": "Monday", "monthly_price": 110}).encode()
    urllib.request.urlopen(urllib.request.Request("http://localhost:8099/ingest/receptionist", data=body,
        headers={"Content-Type": "application/json"}, method="POST"), timeout=20)

async def main():
    os.makedirs(FRAMES, exist_ok=True); shutil.rmtree(OUT, ignore_errors=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=OUT,
                                  record_video_size={"width": 1920, "height": 1080})
        pg = await ctx.new_page()
        await pg.goto(f"file://{ROOT}/docs/stage.html")
        await pg.wait_for_selector("#dash")
        await pg.frame_locator("#dash").locator(".card").first.wait_for(timeout=15000)
        await pg.wait_for_timeout(600)
        t0 = time.time()
        def now(): return time.time() - t0
        async def at(t):  # sleep until timeline second t
            d = t - now()
            if d > 0: await pg.wait_for_timeout(int(d * 1000))
        async def api(call): await pg.evaluate(f"api.{call}")
        async def shot(name): await pg.screenshot(path=f"{FRAMES}/{name}.png")
        def audio(f, t): AUDIO.append((f, t))

        # ---- HOOK (0–8s)
        await at(0.4); await api("hook(1)"); audio(NARR["n_hook"]["file"], 0.5)
        await at(4.4); await api("hook(2)")
        await at(5.5); await shot("hook")
        # ---- SCENE + incoming call
        await at(8.2); await api("scene()")
        await at(8.7); await api("incoming()"); audio(f"{ROOT}/docs/vid2/ring.mp3", 8.7); audio(f"{ROOT}/docs/vid2/ring.mp3", 10.7)
        await at(10.0); await shot("incoming")
        await at(12.3); await api("answer()"); await api("caption('Answers on the first ring — 24/7','fa-phone-volume')")
        # ---- conversation
        t = 12.7
        caps = {2: ("Qualifies the caller", "fa-user-check"), 4: ("Quotes the right unit — instantly", "fa-box"),
                6: ("Reserves + books the tour, in-call", "fa-calendar-check")}
        for i, ln in enumerate(LINES):
            await at(t); audio(f"{ROOT}/{ln['file']}", t)
            await api(f"say({json.dumps(ln['speaker'])},{json.dumps(ln['text'])})")
            if i in caps: await api(f"caption({json.dumps(caps[i][0])},{json.dumps(caps[i][1])})")
            if i == 4: await at(t + 2.0); await shot("call")
            t += ln["dur"] + 0.35
        # ---- call ends → save → zoom reveal
        T = t
        await at(T); await api("endCall()"); await api("caption('')"); audio(f"{ROOT}/docs/vid2/ding.mp3", T + 0.2)
        post_reservation()
        await at(T + 0.5); audio(NARR["n_save"]["file"], T + 0.6)
        await api("zoom(1180,330,1.45)")
        await at(T + 3.6); await api("callout('Saved to CRM — no human touched it',905,690)")
        await at(T + 4.6); await shot("saved")
        await at(T + 6.2); await api("callout('')")
        dash = next(f for f in pg.frames if "/agent/" in f.url)
        await dash.evaluate("document.querySelector('.tab[data-tab=\"reservations\"]').click()")
        await api("zoom(800,430,1.45)")
        await at(T + 7.4); await api("callout('10×10 reserved · tour booked · $110/mo',1090,470)")
        await at(T + 8.6); await shot("reservation")
        # ---- END CARD
        await at(T + 10.6); await api("end()"); audio(NARR["n_cta"]["file"], T + 11.0)
        await at(T + 12.0); await shot("end")
        await at(T + 15.0)
        total = now()
        await ctx.close(); await b.close()
    webm = glob.glob(f"{OUT}/*.webm")[0]
    json.dump({"audio": AUDIO, "total": total}, open(f"{ROOT}/docs/vid2/timeline.json", "w"), indent=1)
    mux(webm, total)

def mux(webm, total):
    inputs, chains, tags = ["-i", webm], [], []
    for i, (f, t) in enumerate(AUDIO):
        inputs += ["-i", f]
        chains.append(f"[{i+1}:a]adelay={int(t*1000)}|{int(t*1000)}[a{i}]"); tags.append(f"[a{i}]")
    fc = ";".join(chains) + f";{''.join(tags)}amix=inputs={len(AUDIO)}:normalize=0:dropout_transition=0,apad[aout]"
    mp4 = f"{ROOT}/docs/demo-storage.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
                    "-map", "0:v:0", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", mp4], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf",
                    "fps=12,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4",
                    f"{ROOT}/docs/demo-storage.gif"], check=True)
    print("done", mp4, f"{total:.1f}s")

asyncio.run(main())
