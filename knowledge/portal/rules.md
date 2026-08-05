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

**R7.5.** Fourteen is what a laptop holds, not what a phone holds. The server
still sends fourteen; the page draws `holds()` of them — one per 13000 square
pixels of box, floor of six — and the tail it drops is the smallest tags, never
a picked one. Everything else about the drawing is a share of `unit`, the room
one bubble has (`sqrt(area / count)`): the radii, the type size, the thread
lengths, where a new bubble is born. Nothing is a pixel constant, because a
layout tuned at one width is a mess at every other one, and a resize lays the
last answer out again rather than stretching what is on screen.

**R7.6.** The web is put in the middle as one thing, not bubble by bubble. The
spring pulling every bubble at the centre had its x component multiplied by the
box aspect, which on a laptop strip came to a fifth of the y one and let the
whole web drift out to both edges. A weak spring plus one eased translation of
the whole set per step keeps it centred at any shape of box.

**R7.7.** The counts in a real vault are all within a factor of three of each
other, so the size of a bubble is where its count falls between the smallest and
the biggest actually on screen — not what fraction it is of the biggest. On prod
data (57 down to 21 links) `R0 + RK * sqrt(count / top)` drew fourteen circles
of 27 to 36 pixels: near enough identical, and fourteen bubbles of one size have
no reason to prefer any arrangement, which is exactly what "the tags are going
mad" looked like. Normalising the range instead spreads them 8 to 34.

**R7.8.** A settled layout is not the same thing as a readable one, and three
of the four things that fixed this happen off screen:

- The solver runs all but the last sixty steps synchronously in `kick()`. What
  the eye read as the tags panicking was the search itself — three hundred
  frames of bubbles hunting for their places. The sixty that are left are the
  web closing up, which reads as motion with a purpose. Fourteen bubbles solved
  in one go cost a few milliseconds.
- The threads win over the separation in places and the solver stops with a pair
  still touching, so `unpack()` takes the leftovers out by hand once it has
  stopped — no springs, no velocities, just move the pair apart until the boxes
  clear.
- A hub is on many threads at once (`accessories` is on ten of the forty-one)
  and the pull of all of them together dragged it straight through its
  neighbours, so each bubble's share of a thread is divided by the square root
  of how many threads it holds.
- Where the forces balance is not where the box is. On a laptop strip the web
  came to rest as a clump 417 pixels wide inside 1152, with empty sides. So the
  settled web is pulled out to the box (`spread()`), the two axes separately and
  at most doubled: a strip needs the width, a phone the height. Moving bubbles
  apart can never create an overlap, so this is safe after `unpack()`.

**R7.9.** How much room the web has is not the stylesheet's decision alone.
`stretch()` grows the box downwards for as many bubbles as there are — the
target is area per bubble, so a wide box already has it and keeps the height the
css gave it, while a phone finds the same area going down (up to 620px). The box
never shrinks below the css height, that is the shape of the page. It runs from
`apply()` as well as from `measure()`: growing the box on new data and then
laying the web out at the old height puts bubbles outside it.

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
them narrows anything: every second link is on instagram. The same goes for a
tag naming a shape rather than a subject: `brand` sat on 16 notes, seventh
biggest in the vault, and every one of them was a shop selling something.
`portal.SOURCE_TAGS` and `portal.VAGUE_TAGS` join into `portal.OFF_WEB`, which
keeps them off the web and out of `top_tags()`, so the model never plans a
search around one either. They stay on the note and in the panel — they are
context, just not a way in. Both counts go through `portal._ranked()`, which is
the only place the list is applied.

**R7.3.** What has to stay apart is not two circles. The label hangs under the
bubble and is usually wider than it, so a bubble is a rectangle: the measured
width of its text and a line of type below the circle. A pair whose boxes
overlap gives way along whichever axis is nearer to free — pushing along the
line of centres is what let `running` and `hiking` slide into one word. The
sides of the box hold in the text too: holding the centre of the circle inside
was cutting `accessories` and `home-deco` off at the edge.

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

