// Bunker Board shared state (Only Friends, Monday 11-16). The control dock and the on-air browser source run in
// the same OBS, so they share localStorage; BroadcastChannel + a poll keep the board in step with every tap.
const POOL = [
  { id: "matt", name: "Matt" }, { id: "nikki", name: "Nikki" }, { id: "melissa", name: "Melissa" },
  { id: "jouhan", name: "Jouhan" }, { id: "sam", name: "Sam" }, { id: "landon", name: "Landon" },
  { id: "jesse", name: "Jesse" }, { id: "brian", name: "Brian" }, { id: "guapo", name: "Guapo" },
  { id: "conrad", name: "Conrad" }, { id: "brent", name: "Brent" },
];
const PANEL = ["matt", "nikki", "melissa", "jouhan"];   // whose bunkers are on the board, left to right
const KEY = "of-bunker-state-v1";
const HAS_IMG = new Set(["matt", "jouhan", "nikki", "melissa", "sam", "landon", "jesse", "brian", "guapo", "conrad", "brent"]);

function blank(seats) {
  const b = {}; PANEL.forEach(p => b[p] = []);
  return { mode: "hide", seats: seats || 3, bunkers: b, locked: [], last: null, rev: 0 };
}
function load() {
  try { const s = JSON.parse(localStorage.getItem(KEY)); if (s && s.bunkers) return s; } catch (e) {}
  return blank();
}
let chan = null; try { chan = new BroadcastChannel("of-bunker"); } catch (e) {}
function save(s) {
  s.rev = (s.rev || 0) + 1;
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {}
  try { chan && chan.postMessage(s); } catch (e) {}
}
function person(id) { return POOL.find(p => p.id === id) || { id, name: id }; }
function headHTML(id, cls) {
  const p = person(id);
  return HAS_IMG.has(id)
    ? `<div class="head ${cls || ""}"><img src="heads/${id}.webp" alt=""><span>${p.name}</span></div>`
    : `<div class="head ${cls || ""} noimg"><b>${p.name[0]}</b><span>${p.name}</span></div>`;
}
function tally(s) {
  const n = {}; POOL.forEach(p => n[p.id] = 0);
  Object.values(s.bunkers).forEach(list => list.forEach(id => n[id]++));
  return n;
}
function subscribe(fn) {
  let rev = -1;
  const apply = s => { if (s && s.rev !== rev) { rev = s.rev; fn(s); } };
  apply(load());
  chan && (chan.onmessage = e => apply(e.data));
  window.addEventListener("storage", e => { if (e.key === KEY) apply(load()); });
  setInterval(() => apply(load()), 400);
}
