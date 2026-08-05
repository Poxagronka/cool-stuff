"""The tag web: the biggest tags as bubbles on threads, drawn on a canvas.

The page interpolates CSS and JS from here. Canvas rather than SVG for two
reasons: a dozen nodes redrawn while the layout settles cost nothing, and
nothing that came off the network is ever parsed as markup — labels go through
fillText, the fallback list through textContent. Tag strings are written by a
model reading arbitrary web pages, so they get treated as hostile text.

Only the biggest tags are drawn, and once the layout has come to rest it stops
moving. Sixty bubbles with a wobble on each was a picture nobody could read.
"""

CSS = """
  /* ---------- the tag web ---------- */
  [hidden] { display: none !important; }

  :root { --bubble: #1c1c21; }
  .web { padding: 0 0 22px; }
  /* the row holds nothing but the reset button, which comes and goes. it keeps
     its height anyway, or the whole web jumps down the moment a tag is picked */
  .webbar {
    display: flex; align-items: baseline; gap: 10px; padding-bottom: 8px;
    min-height: 31px;
  }
  .webclear {
    margin-left: auto; font: inherit; font-size: 12px; color: var(--dim);
    background: none; border: 0; padding: 2px 4px; cursor: pointer;
    transition: color .18s var(--ease);
  }
  .webclear:hover { color: var(--text); }
  .webclear:focus-visible { outline: 1px solid var(--text); outline-offset: 2px; }
  .webbox {
    position: relative; height: clamp(260px, 38vh, 400px);
    background: var(--raise); border: 1px solid var(--line); border-radius: 14px;
    overflow: hidden;
  }
  /* a narrow box is not a short one: the bubbles need area, and on a phone the
     only place left to find it is downwards */
  @media (max-width: 700px) {
    .webbox { height: min(62vh, 460px); }
  }
  .webbox canvas { display: block; width: 100%; height: 100%; touch-action: none; }
  .webbox canvas:focus-visible { outline: 1px solid var(--dim); outline-offset: -1px; }
  .tip {
    position: absolute; pointer-events: none; z-index: 5;
    padding: 4px 9px; border-radius: 7px; font-size: 12px; white-space: nowrap;
    color: var(--text); background: #1b1b1f; border: 1px solid var(--line-hi);
    font-variant-numeric: tabular-nums;
  }
  /* the same graph as a plain list of buttons, for keyboard and screen readers */
  .sr {
    position: absolute; left: 0; top: 0; margin: 0; padding: 0; list-style: none;
    width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%);
  }
  .sr:focus-within {
    width: auto; height: auto; overflow: visible; clip-path: none;
    display: flex; flex-wrap: wrap; gap: 6px; padding: 10px;
    background: var(--bg); z-index: 6;
  }
  .sr button {
    font: inherit; font-size: 13px; color: var(--dim); cursor: pointer;
    background: transparent; border: 1px solid var(--line);
    border-radius: 999px; padding: 5px 11px;
  }
  .sr button[aria-pressed="true"] { color: var(--bg); background: var(--text); }
"""

MARKUP = """
<section class="web" aria-label="Tag web">
  <div class="webbar">
    <button class="webclear" id="webclear" type="button" hidden>× reset</button>
  </div>
  <div class="webbox" id="webbox">
    <canvas id="webcv" tabindex="-1"></canvas>
    <div class="tip" id="webtip" hidden></div>
    <ul class="sr" id="weblist"></ul>
  </div>
</section>
"""

