# Public portal — rules

**R1.** The model behind the search box does not write the answer. Its only
output is a call to the `search` tool with query/category/tag/reply fields,
forced through `tool_choice`. The user never sees free text from the model, so at
worst an injection in the question spoils the search query instead of replacing
the answer.

**R2.** Note contents never reach the model. It sees only the question, the list
of categories and the top tags. As long as that holds, an injection from a page
that made it into the database cannot reach the chat line.

**R3.** Whatever the model returns is still filtered on the server: category and
tag must come from the known lists, query and reply go through a character
allowlist and a length cap. The model is not a trusted source, not even our own.

**R4.** The limit is 10 questions per minute per address, a question is at most
200 characters, and identical questions are served from cache. The portal is
public and the owner pays for the tokens.

**R5.** Search is tokenised, not substring. Both the notes and the question are
cut into words, folded to latin (so «найк» and "nike" are the same token) and
matched term by term: exact, then prefix, then a difflib near-match for typos,
then substring, each worth less than the one before. A word's contribution is
its IDF, so a rare brand name outweighs "app" appearing in half the vault, and a
hit in the title or keywords counts triple a hit in the body. See
`src/tglinks/textsearch.py`.

**R5.2.** The model's `category`/`tag` guess is a hint, not a filter. When the
plan returns no hits, the server drops the category and tag and searches again
on the words alone. Without that, one wrong guess ("потолочные вентиляторы" →
`tech`) turns a perfectly good query into an empty page.

**R5.1.** Search has two modes. The search box is strict mode: every word must
match, since a person knows what they are typing. A question through the model is
`any` mode: the model's words are a guess at synonyms, and requiring all of them
means finding nothing. There one match is enough, and ranking by the number of
matched words puts the best result on top.

**R6.** Page text that goes into the classifier prompt is wrapped in a marker
saying it is data, not instructions. A page from the internet is untrusted input,
and the only thing protecting the note description is structured output through
forced tool use.

**R7.** The tags are a web, not a cloud: a force-directed graph of bubbles on
threads that doubles as the filter. `GET /api/graph` answers
`{nodes, edges, picked}` for whatever the current results are — nodes are the
top 14 tags with their counts plus any tag already picked, edges are the pairs
that appear on the same note. A picked tag is kept even when the narrowed
results push it out of the top slice: a web missing the node you are standing
on reads as a bug.

**R7.1.** Fourteen, not sixty. Sixty bubbles in a box 380 pixels tall sat on
top of each other with their labels overlapping, and the layout never settled,
so the whole thing shook. Narrowing is what makes the web readable and it comes
for free: `graph()` is handed the already-filtered results, so picking a tag
drops every big tag that does not keep company with it and the next fourteen
are drawn from what is left. There is no separate "show the neighbours" path.

**R7.2.** Nothing on the web drifts by itself. Each bubble used to carry a
sine-wave wobble, which meant a `requestAnimationFrame` loop that never ended,
hit-testing against a moving target, and a picture that would not hold still
long enough to read. The solver now runs until the layout comes to rest and
then the loop stops dead; hovering, dragging or picking wakes it for one frame.
Under `prefers-reduced-motion` nothing reflows at all: taking hold of a bubble
and letting go of it only ask for a repaint, where otherwise they would re-solve
the layout and slide the whole web around a finger. And only the pointer that
took a bubble can move or release it — a second finger crossing the canvas was
steering and ending the first one's drag.

**R7.4.** Where a link lives is not what it is about. `instagram` (36 notes),
`youtube`, `tiktok`, `twitter`, `spotify`, `pinterest`, `wikipedia` and the
format tags `video` and `image` were the biggest bubbles on the web and none of
them narrows anything: every second link is on instagram. `portal.SOURCE_TAGS`
keeps them off the web and out of `top_tags()`, so the model never plans a
search around one either. They stay on the note and in the panel — they are
context, just not a way in. Both counts go through `portal._ranked()`, which is
the only place the list is applied.

