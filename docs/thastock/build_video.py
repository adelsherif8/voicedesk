"""Thastock marketing video — NEW format: a real screen-recording of the live product,
annotated on a trading-day clock. No phone call, no dashboard-in-a-frame; the site IS the stage."""
import asyncio, json, os, subprocess, time, glob, shutil
from playwright.async_api import async_playwright

ROOT = "/Users/adel/Desktop/GHAI/voicedesk"
OUT = f"{ROOT}/docs/vid_out"; FR = f"{ROOT}/docs/thastock/frames"
N = json.load(open(f"{ROOT}/docs/thastock/vid/narr.json")); AUDIO = []

OVERLAY = """
(() => {
  const css = document.createElement('style');
  css.textContent = `
  #ov{position:fixed;inset:0;pointer-events:none;z-index:2147483647;font-family:'IBM Plex Mono',ui-monospace,monospace}
  #ovclock{position:fixed;right:34px;top:110px;background:#17120e;border:1px solid rgba(200,164,92,.5);
    color:#c8a45c;padding:10px 18px;font-size:20px;letter-spacing:.06em;box-shadow:0 16px 40px rgba(0,0,0,.6);
    display:flex;align-items:center;gap:12px;opacity:0;transition:opacity .5s}
  #ovclock.on{opacity:1}
  #ovclock i{width:9px;height:9px;border-radius:50%;background:#5fbf87;display:inline-block}
  #ovclock i.closed{background:#8d8377}
  #ovclock small{color:#8d8377;font-size:12px;letter-spacing:.18em;text-transform:uppercase}
  #ovco{position:fixed;left:50%;transform:translateX(-50%) translateY(14px);bottom:70px;background:#c8a45c;color:#17120e;
    font-family:Inter,system-ui,sans-serif;font-weight:700;font-size:25px;padding:15px 30px;
    box-shadow:0 24px 60px rgba(0,0,0,.55);opacity:0;transition:all .45s;display:flex;align-items:center;gap:14px}
  #ovco.on{opacity:1;transform:translateX(-50%) translateY(0)}
  #ovco b{font-family:'IBM Plex Mono',monospace;background:#17120e;color:#c8a45c;padding:3px 10px;font-size:20px}
  #ovend{position:fixed;inset:0;background:#17120e;color:#f0e9dc;display:flex;flex-direction:column;
    align-items:center;justify-content:center;text-align:center;opacity:0;transition:opacity .7s}
  #ovend.on{opacity:1}
  #ovend .bars{display:flex;align-items:flex-end;gap:6px;height:64px;margin-bottom:30px}
  #ovend .bars i{width:16px;background:#c8a45c}
  #ovend h2{font-family:'Playfair Display',Georgia,serif;font-size:78px;line-height:1.05;font-weight:800}
  #ovend h2 em{font-style:italic;color:#c8a45c}
  #ovend p{margin-top:26px;font-family:Inter,system-ui,sans-serif;font-size:24px;color:#a89d8e}
  #ovend p b{color:#f0e9dc}
  #ovend .st{margin-top:22px;font-size:14px;letter-spacing:.24em;text-transform:uppercase;color:#c8a45c}
  `;
  document.head.appendChild(css);
  const ov = document.createElement('div'); ov.id='ov';
  ov.innerHTML = `<div id="ovclock"><i class="closed"></i><span id="ovt">08:29 EST</span><small id="ovs">pre-market</small></div>
    <div id="ovco"><span id="ovcot"></span></div>
    <div id="ovend"><div class="bars"><i style="height:26px"></i><i style="height:42px"></i><i style="height:60px"></i></div>
      <h2>Stop missing the moves<br/><em>that matter.</em></h2>
      <p><b>Thastock</b> · AI market intelligence — built end to end by <b>Adel Atya</b><br/>thastock.com · free forever, $9/mo pro</p>
      <div class="st">Next.js · OpenAI · Market data APIs · SEC EDGAR · Vercel</div></div>`;
  document.body.appendChild(ov);
  window.ovClock = (t, s, open) => { const c=document.getElementById('ovclock');
    document.getElementById('ovt').textContent=t; document.getElementById('ovs').textContent=s;
    c.querySelector('i').className = open ? '' : 'closed'; c.classList.add('on'); };
  window.ovCallout = (html) => { const c=document.getElementById('ovco');
    if(!html){c.classList.remove('on');return;} document.getElementById('ovcot').innerHTML=html; c.classList.add('on'); };
  window.ovEnd = () => { document.getElementById('ovclock').classList.remove('on');
    document.getElementById('ovco').classList.remove('on'); document.getElementById('ovend').classList.add('on'); };
})();
"""

