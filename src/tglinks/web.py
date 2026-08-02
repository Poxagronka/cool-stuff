"""The public page. One file, no build step, no framework."""

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>cool stuff</title>
<style>
  :root {
    --bg: #0e0e10; --card: #17171a; --line: #26262b;
    --text: #e8e8ea; --dim: #8a8a94; --accent: #d8b26a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 10; background: rgba(14,14,16,.92);
    backdrop-filter: blur(12px); border-bottom: 1px solid var(--line);
    padding: 18px 20px 12px;
  }
  .wrap { max-width: 1180px; margin: 0 auto; }
  h1 { margin: 0 0 12px; font-size: 17px; font-weight: 600; letter-spacing: .3px; }
  h1 span { color: var(--dim); font-weight: 400; margin-left: 8px; font-size: 14px; }
  input[type=search] {
    width: 100%; padding: 11px 14px; border-radius: 9px; font-size: 15px;
    background: var(--card); border: 1px solid var(--line); color: var(--text);
    outline: none;
  }
  input[type=search]:focus { border-color: var(--accent); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .chip {
    padding: 4px 10px; border-radius: 999px; cursor: pointer; font-size: 13px;
    background: var(--card); border: 1px solid var(--line); color: var(--dim);
    user-select: none;
  }
  .chip:hover { color: var(--text); }
  .chip.on { background: var(--accent); border-color: var(--accent); color: #16160f; }
  .chip b { font-weight: 500; opacity: .6; margin-left: 5px; }
  main { max-width: 1180px; margin: 0 auto; padding: 20px; }
  .grid {
    display: grid; gap: 14px;
    grid-template-columns: repeat(auto-fill, minmax(255px, 1fr));
  }
  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    overflow: hidden; display: flex; flex-direction: column;
    text-decoration: none; color: inherit; transition: border-color .15s;
  }
  .card:hover { border-color: var(--accent); }
  .card.dead { opacity: .45; }
  .thumb { aspect-ratio: 16/9; object-fit: cover; width: 100%; background: #1e1e22; }
  .body { padding: 12px 13px 13px; display: flex; flex-direction: column; gap: 7px; flex: 1; }
  .t { font-weight: 600; line-height: 1.35; }
  .d { color: var(--dim); font-size: 13.5px; flex: 1; }
  .meta { display: flex; gap: 8px; font-size: 12px; color: var(--dim); align-items: center; }
  .meta .dot { opacity: .4; }
  .tags { display: flex; flex-wrap: wrap; gap: 5px; }
  .tag {
    font-size: 11.5px; padding: 2px 7px; border-radius: 5px;
    background: #202024; color: var(--dim); cursor: pointer;
  }
  .tag:hover { color: var(--accent); }
  .q {
    font-size: 13px; color: #a8a8b2; border-left: 2px solid #34343a;
    padding-left: 9px; line-height: 1.45;
  }
  .q b { color: var(--accent); font-weight: 500; }
  .plan {
    margin-top: 9px; font-size: 13px; color: var(--dim);
    display: flex; gap: 8px; align-items: baseline;
  }
  .plan b { color: var(--accent); font-weight: 500; }
  .plan .x { cursor: pointer; margin-left: auto; }
  .plan .x:hover { color: var(--text); }
  .empty { color: var(--dim); padding: 60px 0; text-align: center; }
  .more { display: block; margin: 24px auto 0; padding: 10px 22px; cursor: pointer;
    background: var(--card); border: 1px solid var(--line); color: var(--text);
    border-radius: 9px; font-size: 14px; }
  .more:hover { border-color: var(--accent); }
  footer { color: var(--dim); font-size: 12.5px; text-align: center; padding: 30px 20px 50px; }
</style>
</head>
<body>
<header><div class="wrap">
  <h1>cool stuff <span id="count"></span></h1>
  <input type="search" id="q" maxlength="200" autocomplete="off"
         placeholder="кроссовки, шрифт, кофе…  или спроси словами и нажми Enter">
  <div class="plan" id="plan" hidden></div>
  <div class="chips" id="cats"></div>
  <div class="chips" id="tags"></div>
</div></header>

<main>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" hidden>Ничего не нашлось</div>
  <button class="more" id="more" hidden>Показать ещё</button>
</main>

<footer>Ссылки из одного телеграм-чата. Пополняется само.</footer>

<script>
const $ = s => document.querySelector(s);
let state = { q: "", category: "", tag: "", offset: 0 };
let total = 0;

const esc = s => (s || "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function card(it) {
  const img = it.image
    ? `<img class="thumb" src="${esc(it.image)}" loading="lazy" alt=""
         onerror="this.remove()">` : "";
  const tags = it.tags.slice(0, 4).map(t =>
    `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join("");
  const q = it.quotes[0];
  const quote = q
    ? `<div class="q"><b>${esc(q.author)}</b>: ${esc(q.text.slice(0, 220))}</div>` : "";
  const by = it.by ? `<span class="dot">·</span>${esc(it.by)}` : "";
  return `<a class="card ${it.dead ? "dead" : ""}" href="${esc(it.url)}"
      target="_blank" rel="noopener noreferrer">
    ${img}
    <div class="body">
      <div class="t">${esc(it.title || it.domain)}</div>
      <div class="d">${esc(it.description)}</div>
      ${quote}
      <div class="tags">${tags}</div>
      <div class="meta">${esc(it.domain)}<span class="dot">·</span>${esc(it.date)}${by}
        ${it.dead ? '<span class="dot">·</span>не открывается' : ""}</div>
    </div></a>`;
}

async function load(reset) {
  if (reset) state.offset = 0;
  const p = new URLSearchParams({
    q: state.q, category: state.category, tag: state.tag, offset: state.offset,
  });
  const r = await fetch("/api/search?" + p);
  const data = await r.json();
  total = data.total;
  const html = data.items.map(card).join("");
  if (reset) $("#grid").innerHTML = html; else $("#grid").insertAdjacentHTML("beforeend", html);
  $("#count").textContent = total ? `${total} ${plural(total)}` : "";
  $("#empty").hidden = total > 0;
  state.offset += data.items.length;
  $("#more").hidden = state.offset >= total;
}

function plural(n) {
  const t = n % 100, o = n % 10;
  if (t > 10 && t < 20) return "ссылок";
  if (o === 1) return "ссылка";
  if (o >= 2 && o <= 4) return "ссылки";
  return "ссылок";
}

function chips(el, items, key, label) {
  el.innerHTML = items.map(([name, n]) =>
    `<span class="chip ${state[key] === name ? "on" : ""}" data-${key}="${esc(name)}">
       ${esc(label ? label(name) : name)}<b>${n}</b></span>`).join("");
}

const NAMES = {
  clothing: "одежда", tech: "железо", software: "софт", site: "сайты",
  article: "статьи", video: "видео", food: "еда", place: "места", misc: "разное",
};

document.addEventListener("click", e => {
  const cat = e.target.closest("[data-category]");
  const tag = e.target.closest("[data-tag]");
  if (cat) {
    const v = cat.dataset.category;
    state.category = state.category === v ? "" : v;
    boot(); return;
  }
  if (tag) {
    e.preventDefault();
    const v = tag.dataset.tag;
    state.tag = state.tag === v ? "" : v;
    boot(); return;
  }
});

let timer;
$("#q").addEventListener("input", e => {
  clearTimeout(timer);
  state.q = e.target.value;
  $("#plan").hidden = true;
  timer = setTimeout(() => load(true), 180);
});
$("#q").addEventListener("keydown", e => {
  if (e.key === "Enter") { clearTimeout(timer); ask(e.target.value); }
});
$("#more").addEventListener("click", () => load(false));

// enter asks the model to turn the question into search parameters. it never
// writes an answer of its own — everything shown below comes from the vault
async function ask(question) {
  if (!question.trim()) return;
  const plan = $("#plan");
  plan.hidden = false;
  plan.textContent = "думаю…";
  let r;
  try {
    r = await fetch("/api/ask", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ q: question.slice(0, 200) }),
    });
  } catch (err) { plan.textContent = "не дозвонился"; return; }
  if (r.status === 429) { plan.textContent = "слишком часто, подожди минуту"; return; }
  if (!r.ok) { plan.textContent = "не получилось, ищи словами"; return; }

  const data = await r.json();
  const p = data.plan;
  state = { q: p.query, category: p.category, tag: p.tag, offset: 0 };
  $("#q").value = question;
  const bits = [p.query && `<b>${esc(p.query)}</b>`,
                p.category && esc(NAMES[p.category] || p.category),
                p.tag && "#" + esc(p.tag)].filter(Boolean).join(" · ");
  plan.innerHTML = `${esc(p.reply)}${bits ? " → " + bits : ""}
    <span class="x" id="reset">сбросить</span>`;
  $("#reset").onclick = () => {
    state = { q: "", category: "", tag: "", offset: 0 };
    $("#q").value = ""; plan.hidden = true; boot();
  };

  total = data.total;
  $("#grid").innerHTML = data.items.map(card).join("");
  $("#count").textContent = total ? `${total} ${plural(total)}` : "";
  $("#empty").hidden = total > 0;
  state.offset = data.items.length;
  $("#more").hidden = state.offset >= total;
  const f = await (await fetch("/api/facets")).json();
  chips($("#cats"), f.categories, "category", n => NAMES[n] || n);
  chips($("#tags"), f.tags, "tag");
}

async function boot() {
  const r = await fetch("/api/facets");
  const f = await r.json();
  chips($("#cats"), f.categories, "category", n => NAMES[n] || n);
  chips($("#tags"), f.tags, "tag");
  await load(true);
}
boot();
</script>
</body>
</html>
"""
