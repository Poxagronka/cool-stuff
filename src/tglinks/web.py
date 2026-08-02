"""The public page. One file, no build step, no framework."""

from . import brand, graph, sheet

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>cool stuff</title>
{icon}
<style>
  :root {
    --bg: #0b0b0c;
    --raise: #121214;
    --line: #1f1f22;
    --line-hi: #34343a;
    --text: #ededf0;
    --dim: #77777f;
    --dimmer: #4a4a52;
    --ease: cubic-bezier(.2, .7, .3, 1);
  }
  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
  }
  * { box-sizing: border-box; }
  html { scrollbar-gutter: stable; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.55 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
          Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  ::selection { background: var(--text); color: var(--bg); }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 0 24px; }

  /* ---------- header ---------- */
  header {
    position: sticky; top: 0; z-index: 20;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    backdrop-filter: blur(16px) saturate(140%);
    border-bottom: 1px solid var(--line);
  }
  .bar { display: flex; align-items: baseline; gap: 14px; padding: 20px 0 14px; }
  .mark {
    display: inline-flex; align-items: center; gap: 9px;
    font-size: 13px; font-weight: 500; letter-spacing: .14em; text-transform: uppercase;
  }
  .glyph { flex: none; transform: translateY(1px); }
  .count {
    font-variant-numeric: tabular-nums; font-size: 13px; color: var(--dim);
    transition: opacity .25s var(--ease);
  }
  .count.busy { opacity: .35; }
  .who {
    margin-left: auto; font-size: 13px; color: var(--dim); text-decoration: none;
    transition: color .18s var(--ease);
  }
  .who:hover { color: var(--text); }

  .field { position: relative; padding-bottom: 16px; }
  .field input {
    width: 100%; padding: 13px 40px 13px 15px; font: inherit; font-size: 15px;
    color: var(--text); background: var(--raise);
    border: 1px solid var(--line); border-radius: 10px; outline: none;
    transition: border-color .2s var(--ease), background .2s var(--ease);
  }
  .field input::placeholder { color: var(--dimmer); }
  .field input:hover { border-color: var(--line-hi); }
  .field input:focus { border-color: var(--dim); background: #141417; }
  .field .clear {
    position: absolute; right: 12px; top: 12px; width: 22px; height: 22px;
    display: grid; place-items: center; border-radius: 6px; cursor: pointer;
    color: var(--dimmer); opacity: 0; pointer-events: none;
    transition: opacity .2s var(--ease), color .2s var(--ease);
  }
  .field .clear.on { opacity: 1; pointer-events: auto; }
  .field .clear:hover { color: var(--text); }

  /* thin progress line that lives on the header's bottom border */
  .bead {
    position: absolute; left: 0; bottom: -1px; height: 1px; width: 100%;
    background: linear-gradient(90deg, transparent, var(--text), transparent);
    transform: scaleX(0); transform-origin: left;
    opacity: 0; transition: opacity .2s;
  }
  .bead.on { opacity: .5; animation: sweep 1.1s var(--ease) infinite; }
  @keyframes sweep {
    0%   { transform: translateX(-30%) scaleX(.3); }
    100% { transform: translateX(100%) scaleX(.3); }
  }

  /* ---------- the plan line from the model ---------- */
  .plan {
    display: flex; align-items: baseline; gap: 10px; font-size: 13px;
    color: var(--dim); padding-bottom: 14px; margin-top: -4px;
    animation: rise .3s var(--ease) both;
  }
  .plan b { color: var(--text); font-weight: 500; }
  .plan .x { margin-left: auto; cursor: pointer; }
  .plan .x:hover { color: var(--text); }

  /* ---------- filters ---------- */
  .rail { display: flex; flex-wrap: wrap; gap: 7px; padding-bottom: 16px; }
  .crumbs { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
  .lead {
    font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--dimmer); margin-right: 2px;
  }
  .pill {
    --pad: 5px 11px;
    font-family: inherit;
    padding: var(--pad); border-radius: 999px; cursor: pointer;
    font-size: 13px; line-height: 1.3; color: var(--dim);
    background: transparent; border: 1px solid var(--line);
    user-select: none; white-space: nowrap;
    transition: color .18s var(--ease), border-color .18s var(--ease),
                background .18s var(--ease), transform .18s var(--ease);
  }
  .pill:hover { color: var(--text); border-color: var(--line-hi); }
  .pill:active { transform: scale(.97); }
  .pill.on {
    color: var(--bg); background: var(--text); border-color: var(--text);
  }
  .pill.on::after { content: "×"; margin-left: 7px; opacity: .55; }

{graph_css}
{sheet_css}
  /* ---------- results ---------- */
  main { padding: 22px 0 0; }
  .grid {
    display: grid; gap: 16px;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  }
  .card {
    position: relative; display: flex; flex-direction: column; overflow: hidden;
    background: var(--raise); border: 1px solid var(--line); border-radius: 14px;
    text-decoration: none; color: inherit; cursor: pointer;
    animation: rise .34s var(--ease) both;
    animation-delay: calc(var(--i) * 18ms);
    transition: border-color .2s var(--ease), transform .2s var(--ease),
                background .2s var(--ease);
  }
  .card:hover {
    border-color: var(--line-hi); background: #16161a; transform: translateY(-2px);
  }
  .card.dead { opacity: .4; }
  .card.dead:hover { opacity: .7; }
  @keyframes rise {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: none; }
  }
  .shot {
    aspect-ratio: 16 / 9; width: 100%; object-fit: cover; background: #17171b;
    filter: grayscale(.35) contrast(1.02);
    transition: filter .35s var(--ease), transform .5s var(--ease);
  }
  .card:hover .shot { filter: none; transform: scale(1.02); }
  .body { display: flex; flex-direction: column; gap: 8px; padding: 14px 15px 15px; flex: 1; }
  /* the title is what opens the note, so it is the button and the card is a
     plain container: a button holding other buttons is read out as one thing */
  .t {
    font-family: inherit; font-size: inherit; color: inherit;
    background: none; border: 0; padding: 0; width: 100%; text-align: left;
    cursor: pointer;
    font-weight: 600; line-height: 1.35; letter-spacing: -.01em;
  }
  .d { color: var(--dim); font-size: 13.5px; flex: 1; }
  .quote {
    font-size: 12.5px; color: #93939c; line-height: 1.5;
    border-left: 1px solid var(--line-hi); padding-left: 10px;
  }
  .quote b { color: var(--text); font-weight: 500; }
  .tagline { display: flex; flex-wrap: wrap; gap: 5px; }
  /* a clickable chip is a real button, so the keyboard reaches it for free */
  .mini {
    font-family: inherit; border: 0; text-align: left; line-height: 1.55;
    font-size: 11px; letter-spacing: .02em; padding: 2px 7px; border-radius: 5px;
    background: #1b1b1f; color: var(--dim); cursor: pointer;
    transition: color .16s var(--ease), background .16s var(--ease);
  }
  .mini:hover { color: var(--text); background: #232329; }
  .mini:focus-visible, .pill:focus-visible, .t:focus-visible {
    outline: 1px solid var(--text); outline-offset: 2px;
  }
  .meta {
    display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: var(--dimmer);
    font-variant-numeric: tabular-nums;
  }
  .meta s { text-decoration: none; opacity: .5; }

  .note { color: var(--dim); text-align: center; padding: 90px 0; font-size: 14px; }
  .note b { color: var(--text); font-weight: 500; }
  .more {
    display: block; margin: 26px auto 0; padding: 11px 26px; font: inherit;
    font-size: 14px; color: var(--text); background: transparent; cursor: pointer;
    border: 1px solid var(--line); border-radius: 10px;
    transition: border-color .18s var(--ease), background .18s var(--ease);
  }
  .more:hover { border-color: var(--line-hi); background: var(--raise); }
  footer {
    color: var(--dimmer); font-size: 12px; text-align: center;
    padding: 44px 24px 60px;
  }
  /* skeletons while the first page loads */
  .ghost {
    height: 190px; border-radius: 14px; background: var(--raise);
    animation: breathe 1.4s ease-in-out infinite;
  }
  @keyframes breathe { 0%,100% { opacity: .5 } 50% { opacity: .85 } }
</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="bar">
      <span class="mark">{glyph}cool stuff</span>
      <span class="count" id="count"></span>
      <a class="who" href="/me">profile</a>
    </div>
    <div class="field">
      <input id="q" type="search" maxlength="200" autocomplete="off" spellcheck="false"
             placeholder="sneakers, typeface, coffee…   or ask a question and hit Enter">
      <span class="clear" id="clear" title="Clear">×</span>
    </div>
    <div class="plan" id="plan" hidden></div>
    <div class="crumbs rail" id="crumbs" hidden></div>
  </div>
  <div class="bead" id="bead"></div>
</header>

<main class="wrap">
{graph_markup}
  <div class="grid" id="grid"></div>
  <div class="note" id="note" hidden></div>
  <button class="more" id="more" hidden>Load more</button>
</main>

<footer>Links from one Telegram chat. Grows on its own.</footer>
{sheet_markup}

<script>
const $ = s => document.querySelector(s);
const state = { q: "", category: "", tags: [], offset: 0 };
let total = 0;

const esc = s => (s || "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const NAMES = {
  clothing: "clothing", tech: "hardware", software: "software", site: "sites",
  article: "reading", video: "video", food: "food", place: "places", misc: "other",
};

// a category or a source is model-written text. `__proto__` on a plain object
// hands back something inherited rather than nothing, and the caller then tries
// to escape an object, so the lookup asks whether the key is really there
const look = (table, key) => (Object.hasOwn(table, key || "") ? table[key] : "") || key;

// everything on screen, keyed by url, so a click can find the note behind the
// card it landed on without stuffing the whole note into a data attribute
const shown = new Map();

function card(it, i) {
  shown.set(it.url, it);
  const shot = it.image
    ? `<img class="shot" src="${esc(it.image)}" loading="lazy" alt="" onerror="this.remove()">`
    : "";
  const tags = it.tags.slice(0, 4).map(t =>
    `<button type="button" class="mini" data-tag="${esc(t)}">${esc(t)}</button>`).join("");
  const q = it.quotes[0];
  const quote = q
    ? `<div class="quote"><b>${esc(q.author)}</b> ${esc(q.text.slice(0, 200))}</div>` : "";
  const by = it.by ? `<s>·</s>${esc(it.by)}` : "";
  // nobody said this one in the chat, it came out of someone's own notes
  const kept = it.saved ? `<s>·</s>saved` : "";
  const dead = it.dead ? `<s>·</s>link is down` : "";
  // the card itself opens the note; only the small link leaves for the site.
  // the title carries the same job for the keyboard, and it is the button —
  // a card with the role would have swallowed the chips and the link inside it
  return `<article class="card${it.dead ? " dead" : ""}" style="--i:${i}"
      data-open="${esc(it.url)}">
    ${shot}
    <div class="body">
      <button type="button" class="t" data-open="${esc(it.url)}"
        >${esc(it.title || it.domain)}</button>
      <div class="d">${esc(it.description)}</div>
      ${quote}
      <div class="tagline">${tags}</div>
      ${outlink(it.url, it.domain)}
      <div class="meta">${esc(it.date)}${by}${kept}${dead}</div>
    </div></article>`;
}

// one render, driven only by state.tags. clearing the markup is not decoration:
// .crumbs sets display:flex, which beats the browser's rule for [hidden], so a
// row that is merely hidden goes on showing the tags you just took off
function crumbs() {
  const box = $("#crumbs");
  box.hidden = !state.tags.length;
  // one button puts the whole page back the way it opened, so it shows for a
  // typed query and a category from the model too, not only for picked tags
  $("#webclear").hidden = !(state.tags.length || state.q || state.category);
  box.innerHTML = !state.tags.length ? ""
    : `<span class="lead">path</span>` + state.tags.map(t =>
        `<button type="button" class="pill on" data-tag="${esc(t)}">${esc(t)}</button>`).join("");
}

function busy(on) {
  $("#bead").classList.toggle("on", on);
  $("#count").classList.toggle("busy", on);
}

function say(n) {
  $("#count").textContent = n === 0 ? "nothing found"
    : n === 1 ? "1 link" : `${n} links`;
}

function skeletons() {
  $("#grid").innerHTML = Array.from({ length: 8 }, () => `<div class="ghost"></div>`).join("");
}

// the one place the filter is turned into a query string. the results and the
// web are the same filter, so they must never build it two different ways
function filters() {
  const p = new URLSearchParams({ q: state.q, category: state.category });
  state.tags.forEach(t => p.append("tag", t));
  return p;
}

// every request takes a ticket. a reply holding an old one belongs to a filter
// the page has already left, or to a "load more" that was clicked twice at the
// same offset, and appending it would mix two result sets into one grid
let ticket = 0;

async function load(reset) {
  if (reset) state.offset = 0;
  const mine = ++ticket;
  busy(true);
  const p = filters();
  p.set("offset", state.offset);
  let data;
  try {
    data = await (await fetch("/api/search?" + p)).json();
  } catch (err) {
    if (mine !== ticket) return;
    busy(false); note("Could not reach the server."); return;
  }
  if (mine !== ticket) return;
  busy(false);
  total = data.total;
  paint(data, reset);
  // everything in the collection is written in english, so a question typed in
  // another alphabet can only ever hit the chat quotes. when it hits nothing,
  // hand it to the model, which translates it into english search words
  if (reset && !total && FOREIGN.test(state.q)) ask(state.q);
}

// anything past latin extended-b: cyrillic, greek, cjk and the rest
const FOREIGN = /[^\\u0000-\\u024F]/;

function paint(data, reset) {
  if (reset) shown.clear();
  const html = data.items.map(card).join("");
  if (reset) $("#grid").innerHTML = html;
  else $("#grid").insertAdjacentHTML("beforeend", html);
  say(total);
  state.offset += data.items.length;
  $("#more").hidden = state.offset >= total;
  $("#note").hidden = total > 0;
  if (!total) note("Nothing matched. Try fewer words, or drop a filter.");
  crumbs();
  if (reset) Web.pull(filters());
}

function note(text) {
  const el = $("#note");
  el.hidden = false;
  el.innerHTML = text;
}

{graph_js}

{sheet_js}

/* ---------- interaction ---------- */

// the only way a tag is ever added or removed. the crumbs, the bubbles and the
// cards all come through here, so there is one place where the filter changes
function toggleTag(v) {
  // a tag already on the path comes off, a new one narrows further
  state.tags = state.tags.includes(v)
    ? state.tags.filter(t => t !== v) : [...state.tags, v];
  // repaint before the fetch: letting a tag go has to look immediate
  crumbs();
  Web.repaint();
  load(true);
}

document.addEventListener("click", e => {
  const tag = e.target.closest("[data-tag]");
  if (tag) {
    e.preventDefault();
    // picking a tag from inside the note means "show me these", not "read on"
    const inside = Sheet.isOpen;
    Sheet.shut();
    toggleTag(tag.dataset.tag);
    // shut() hands focus back to the card that opened the panel, and the grid
    // under it is about to be replaced by the answer. the crumb for the tag
    // just picked is the one thing on screen that outlives the swap
    if (inside) {
      const crumb = $("#crumbs [data-tag]");
      if (crumb) crumb.focus();
    }
    scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  // a link is a link wherever it sits; anywhere else on a card opens the note
  if (e.target.closest("a")) return;
  const open = e.target.closest("[data-open]");
  if (open && shown.has(open.dataset.open)) Sheet.open(shown.get(open.dataset.open));
});

$("#webclear").addEventListener("click", reset);

let timer;
$("#q").addEventListener("input", e => {
  clearTimeout(timer);
  // the ticket is spent the moment a key lands, not when the debounce fires:
  // an answer arriving inside those 180ms would otherwise overwrite the query
  // that is sitting in the box and then be searched for
  ticket++;
  state.q = e.target.value;
  $("#plan").hidden = true;
  $("#clear").classList.toggle("on", !!state.q);
  timer = setTimeout(() => load(true), 180);
});
$("#q").addEventListener("keydown", e => {
  if (e.key === "Enter") { clearTimeout(timer); ask(e.target.value); }
  if (e.key === "Escape" && !Sheet.isOpen) reset();
});
$("#clear").addEventListener("click", reset);
$("#more").addEventListener("click", () => load(false));

// "/" focuses the search box, the way every search-first page does it
addEventListener("keydown", e => {
  if (e.key === "Escape" && Sheet.isOpen) { Sheet.shut(); return; }
  // the search box is behind the panel: sending focus there would step straight
  // out of the modal and past the trap that keeps tab inside it
  if (Sheet.isOpen) return;
  if (e.key === "/" && document.activeElement !== $("#q")) {
    e.preventDefault(); $("#q").focus();
  }
});

function reset() {
  state.q = ""; state.category = ""; state.tags = []; state.offset = 0;
  $("#q").value = ""; $("#clear").classList.remove("on");
  $("#plan").hidden = true;
  crumbs();
  Web.repaint();
  load(true);
}

// enter asks the model to turn the question into search parameters. it never
// writes an answer of its own — everything shown below comes from the vault
async function ask(question) {
  if (!question.trim()) return;
  const plan = $("#plan");
  plan.hidden = false;
  plan.textContent = "reading the question…";
  busy(true);
  skeletons();
  // the question takes a ticket from the same book as the search box, so a
  // typed query still in flight cannot land on top of the answer
  const mine = ++ticket;
  let r;
  try {
    r = await fetch("/api/ask", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ q: question.slice(0, 200) }),
    });
  } catch (err) {
    if (mine !== ticket) return;
    busy(false); plan.textContent = "Could not reach the server."; return;
  }
  if (mine !== ticket) return;
  busy(false);
  if (r.status === 429) { plan.textContent = "Too many questions — wait a minute."; return; }
  if (!r.ok) { plan.textContent = "That did not work. Try plain keywords."; return; }

  const data = await r.json();
  if (mine !== ticket) return;
  const p = data.plan;
  state.q = p.query; state.category = p.category;
  state.tags = p.tag ? [p.tag] : []; state.offset = 0;
  const bits = [p.query && `<b>${esc(p.query)}</b>`,
                p.category && esc(look(NAMES, p.category))].filter(Boolean).join("  ·  ");
  plan.innerHTML = `${esc(p.reply)}${bits ? " → " + bits : ""}
    <span class="x" id="undo">clear</span>`;
  $("#undo").onclick = reset;
  total = data.total;
  paint(data, true);
}

Web.start({ pick: toggleTag, picked: () => state.tags });
skeletons();
load(true);
</script>
</body>
</html>
"""

# not an f-string on the template itself: it is full of javascript braces
PAGE = (
    _PAGE.replace("{icon}", brand.ICON_LINK)
    .replace("{glyph}", brand.GLYPH)
    .replace("{graph_css}", graph.CSS)
    .replace("{graph_markup}", graph.MARKUP)
    .replace("{graph_js}", graph.JS)
    .replace("{sheet_css}", sheet.CSS)
    .replace("{sheet_markup}", sheet.MARKUP)
    .replace("{sheet_js}", sheet.JS)
)
