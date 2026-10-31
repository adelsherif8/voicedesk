// "Talk to this agent": asks our server for a call token, then joins with the Retell web SDK.
// The SDK's control requests go through our endpoint, so no Retell key ever reaches this page.
const SDK = "/static/vendor/retell-client-js-sdk-3.0.3.min.js";

const root = document.getElementById("talk");
const startBtn = root.querySelector(".talk-start");
const startLabel = startBtn.querySelector("span");
const hangBtn = root.querySelector(".talk-hang");
const soundBtn = root.querySelector(".talk-sound");
const statusEl = root.querySelector(".talk-status");
const maxSeconds = Number(root.dataset.maxSeconds);
const slug = root.dataset.slug;

let session = null;
let timer = null;
let finalState = null; // what to show once the session ends
let cancelled = false; // hung up before the session existed

function show(state, text) {
  root.dataset.state = state;
  statusEl.textContent = text;
  const busy = state === "connecting" || state === "live";
  startBtn.hidden = state === "live";
  startBtn.disabled = state === "connecting" || state === "limit";
  startLabel.textContent = state === "connecting" ? "Connecting..."
    : state === "idle" || state === "limit" ? "Talk to this agent" : "Talk again";
  hangBtn.hidden = !busy;
  if (!busy) soundBtn.hidden = true;
}

function micFailure(err) {
  const name = err && err.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access is blocked. Allow the microphone for this site in your browser settings, then try again.";
  }
  if (name === "NotFoundError") return "No microphone was found on this device.";
  return "Your browser could not open the microphone. Please try another browser.";
}

function clock(seconds) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function stopTimer() {
  if (timer) clearInterval(timer);
  timer = null;
}

function goLive() {
  const deadline = Date.now() + maxSeconds * 1000;
  const tick = () => {
    const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
    statusEl.textContent = `Live, ${clock(left)} left. Say hello.`;
    if (left === 0 && session) {
      finalState = ["ended", "The demo time limit was reached, so the call ended."];
      session.end();
    }
  };
  show("live", "");
  tick();
  timer = setInterval(tick, 1000);
  session.startAudioPlayback().catch(() => { soundBtn.hidden = false; });
}

function failure(err) {
  // Our endpoint's own friendly message, carried on the SDK's API error.
  const body = err && err.body;
  if (body && body.reason === "limit") finalState = ["limit", body.message];
  else if (body && body.message) finalState = ["error", body.message];
  else if (err && ["NotAllowedError", "NotFoundError", "NotReadableError", "SecurityError"].includes(err.name)) {
    finalState = ["mic-denied", micFailure(err)];
  } else if (!finalState && session && session.status === "connecting") {
    finalState = ["error", "The call could not connect. Please try again in a moment."];
  }
}

async function start() {
  cancelled = false;
  show("connecting", "Allow the microphone if your browser asks.");
  // Ask for the microphone first, so a refusal does not use up one of the visitor's calls.
  try {
    const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
    probe.getTracks().forEach((t) => t.stop());
  } catch (err) {
    show("mic-denied", micFailure(err));
    return;
  }
  if (cancelled) return;
  statusEl.textContent = "Connecting to the agent...";
  finalState = null;
  try {
    const { RetellClient } = await import(SDK);
    if (cancelled) return;
    const client = new RetellClient({
      key: "unused", // our endpoint holds the real key and ignores this
      fetch: () => fetch(`/api/web-call/${encodeURIComponent(slug)}`, { method: "POST" }),
    });
    session = client.createWebCall({
      agent_id: slug, // the server maps the page slug to the agent
      hooks: {
        onStatus: (status) => { if (status === "live") goLive(); },
        onError: failure,
        onEnd: () => {
          stopTimer();
          session = null;
          const [state, text] = finalState || ["ended", "Call ended. Thanks for trying the demo."];
          show(state, text);
        },
      },
    });
  } catch (err) {
    session = null;
    show("error", "The call could not start. Please try again in a moment.");
  }
}

startBtn.addEventListener("click", () => {
  if (!session) start();
});
hangBtn.addEventListener("click", () => {
  if (session) session.end();
  else {
    cancelled = true;
    show("idle", "");
  }
});
soundBtn.addEventListener("click", () => {
  if (session) session.startAudioPlayback().then(() => { soundBtn.hidden = true; }).catch(() => {});
});
window.addEventListener("pagehide", () => { if (session) session.end(); });

if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
  show("mic-denied", "This browser cannot open the microphone here. Please use a current browser over HTTPS.");
  startBtn.disabled = true;
} else {
  show("idle", "");
}