JS = """
// the web has no notion of what is picked. it asks the page every frame, so
// the drawing and the filter cannot drift apart the way two lists would
const Web = (() => {
  const box = $("#webbox"), cv = $("#webcv"), tip = $("#webtip"), list = $("#weblist");
  const ctx = cv.getContext("2d");
  const calm = matchMedia("(prefers-reduced-motion: reduce)");

  const nodes = new Map();   // tag -> body. survives refetches so the web keeps its shape
  let links = [], heaviest = 1;
  let W = 300, H = 260, raf = 0, last = 0, still = 0, steps = 0, asleep = true;
  // nothing about the drawing is a pixel constant: the circles, the type, the
  // threads and how many bubbles there are at all come off the size of the box.
  // `unit` is the room one bubble has, and every length below is a share of it
  let unit = 150, font = 13, lineH = 16, R0 = 14, RK = 22;
  // the last answer from the server, kept so a resize can lay it out again at
  // the new size rather than wait for the next fetch
  let latest = null;
  // a layout that has not come to rest in this many steps never will, and going
  // on solving it is just a warm laptop
  const BUDGET = 320;
  // grabId is the finger holding the bubble: a second one on the glass must not
  // steer the first one's drag or end it
  let hot = null, grab = null, grabId = -1, seq = 0;
  let onPick = () => {}, picked = () => [];

  const FACE = "ui-sans-serif, -apple-system, sans-serif";
  const skin = getComputedStyle(document.documentElement);
  const hue = (name, fallback) => skin.getPropertyValue(name).trim() || fallback;
  const ink = {
    text: hue("--text", "#ededf0"), dim: hue("--dim", "#77777f"),
    line: hue("--line-hi", "#34343a"), body: hue("--bubble", "#1c1c21"),
  };

  // a stable per-tag number, so a bubble is born in the same place every time
  function seed(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0) / 4294967296;
  }

  // never trust the string: strip control characters, keep it short enough to read
  function label(s) {
    let out = "";
    for (const ch of s) { if (ch.codePointAt(0) > 31) out += ch; if (out.length > 22) break; }
    return out.length > 22 ? out.slice(0, 21) + "\\u2026" : out;
  }

  function born(tag, near) {
    const a = seed(tag) * 6.283, spread = unit * (0.25 + seed(tag + "r") * 0.55);
    return {
      tag, count: 1, r: 10, text: "", lw: 0, hw: 10, hh: 10, drop: 0,
      x: near.x + Math.cos(a) * spread, y: near.y + Math.sin(a) * spread,
      vx: 0, vy: 0,
    };
  }

  // one bubble's worth of room, and every length that follows from it. a phone
  // gets small circles and small type, a laptop the same picture larger — the
  // ratios are what stay fixed, not the pixels
  function tune(count) {
    const room = Math.sqrt((W * H) / Math.max(1, count));
    unit = Math.max(56, Math.min(room, Math.min(W, H) * 0.62));
    font = Math.max(10, Math.min(15, Math.round(unit * 0.082)));
    lineH = Math.round(font * 1.3);
    R0 = Math.max(7, unit * 0.085);
    RK = Math.max(7, unit * 0.13);
  }

  // how many bubbles this box can hold at all. fourteen is what a laptop fits;
  // a phone that is handed fourteen puts words on top of words, so it gets fewer
  const holds = () => Math.max(6, Math.min(14, Math.floor((W * H) / 13000)));

  // the word as it will be drawn, cut to something that fits the box rather
  // than to a fixed number of characters: `outdoor-gear` is nearly half the
  // width of a phone
  function fit(tag) {
    const room = Math.max(48, Math.min(W * 0.38, unit * 1.6));
    let out = label(tag);
    if (ctx.measureText(out).width <= room) return out;
    while (out.length > 3 && ctx.measureText(out + "\\u2026").width > room) {
      out = out.slice(0, -1);
    }
    return out + "\\u2026";
  }

  // the box the bubble and its word together take up. the word hangs below the
  // circle, so the box is taller than the circle and its centre sits lower
  function shape(n) {
    n.hw = Math.max(n.r, n.lw / 2) + 5;
    const tall = n.r + 4 + lineH;
    n.drop = (tall - n.r) / 2;
    n.hh = (n.r + tall) / 2 + 3;
  }

  function apply(data) {
    latest = data;
    const on = new Set(picked());
    const keep = new Set();
    const all = (data.nodes || []).filter(
      raw => raw && typeof raw.tag === "string" && raw.tag);
    // the server ranks them, so the tail this drops is the smallest tags. a tag
    // already picked never drops out: a web missing the node you stand on is a bug
    const drawn = all.slice(0, holds());
    const inside = new Set(drawn.map(raw => raw.tag));
    for (const raw of all) {
      if (on.has(raw.tag) && !inside.has(raw.tag)) { drawn.push(raw); inside.add(raw.tag); }
    }
    tune(drawn.length);
    ctx.font = font + "px " + FACE;
    const top = Math.max(1, ...drawn.map(raw => raw.count || 1));
    // new bubbles come in beside what is already picked, not out of the corner
    const anchor = { x: W / 2, y: H / 2 };
    const held = [...nodes.values()].filter(n => on.has(n.tag));
    if (held.length) {
      anchor.x = held.reduce((s, n) => s + n.x, 0) / held.length;
      anchor.y = held.reduce((s, n) => s + n.y, 0) / held.length;
    }
    for (const raw of drawn) {
      const tag = raw.tag;
      keep.add(tag);
      let n = nodes.get(tag);
      if (!n) { n = born(tag, anchor); nodes.set(tag, n); }
      n.count = Math.max(1, raw.count | 0);
      n.r = R0 + RK * Math.sqrt(n.count / top);
      n.text = fit(tag);
      n.lw = ctx.measureText(n.text).width;
      shape(n);
    }
    for (const tag of [...nodes.keys()]) if (!keep.has(tag)) nodes.delete(tag);
    links = (data.edges || [])
      .filter(e => Array.isArray(e) && nodes.has(e[0]) && nodes.has(e[1]))
      .map(e => [nodes.get(e[0]), nodes.get(e[1]), Math.max(1, e[2] | 0)]);
    heaviest = Math.max(1, ...links.map(e => e[2]));
    roster();
    kick();
  }

  // the same nodes as buttons. built with the DOM, never with a markup string
  const buttons = new Map();
  function roster() {
    const on = new Set(picked());
    const want = [...nodes.values()].sort((a, b) => b.count - a.count);
    const same = want.length === buttons.size && want.every(n => buttons.has(n.tag));
    // rebuilding on every toggle would throw a keyboard user out of the list,
    // so when only the picked set moved, the buttons stay where they are
    if (!same) {
      buttons.clear();
      list.replaceChildren(...want.map(n => {
        const li = document.createElement("li");
        const b = document.createElement("button");
        b.type = "button";
        b.addEventListener("click", () => onPick(n.tag));
        buttons.set(n.tag, b);
        li.append(b);
        return li;
      }));
    }
    for (const n of want) {
      const b = buttons.get(n.tag);
      b.textContent = label(n.tag) + " (" + n.count + ")";
      b.setAttribute("aria-pressed", on.has(n.tag) ? "true" : "false");
    }
  }

  function measure() {
    const rect = box.getBoundingClientRect();
    W = Math.max(200, rect.width); H = Math.max(180, rect.height);
    const dpr = Math.min(2, devicePixelRatio || 1);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // the sizes are a share of the box, so a box that changed size is the whole
    // layout again — including how many bubbles there is room for
    if (latest) apply(latest); else kick();
  }

  function settle(rounds) { for (let i = 0; i < rounds; i++) physics(1); }

  function physics(k) {
    const on = new Set(picked());
    const all = [...nodes.values()];
    for (let i = 0; i < all.length; i++) {
      const a = all[i];
      for (let j = i + 1; j < all.length; j++) {
        const b = all[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) { dx = (seed(a.tag) - 0.5) || 0.3; dy = 0.4; d2 = 1; }
        const d = Math.sqrt(d2);
        // plain inverse-square push, in units of the room a bubble has, so a
        // small box spreads the same picture and not a crowded one
        const f = unit * unit * 0.16 / d2;
        const ux = dx / d * f, uy = dy / d * f;
        a.vx -= ux * k; a.vy -= uy * k; b.vx += ux * k; b.vy += uy * k;
        // what must not overlap is not two circles: the word hangs under the
        // bubble and is usually wider than it. so the pair is kept apart as two
        // boxes, and they give way along whichever axis is nearer to free —
        // pushing along the line of centres is what let labels slide together
        const ay = a.y + a.drop, by = b.y + b.drop;
        const gx = a.hw + b.hw, gy = a.hh + b.hh;
        const ox = gx - Math.abs(dx), oy = gy - Math.abs(by - ay);
        if (ox > 0 && oy > 0) {
          // a soft floor rather than a hard one: stiff enough and the pair just
          // bounces off each other forever instead of coming to rest
          if (ox / gx <= oy / gy) {
            const s = (dx >= 0 ? 1 : -1) * ox * 0.22 * k;
            a.vx -= s; b.vx += s;
          } else {
            const s = (by >= ay ? 1 : -1) * oy * 0.22 * k;
            a.vy -= s; b.vy += s;
          }
        }
      }
    }
    for (const [a, b, w] of links) {
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 1;
      // the more two tags are said together, the shorter the thread between them
      const rest = a.r + b.r + unit * (0.18 + 0.5 * (1 - w / heaviest));
      const f = (d - rest) * 0.012 * k;
      const ux = dx / d * f, uy = dy / d * f;
      a.vx += ux; a.vy += uy; b.vx -= ux; b.vy -= uy;
    }
    let fastest = 0;
    for (const n of all) {
      // what is picked sinks to the middle, the rest hangs off it
      const pull = on.has(n.tag) ? 0.011 : 0.004;
      // a wide box used to divide this by its own aspect, which on a laptop
      // strip came to a fifth and let the web drift out to both edges
      n.vx += (W / 2 - n.x) * pull * Math.max(0.3, H / W) * k;
      n.vy += (H / 2 - n.y) * pull * k;
      n.vx *= 0.86; n.vy *= 0.86;
      if (grab === n) { n.vx = 0; n.vy = 0; continue; }
      n.x += n.vx * k; n.y += n.vy * k;
      // the word is wider than the bubble, so what the sides hold in is the
      // word: keeping the centre inside was cutting labels off at both edges
      const padX = Math.max(n.r, n.lw / 2) + 4;
      n.x = Math.min(W - padX, Math.max(padX, n.x));
      // and it hangs below, so the floor is a line of type further up
      n.y = Math.min(H - n.r - lineH - 6, Math.max(n.r + 4, n.y));
      fastest = Math.max(fastest, Math.abs(n.vx) + Math.abs(n.vy));
    }
    // the web is put in the middle as one thing. a spring on every bubble
    // pulling at the centre either leaves half a wide box empty or knots
    // everything up in the narrow one, and which of the two it does depends on
    // the shape of the box
    if (!grab) recentre(all);
    still = fastest < 0.12 ? still + 1 : 0;
    steps++;
  }

  // eased rather than exact: snapping the whole web sideways every step reads
  // as the picture sliding around under a layout that has not settled yet
  function recentre(all) {
    if (!all.length) return;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const n of all) {
      x0 = Math.min(x0, n.x - n.hw); x1 = Math.max(x1, n.x + n.hw);
      y0 = Math.min(y0, n.y - n.r); y1 = Math.max(y1, n.y + n.r + 4 + lineH);
    }
    const dx = ((W - (x1 - x0)) / 2 - x0) * 0.12;
    const dy = ((H - (y1 - y0)) / 2 - y0) * 0.12;
    if (Math.abs(dx) < 0.05 && Math.abs(dy) < 0.05) return;
    for (const n of all) { n.x += dx; n.y += dy; }
  }

  function draw() {
    const on = new Set(picked());
    ctx.clearRect(0, 0, W, H);
    const near = hot ? new Set([hot.tag]) : new Set();

    for (const [a, b, w] of links) {
      const ax = a.x, ay = a.y, bx = b.x, by = b.y;
      const lit = near.has(a.tag) || near.has(b.tag) || on.has(a.tag) || on.has(b.tag);
      ctx.globalAlpha = Math.min(1, (0.12 + 0.3 * (w / heaviest)) * (lit ? 2.2 : 1));
      ctx.strokeStyle = lit ? ink.text : ink.line;
      ctx.lineWidth = 0.6 + 1.1 * (w / heaviest);
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }
    ctx.globalAlpha = 1;

    for (const n of nodes.values()) {
      const x = n.x, y = n.y;
      const isOn = on.has(n.tag), isHot = hot === n;
      ctx.beginPath(); ctx.arc(x, y, n.r, 0, 6.2832);
      ctx.fillStyle = isOn ? ink.text : ink.body;
      ctx.fill();
      ctx.lineWidth = isHot ? 1.5 : 1;
      ctx.strokeStyle = isOn || isHot ? ink.text : ink.line;
      ctx.stroke();
      ctx.fillStyle = isOn ? ink.text : isHot ? ink.text : ink.dim;
      ctx.font = font + "px " + FACE;
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      ctx.fillText(n.text || label(n.tag), x, y + n.r + 4);
    }
  }

  function frame(ts) {
    raf = 0;
    if (asleep) return;
    const done = still > 20 || steps >= BUDGET;
    if (!done) {
      const dt = Math.min(2.5, (ts - last) / 16) || 1;
      last = ts;
      physics(dt);
    }
    draw();
    // nothing drifts on its own: once the layout has come to rest the loop
    // stops dead, and hovering, dragging or picking wakes it for a frame
    if (done) { asleep = true; return; }
    raf = requestAnimationFrame(frame);
  }

  // wake redraws what is already there. kick also tells the solver to run again
  function wake() {
    if (!asleep) return;
    asleep = false; last = 0;
    if (!raf) raf = requestAnimationFrame(frame);
  }

  function kick() {
    still = 0; steps = 0; last = 0; asleep = false;
    // nothing may drift for someone who asked for no motion, so the layout is
    // solved here and the loop is handed something finished to draw once
    if (calm.matches) { settle(400); steps = BUDGET; }
    if (!raf) raf = requestAnimationFrame(frame);
  }

  function pause() { asleep = true; if (raf) cancelAnimationFrame(raf); raf = 0; }

  function find(ev) {
    const rect = cv.getBoundingClientRect();
    const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
    let best = null;
    for (const n of nodes.values()) {
      if (Math.hypot(px - n.x, py - n.y) <= n.r + 4) best = n;
    }
    return [best, px, py];
  }

  cv.addEventListener("pointermove", ev => {
    if (grab) {
      if (ev.pointerId !== grabId) return;
      const rect = cv.getBoundingClientRect();
      grab.x = ev.clientX - rect.left; grab.y = ev.clientY - rect.top;
      // a layout that has already spent its budget still has to give way to a
      // bubble being dragged through it, so the solver gets its steps back —
      // except for someone who asked for no motion, where the one bubble under
      // the finger moves and the rest of the web stays where it was put
      if (!calm.matches) { still = 0; steps = 0; }
      wake();
      return;
    }
    const [n, px, py] = find(ev);
    if (n !== hot) { hot = n; wake(); }
    cv.style.cursor = n ? "pointer" : "default";
    tip.hidden = !n;
    if (n) {
      tip.textContent = label(n.tag) + "  \\u00b7  " + n.count
        + (n.count === 1 ? " link" : " links");
      tip.style.left = Math.min(W - 150, px + 14) + "px";
      tip.style.top = Math.max(4, py - 34) + "px";
    }
  });

  cv.addEventListener("pointerleave", ev => {
    const lit = hot;
    hot = null; tip.hidden = true;
    // only the finger that took the bubble can let go of it: a second one
    // sliding off the glass was ending someone else's drag
    if (grab && ev.pointerId === grabId) { grab = null; grabId = -1; }
    // the highlight is already painted and the loop may have gone to sleep on
    // top of it, so clearing it has to ask for one more frame
    if (lit) wake();
  });

  cv.addEventListener("pointerdown", ev => {
    if (grab) return;
    const [n] = find(ev);
    if (!n) return;
    grab = n; grabId = ev.pointerId;
    // a pointer the browser will not hand over is not worth losing the click for
    try { cv.setPointerCapture(ev.pointerId); } catch (err) { /* keep going */ }
    // taking hold of a bubble is not a reason to solve the layout again: one
    // frame is enough to draw it lit, and under no-motion kick() would reflow
    // the whole web around a finger that has not moved yet
    wake();
  });

  cv.addEventListener("pointerup", ev => {
    if (grab && ev.pointerId !== grabId) return;
    const held = grab;
    grab = null; grabId = -1;
    if (!held) return;
    const [n] = find(ev);
    // a drag that ends on the bubble it started from is still a click
    if (n === held) onPick(held.tag);
    // the web closes back around the bubble that was let go, unless no motion
    // was asked for: then it stays exactly where the finger left it
    if (calm.matches) wake(); else kick();
  });

  new ResizeObserver(measure).observe(box);
  new IntersectionObserver(es => {
    if (es[0].isIntersecting) wake(); else pause();
  }, { threshold: 0 }).observe(box);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pause(); else wake();
  });
  calm.addEventListener("change", kick);

  return {
    start(opts) { onPick = opts.pick; picked = opts.picked; measure(); },
    // the page calls this the instant a tag is toggled, before any network work,
    // so letting a tag go is visible immediately
    repaint() { roster(); kick(); },
    async pull(params) {
      const mine = ++seq;
      let data;
      try { data = await (await fetch("/api/graph?" + params)).json(); }
      catch (err) { return; }
      if (mine !== seq || !data || !Array.isArray(data.nodes)) return;
      apply(data);
    },
  };
})();
"""
