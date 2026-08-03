"""The panel that opens when a card is clicked: the note, as the vault has it.

A card is a summary; this is the whole thing — the front matter laid out as a
properties table, the description, and every chat quote rather than the first
one. It reads like the note does in Obsidian because it is the same fields in
the same order.

Everything on screen comes off the network, so nothing here is ever handed to
innerHTML unescaped: the page's own `esc` runs over every value.
"""

CSS = """
  /* ---------- the note panel ---------- */
  .veil {
    position: fixed; inset: 0; z-index: 40;
    display: grid; place-items: start center; padding: 40px 20px;
    overflow-y: auto; overscroll-behavior: contain;
    background: color-mix(in srgb, #000 62%, transparent);
    backdrop-filter: blur(6px);
    animation: fade .18s var(--ease) both;
  }
  @keyframes fade { from { opacity: 0 } to { opacity: 1 } }
  .sheet {
    position: relative; width: min(660px, 100%);
    background: var(--raise); border: 1px solid var(--line-hi);
    border-radius: 16px; overflow: hidden;
    animation: lift .22s var(--ease) both;
  }
  @keyframes lift {
    from { opacity: 0; transform: translateY(12px) scale(.99) }
    to   { opacity: 1; transform: none }
  }
  .sheet .shut {
    position: absolute; right: 12px; top: 12px; z-index: 2;
    width: 30px; height: 30px; display: grid; place-items: center;
    padding: 0; cursor: pointer;
    color: var(--dim); background: color-mix(in srgb, var(--bg) 70%, transparent);
    border: 1px solid var(--line); border-radius: 8px;
    transition: color .18s var(--ease), border-color .18s var(--ease);
  }
  .sheet .shut:hover { color: var(--text); border-color: var(--line-hi); }
  /* the panel puts the keyboard on this button the moment it opens, and a ring
     drawn around it then reads as a box someone drew on the photo. the button
     lighting up is the same signal without the frame */
  .sheet .shut:focus-visible { color: var(--text); border-color: var(--text); }
  .out:focus-visible { outline: 1px solid var(--text); outline-offset: 2px; }
  .sheet .hero {
    width: 100%; aspect-ratio: 16 / 9; object-fit: cover; background: #17171b;
    display: block; border-bottom: 1px solid var(--line);
  }
  .sheet .inner { padding: 22px 24px 26px; }
  .sheet h2 {
    margin: 0 0 12px; font-size: 22px; line-height: 1.25; letter-spacing: -.02em;
    padding-right: 34px;
  }
  .sheet .lede { color: var(--dim); font-size: 14.5px; margin: 0 0 18px; }

  /* the link out, the one thing on the panel that leaves the site */
  .out {
    display: inline-flex; align-items: center; gap: 6px; max-width: 100%;
    color: var(--text); text-decoration: none; font-size: 13.5px;
    padding: 7px 12px; border: 1px solid var(--line);
    border-radius: 9px; background: var(--bg);
    transition: border-color .18s var(--ease), background .18s var(--ease);
  }
  .out:hover { border-color: var(--line-hi); background: #16161a; }
  .out span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .out.dud { color: var(--dimmer); cursor: default; }
  .out svg { flex: none; opacity: .6; }
  .out:hover svg { opacity: 1; }

  /* the same link on a card: quieter, and it must not read as the whole card */
  .card .out {
    align-self: flex-start; padding: 4px 9px; font-size: 12px; color: var(--dim);
  }
  .card .out:hover { color: var(--text); }

  .props {
    width: 100%; border-collapse: collapse; margin: 20px 0 0; font-size: 13.5px;
  }
  .props th, .props td {
    text-align: left; vertical-align: top; padding: 8px 0;
    border-top: 1px solid var(--line);
  }
  .props th { width: 130px; font-weight: 400; color: var(--dimmer); }
  .props td { color: var(--text); }
  .props .chips { display: flex; flex-wrap: wrap; gap: 5px; }
  /* keywords are what the model wrote down, not a filter you can walk */
  .props .mini:not([data-tag]) { cursor: default; }
  .props .mini:not([data-tag]):hover { color: var(--dim); background: #1b1b1f; }

  .said { margin: 24px 0 0; }
  .said .lead { display: block; margin-bottom: 10px; }
  .said blockquote {
    margin: 0 0 12px; padding: 0 0 0 12px; font-size: 13.5px; line-height: 1.6;
    color: #93939c; border-left: 1px solid var(--line-hi);
  }
  .said blockquote:last-child { margin-bottom: 0; }
  .said b { color: var(--text); font-weight: 500; }
  .said i { font-style: normal; color: var(--dimmer); font-size: 12px; margin-left: 6px; }
"""

MARKUP = """
<div class="veil" id="veil" hidden role="dialog" aria-modal="true"
     aria-label="Note"><div class="sheet" id="sheet"></div></div>
"""