**R7.3.** The gap that keeps two bubbles apart is `r + r + 34`, not
`r + r + 10`. The label hangs under the bubble and is wider than it is, so
circles that merely fail to touch still have their words running together.

**R8.** The web is drawn on a canvas, and that is a security decision as much
as a performance one. Tag strings are written by a model reading arbitrary web
pages, so they are hostile text: labels go through `fillText` and the
screen-reader fallback list through `textContent`, and nothing off the network
is ever parsed as markup. A dozen nodes redrawn while the layout settles cost
nothing. The css and js live in `src/tglinks/graph.py`; `web.py` interpolates
them.

**R9.** Every input to the search has a ceiling, because the expensive part is
not the match but the vocabulary walk behind each word. A question is 200
characters, the tokeniser reads 8000 characters and stops at 500 words, at most
8 tags are honoured, a page is at most 120 items, and the word-expansion cache
holds 2048 entries with the oldest evicted. Misses are the dangerous half of
that cache: cached, they grow with every new bit of nonsense typed until the
index reloads; uncached, a pasted wall of text turns one request into thousands
of walks. Neither a person nor a note comes anywhere near these numbers.

**R10.** A card is not a link. The whole card used to be one `<a>` to the site,
which meant there was nowhere to put the rest of the note. Now the card is an
`<article data-open="url">` and only the small domain chip leaves for the site;
clicking anywhere else opens the note panel. The document-level click handler
checks in this order: a `[data-tag]` chip filters, anything inside an `<a>` is
left alone, and only then does `[data-open]` open the panel. Get that order
wrong and the outbound link stops working, or every tag chip opens a panel.

**R11.** The note panel is the note. It shows the whole front matter as a
properties table in the vault's own order, the description, and every chat
quote rather than the first one — the same thing Obsidian shows when the file
is opened, which is the point. `Item.public()` therefore ships `keywords`,
`confidence`, the untruncated `shared_at`, `source` and `status` alongside the
fields the card needs. The css, markup and js live in `src/tglinks/sheet.py`,
the same arrangement as `graph.py`.

**R13.** Two things on the page are hostile-text traps that escaping does not
cover. A lookup table indexed with a model-written key (`NAMES[it.category]`)
answers `__proto__` with something inherited, and the caller then tries to
escape an object: `look()` asks `Object.hasOwn` first. And a url out of a note
is not safe merely because its quotes are escaped — `javascript:alert(1)`
survives `esc()` whole — so `outlink()` shows anything that is not plainly
`http(s)` as dead text.

**R14.** Every request the page makes takes a ticket and a late reply holding an
old one is dropped. Without it, switching filters while "load more" is in flight
appends the previous filter's cards to the new results, and two clicks on "load
more" fetch the same offset twice. `load()` and `ask()` share one counter,
because the question and the search box paint the same grid. Typing spends a
ticket on the keystroke, not when the 180ms debounce fires: an answer landing
inside that window would otherwise overwrite the query sitting in the box, and
the scheduled search would then go looking for it.

**R15.** Anything clickable on the page is a `<button>` or an `<a>`, never a
span with a handler. The tag chips were spans, which meant the keyboard could
not pick a tag at all; as buttons they answer Enter and Space themselves and the
existing click handler does the rest, with no keyboard code of its own. The
card is the one thing that is not a button: the title inside it is, because a
button holding four other buttons and a link is read out as a single flattened
control. The mouse still gets the whole card through `data-open` sitting on
both. The panel is a real modal: tab cycles inside it — the listener is on the
document, so focus that has already slipped out is pulled back — `/` is ignored
while it is open, and closing hands focus back to whatever opened it, or to the
search box when that card is gone. Picking a tag from inside the panel lands on
that tag's crumb instead: the card underneath is about to be replaced by the
answer.

**R12.** The page is assembled by `str.replace` over a template full of
javascript braces, so a placeholder that nobody filled in ships as the literal
text `{sheet_js}` and the page half-works with no error anywhere. A test
matches `(?<!\$)\{[a-z_]+\}` against the rendered page; the lookbehind is what
keeps it from tripping over every `${name}` in the javascript.
