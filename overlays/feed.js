// Shared feed loader for the Only Friends OBS overlays. ?demo=1 animates fake data; ?feed=URL overrides the source.
(function () {
  const q = new URLSearchParams(location.search);
  const FEED = q.get("feed") ||
    "https://api.github.com/repos/berkey11/of-mission-control/contents/feed.json?ref=overlay-feed";
  // Without a token GitHub allows 60 requests an hour per IP, so every overlay on the machine shares one fetch through
  // localStorage (OBS browser sources share storage) at most every 70 s. ?token=<read-only GitHub token> allows 10 s.
  const TOKEN = q.get("token");
  const EVERY = Math.max(TOKEN ? 5 : 65, +(q.get("every") || (TOKEN ? 10 : 70))) * 1000;
  const KEY = "of-overlay-feed";
  let backoff = 0;

  function cached() { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  async function load() {
    const c = cached();
    if (c && Date.now() - c.t < EVERY - 2000) return c.data;       // another overlay fetched it moments ago
    try { localStorage.setItem(KEY, JSON.stringify({ t: Date.now(), data: c ? c.data : null })); } catch (e) {}   // claim this round
    const h = { Accept: "application/vnd.github.raw+json" };
    if (TOKEN) h.Authorization = "Bearer " + TOKEN;
    const r = await fetch(FEED, { cache: "no-cache", headers: h });
    if (r.status === 403 || r.status === 429) { backoff = Math.min(backoff + 1, 5); throw new Error("rate limited"); }
    if (!r.ok) throw new Error("HTTP " + r.status);
    backoff = 0;
    const data = await r.json();
    try { localStorage.setItem(KEY, JSON.stringify({ t: Date.now(), data })); } catch (e) {}
    return data;
  }

  function demo(onData) {
    const goals = [{ at: 100, label: "New emote unlocks. Members vote on it" },
                   { at: 200, label: "Second new emote. Members vote again" },
                   { at: 300, label: "Third emote + a bonus After Hours" }];
    const stops = [{ at: 10, label: "An off-limits question" }, { at: 25, label: "An untold story from a big game" },
                   { at: 50, label: "Chat picks a hand, Matt breaks it down" }, { at: 100, label: "Bonus members-only episode" }];
    let m = 92, g = 6;
    const names = ["RiverRat22", "NitNation", "3BetBrian", "FoldEquity", "OverbetOllie"];
    const by = {};
    function frame() {
      const kind = Math.random() < 0.5 ? "gift" : "join";
      let recent = [];
      if (kind === "gift") { const n = [1, 1, 5, 2, 10][Math.floor(Math.random() * 5)]; const who = names[Math.floor(Math.random() * names.length)];
        g += n; m += n; by[who] = (by[who] || 0) + n; recent = [{ kind, name: who, n, at: new Date().toISOString() }]; }
      else { m += 1; recent = [{ kind, name: names[Math.floor(Math.random() * names.length)], at: new Date().toISOString() }]; }
      const next = goals.find(x => m < x.at) || null;
      const from = Math.max(0, ...goals.filter(x => m >= x.at).map(x => x.at));
      const tnext = stops.find(x => g < x.at) || null;
      const top = Object.entries(by).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([name, n]) => ({ name, n }));
      onData({ members: m, goal: { from, next, all: goals }, train: { gifts: g, stops, reached: stops.filter(x => g >= x.at).length, next: tnext, top },
               recent, demo: true, updatedAt: new Date().toISOString() });
    }
    frame(); setInterval(frame, 4000);
  }

  window.OFFeed = function (onData) {
    if (q.get("demo")) return demo(onData);
    const tick = async () => {
      try { const d = await load(); if (d) onData(d); } catch (e) { console.log("[OF overlay]", e.message); }
      setTimeout(tick, Math.min(EVERY, 15000) * (1 + backoff * 2));   // check the shared copy often; fetch only when stale
    };
    tick();
  };

  window.OFSeen = function () {           // remembers which recent events were already shown (per page session)
    const seen = new Set(); let primed = false;
    return function fresh(list) {
      const out = [];
      for (const e of list || []) { const k = e.kind + e.name + e.at + (e.n || ""); if (!seen.has(k)) { seen.add(k); if (primed) out.push(e); } }
      primed = true; return out;
    };
  };
})();