JS = """
// the little box-with-an-arrow. drawn rather than a character so it lines up
const OUT = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
  + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
  + 'stroke-linejoin="round" aria-hidden="true">'
  + '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
  + '<path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>';

// same reason as OUT: the multiplication sign sits off centre in most faces,
// and no amount of line-height fixes it. two strokes on a square viewbox do
const SHUT = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
  + 'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
  + 'aria-hidden="true"><path d="M5 5 19 19"/><path d="M19 5 5 19"/></svg>';

// a url out of a note is text a model wrote, and escaping the four characters
// says nothing about the scheme: `javascript:alert(1)` survives esc() intact.
// anything that is not plainly http shows as text and goes nowhere
const WEB_URL = /^https?:\\/\\//i;

function outlink(url, text) {
  if (!WEB_URL.test(url || "")) return `<span class="out dud">${esc(text)}</span>`;
  return `<a class="out" href="${esc(url)}" target="_blank" rel="noopener noreferrer"
    ><span>${esc(text)}</span>${OUT}</a>`;
}

const Sheet = (() => {
  const veil = $("#veil"), box = $("#sheet");
  let back = null;   // what had the focus before the panel took it

  const NOTE_SOURCE = { chat: "the chat", saved: "saved messages" };

  // the note keeps a full timestamp with an offset. nobody reading it cares
  // about the seconds, and the offset is the same on every note in the vault
  const when = at => (at || "").replace("T", " ").slice(0, 16);

  function row(label, html) {
    return html ? `<tr><th>${esc(label)}</th><td>${html}</td></tr>` : "";
  }

  // a tag filters, so it is a button and the keyboard reaches it; a keyword is
  // only what the model wrote down and has nothing to be clicked for
  function chips(words, clickable) {
    if (!words || !words.length) return "";
    const one = clickable
      ? t => `<button type="button" class="mini" data-tag="${esc(t)}">${esc(t)}</button>`
      : t => `<span class="mini">${esc(t)}</span>`;
    return `<div class="chips">` + words.map(one).join("") + `</div>`;
  }

  function open(it) {
    back = document.activeElement;
    const hero = it.image
      ? `<img class="hero" src="${esc(it.image)}" alt="" onerror="this.remove()">` : "";
    const said = (it.quotes || []).map(q =>
      `<blockquote><b>${esc(q.author)}</b><i>${esc(q.at || "")}</i><br>${esc(q.text)}</blockquote>`
    ).join("");
    box.innerHTML = `
      <button class="shut" id="shut" type="button" aria-label="Close">${SHUT}</button>
      ${hero}
      <div class="inner">
        <h2>${esc(it.title || it.domain)}</h2>
        ${it.description ? `<p class="lede">${esc(it.description)}</p>` : ""}
        ${outlink(it.url, it.url)}
        <table class="props">
          ${row("domain", esc(it.domain))}
          ${row("category", esc(look(NAMES, it.category)))}
          ${row("tags", chips(it.tags, true))}
          ${row("keywords", chips(it.keywords, false))}
          ${row("shared by", esc(it.by))}
          ${row("shared at", esc(when(it.at)))}
          ${row("source", esc(look(NOTE_SOURCE, it.source)))}
          ${row("status", it.dead ? "the link is down" : esc(it.status))}
          ${row("confidence", esc(it.confidence))}
        </table>
        ${said ? `<div class="said"><span class="lead">from the chat</span>${said}</div>` : ""}
      </div>`;
    veil.hidden = false;
    document.body.style.overflow = "hidden";
    $("#shut").focus();
  }

  function shut() {
    if (veil.hidden) return;
    veil.hidden = true;
    box.innerHTML = "";
    document.body.style.overflow = "";
    // the card behind the panel can be gone by now, a search having replaced
    // the grid underneath it. dropping focus on the document strands the
    // keyboard at the top of the page, so the search box catches it instead
    (back && back.isConnected ? back : $("#q")).focus();
    back = null;
  }

  // tab stays inside while the panel is up, or the next press lands on a card
  // behind it that the reader cannot see. the listener sits on the document
  // rather than the panel: focus that has already slipped out would never
  // reach a listener attached to the thing it slipped out of
  document.addEventListener("keydown", e => {
    if (veil.hidden || e.key !== "Tab") return;
    const stops = box.querySelectorAll("button, a[href]");
    if (!stops.length) return;
    const first = stops[0], last = stops[stops.length - 1];
    if (!box.contains(document.activeElement)) {
      e.preventDefault(); first.focus(); return;
    }
    const edge = e.shiftKey ? first : last;
    if (document.activeElement !== edge) return;
    e.preventDefault();
    (e.shiftKey ? last : first).focus();
  });

  // the backdrop closes, the panel does not: a click that started on the text
  // and drifted onto the backdrop would otherwise throw the note away
  veil.addEventListener("mousedown", e => { if (e.target === veil) shut(); });
  veil.addEventListener("click", e => {
    if (e.target.closest("#shut")) shut();
  });

  return { open, shut, get isOpen() { return !veil.hidden; } };
})();
"""