**R15.1.** The whole page is one stylesheet in one string, so a class name used
twice is a silent bug. `.mark` was the header wordmark; a second `.mark` written
later for the tile a pictureless card gets carried `position: absolute;
inset: 0`, won on order, and turned the words "cool stuff" into an invisible box
the width of the header sitting on top of the profile link. Nothing looked
wrong — the link simply stopped taking clicks. The tile is `.tile` now, and
`test_web.py` counts every class declared at the top level of the sheet and
fails on a repeat.

**R12.** The page is assembled by `str.replace` over a template full of
javascript braces, so a placeholder that nobody filled in ships as the literal
text `{sheet_js}` and the page half-works with no error anywhere. A test
matches `(?<!\$)\{[a-z_]+\}` against the rendered page; the lookbehind is what
keeps it from tripping over every `${name}` in the javascript.

**R16.** Folding a word to latin is a bet, and the search has to know it made
one. `textsearch.latin()` transliterates cyrillic so that "хока" and "hoka"
meet on one term, but it runs on every word, so an ordinary russian word comes
out as a latin string the vault has never held: "бег" becomes "beg". Nothing
matched that, the expansion fell through to `difflib` guessing at a
misspelling, and it answered with "be" — nine notes carry it, and none of them
are about running. A query token therefore carries whether it was folded
(`query_tokens`), and a folded one is expanded by exact and prefix only
(`no_guessing`): prefix has to stay, because the vault keeps the chat's russian
captions and "куртк" is the kurtka inside one. The wrong fixes here are adding
"be" to `NOISE`, which patches one collision, and raising the fuzzy cutoff,
which costs english typos their match.

**R17.** A foreign query is searched in both alphabets at once, never as a
fallback. The vault is written in english and keeps russian captions verbatim,
so a russian word has matches on both sides; translating only after the lexical
search came back empty meant that matching a single russian caption hid the
whole english half. `both_alphabets()` runs the query as typed and translated
and merges the two lists on url, each note at its best rank in either. This is
also why R16 matters more than it looks: nine junk hits are not zero, so the
old fallback never fired at all. Translations are memoised per query string —
the box searches on every keystroke and MyMemory is metered by the character.

**R18.** Hidden is a property of the url and it lives in the database
(`hidden_url`), never in the note. The vault is the collection and hiding is a
decision about the site: written into the front matter it would go to git, and
the collector would have to learn about it. It does not — a hidden link still
deduplicates and still gets the next thing the chat said about it appended to
its note, exactly as before. The set reaches the portal once: `app` reads it at
startup and hands it to `portal.Index`, which sorts the parsed notes into
`items` and `buried` at load time. Everything the page shows — the results, the
counts, the tag web — is built from `items`, so nothing has to remember to
filter, and no request touches the database for it. `/api/hide` and
`/me/unhide` write the row and call `index.set_hidden()`, which is one reread of
four hundred files for a list that changes twice a year.

**R19.** The vault moves while it is being read, and every walk of it has to
survive that. `Index._shape()` used to stat each path `rglob` handed it with
nothing around the call, which reads as safe and is not: `rglob` is a generator,
so the tree is listed lazily while the loop runs, and `gitvault.commit_push`
awaits `git pull --rebase` in a subprocess the event loop is free to leave. A
search asking whether the index is stale then walks a `links/` directory that a
rebase is rewriting underneath it, and a path that existed a moment ago is gone
before it is asked how old it is. Under real concurrent churn that was
`FileNotFoundError` on 117 of 300 `_shape()` calls — a 500 out of `/api/search`
through the handler, and through the collector an exception inside `handle()`
before `commit_push` ever ran, with Telegram already handed its 200 and no
retry coming. `_shape()` now skips a file it cannot stat, the same way `parse()`
directly above it swallows `OSError` on purpose. The failure is in the safe
direction: a missed file makes the shape come out smaller than the truth, which
is a difference, and a difference is what makes the next check reload.