async def main():
    os.makedirs(FR, exist_ok=True); shutil.rmtree(OUT, ignore_errors=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=OUT,
                                  record_video_size={"width": 1920, "height": 1080})
        pg = await ctx.new_page()
        await pg.goto("https://thastock.com", wait_until="networkidle", timeout=90000)
        await pg.wait_for_timeout(1500)
        await pg.evaluate(OVERLAY)
        t0 = time.time(); now = lambda: time.time() - t0
        async def at(t):
            d = t - now()
            if d > 0: await pg.wait_for_timeout(int(d * 1000))
        async def shot(n): await pg.screenshot(path=f"{FR}/{n}.png")
        def audio(f, t): AUDIO.append((f, t))
        async def scroll(y, ms=1400):
            await pg.evaluate(f"window.scrollTo({{top:{y},behavior:'smooth'}})"); await pg.wait_for_timeout(ms)

        # 1 — hero, pre-market
        audio(N["hook"]["file"], 0.5)
        await at(0.8); await pg.evaluate("ovClock('08:29 EST','pre-market',false)")
        await at(3.0); await shot("hero")
        await at(6.4); await pg.evaluate("ovCallout('Your watchlist, read by AI <b>before the bell</b>')")
        await at(9.6); await pg.evaluate("ovCallout('')")
        # 2 — § 01 Morning Brief  (heading 1334)
        await at(10.4); await scroll(1200); await pg.evaluate("ovClock('08:30 EST','brief sent',false)")
        audio(N["brief"]["file"], 11.4)
        await at(12.8); await pg.evaluate("ovCallout('<b>08:30</b> AI brief — RSI, earnings, macro, per ticker')")
        await at(14.0); await shot("brief")
        await at(18.4); await pg.evaluate("ovCallout('')")
        # 3 — § 02 Alerts  (heading 2008), market open
        await at(19.2); await scroll(1880); await pg.evaluate("ovClock('09:41 EST','market open',true)")
        audio(N["alert"]["file"], 20.0)
        await at(21.4); await pg.evaluate("ovCallout('Fires on <b>price · RSI · volume · MA cross</b>')")
        await at(22.6); await shot("alerts")
        await at(26.0); await pg.evaluate("ovCallout('')")
        # 4 — § 03 AI Research + § 04 Insider Flow  (2685 / 2795)
        await at(26.8); await scroll(2560)
        audio(N["research"]["file"], 27.4)
        await at(28.6); await pg.evaluate("ovCallout('Drop a ticker → <b>thesis in seconds</b>')")
        await at(29.8); await shot("research")
        await at(32.8); await pg.evaluate("ovCallout('')")
        await at(33.4); await pg.evaluate("ovClock('11:06 EST','filing parsed',true)")
        audio(N["insider"]["file"], 33.8)
        await at(35.2); await pg.evaluate("ovCallout('<b>SEC Form 4</b> parsed live — CEO bought $2.1M')")
        await at(36.4); await shot("insider")
        await at(39.6); await pg.evaluate("ovCallout('')")
        # 5 — § 04 Screener (3252)
        await at(40.2); await scroll(3130)
        await at(41.6); await pg.evaluate("ovCallout('<b>8,000+</b> US equities screened live')")
        await at(42.6); await shot("screener")
        await at(45.0); await pg.evaluate("ovCallout('')")
        # 6 — Portfolio risk (3656)
        await at(45.6); await scroll(3530)
        await at(46.8); await pg.evaluate("ovCallout('Portfolio <b>stress-tested</b> against real drawdowns')")
        await at(47.8); await shot("portfolio")
        await at(50.2); await pg.evaluate("ovCallout('')")
        # 7 — Pricing comparison (3937)
        await at(50.8); await scroll(3860)
        audio(N["cta"]["file"], 51.4)
        await at(52.8); await pg.evaluate("ovCallout('Free forever → <b>$9/mo</b> · four tiers, shipped')")
        await at(53.8); await shot("pricing")
        await at(57.2); await pg.evaluate("ovCallout('')")
        # 8 — end card
        await at(58.2); await pg.evaluate("ovEnd()")
        await at(59.8); await shot("end")
        await at(62.6)
        total = now(); await ctx.close(); await b.close()
    webm = glob.glob(f"{OUT}/*.webm")[0]
    inputs, chains, tags = ["-i", webm], [], []
    for i, (f, t) in enumerate(AUDIO):
        inputs += ["-i", f"{ROOT}/{f}" if not f.startswith("/") else f]
        chains.append(f"[{i+1}:a]adelay={int(t*1000)}|{int(t*1000)}[a{i}]"); tags.append(f"[a{i}]")
    fc = ";".join(chains) + f";{''.join(tags)}amix=inputs={len(AUDIO)}:normalize=0:dropout_transition=0,apad[aout]"
    mp4 = f"{ROOT}/docs/thastock/demo-thastock.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", mp4], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf",
                    "fps=10,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5",
                    f"{ROOT}/docs/thastock/demo-thastock.gif"], check=True)
    print("done", round(total, 1))

asyncio.run(main())
