# Metadata enrichment — rules

**R1.** HTTP 200 does not mean the page is real. Cloudflare and friends return a
stub with status 200 and a plausible `<title>` like "Reddit — Please wait for
verification". Check the text for challenge-page markers, otherwise the garbage
wins the tier race and gets stored as valid metadata.

**R2.** Read up to `</head>` and drop the connection. An average page is ~550 KB,
an average head ~47 KB: the metadata sits in the first few percent, the rest is
wasted traffic and time.

**R3.** oEmbed from X, Bluesky and Mastodon has no `title` field — only `html`
with the post text and `author_name`. A naive "there is a title, so it worked"
check will skip them.

**R4.** Run the history backfill from the laptop, not the server. A home IP is
residential, and the stores hand it metadata they refuse to give a datacenter
range.

**R5.** Judge tiers by "did meaningful metadata come back", not by "did a
response come back". A tier that returned a stub must lose to a tier that
returned a real title.

**R6.** A note name is the link title and nothing else: a date and domain at the
start turn the result list into a column of noise, and they are in the properties
anyway. Links without metadata get a generic title, so several tiktoks end up with
the same name — check the url in the file that is already there, and if it belongs
to another link, append a suffix from the url hash.

**R7.** Do not advertise `accept-encoding: br` (or `zstd`) while httpx cannot
decompress them. The server trusts the header and sends a compressed body, httpx
returns it as is, the parser sees binary garbage and the metadata comes out empty.
This is exactly why instagram and pinterest were considered unreachable for a long
time. Only `gzip, deflate`.

**R8.** JS-driven sites (Instagram, TikTok, Spotify, App Store) give the crawler
an empty shell, but each has one public endpoint with a normal response:
App Store — `itunes.apple.com/lookup?id=`, Instagram — `/p/<code>/embed/captioned/`,
TikTok — redirect from `vm.tiktok.com` to `www.tiktok.com`, then oembed,
Spotify — og tags under a crawler UA. Pinterest gives nothing: both the page and
the internal `PinResource` are closed (403).

**R9.** When there is little metadata (description shorter than ~60 characters),
pull the whole page text, but not raw HTML: drop script/style/nav/header/footer/
aside/form/button, take article/main, throw away one- and two-word lines (those
are menus), and add schema.org JSON-LD and `shortDescription` from the YouTube
player. Do not fetch an image link (`.jpg`) at all.

**R10.** Every fetch checks where it is actually going, on every redirect hop.
Saved messages carry whatever the owner sent himself, including links to the
box this runs on, and following one would hand an internal page to the triage
model. The check is on the resolved address, not on the hostname — a public
name can point at 127.0.0.1 — and it refuses loopback, private, link-local,
reserved, multicast and unspecified, unwrapping `::ffff:127.0.0.1` first,
because that is the same machine wearing a v6 hat. One internal address
anywhere in the answer is enough to refuse the lot. httpx runs each hop back
through the transport, so `GuardedTransport` covers the chain for free;
curl_cffi does not, so that path walks the redirects by hand. `BlockedURL`
subclasses httpx's transport error on purpose: a blocked link then degrades
exactly like an unreachable one and no tier needs new handling.

**R11.** Clusters merge on the resolved url, not only on the normalised one. A
shortener and the shop behind it are two links until somebody follows them, and
two clusters with the same title write the same filename — the second wins and
the first entry points at a note about something else. The oldest cluster keeps
the id, since that is the one the vault and the index already know. The domain
shown for the note is recomputed from the resolved url; the shortener's host is
not what the link is about. When a rename or a merge leaves an old note behind,
it is only deleted if the url inside the file matches the entry it is supposed
to belong to (see R6 — two links can share a stem). The vault is a pushed git
repo, so refusing to delete is always the cheaper mistake.

**R12.** A note whose title only changed case is not a rename on macOS. The
filesystem folds case, so `Gnuhr.md` and `GNUHR.md` are one file: the new note
is written into the old one, the directory keeps the old spelling, and the
tidy-up in R11 then reads the url out of "the old file", finds its own url and
deletes what it just saved. A full regeneration lost 19 of 388 notes this way
before anyone noticed, and nothing complained — the database recorded a
note_path for every entry, the files were simply not there. So `retire` refuses
when the path it is about to unlink is `samefile` as the note just written, and
`write` renames the on-disk entry to the spelling the database is going to
record. Both checks are worth keeping even though Fly runs Linux: the vault is
authored and read on a mac. Verify by counting `entry.note_path` against files
on disk after any bulk run — they must be equal.

The rename the mac declined is still owed, and it comes due the moment the
vault reaches Linux: see deployment R13.

**R14.** A merge never takes a note another link now owns. When two clusters
fold together (R11), the entry that loses keeps a `note_path` remembered from
before, and by then that file can belong to somebody else — R6 gives two
untitled tiktoks the same stem, and the second one to be written is the one the
name now points at. So `retire()` reads the url out of the file and refuses to
unlink it unless that url is the one it came to delete. Dropping the
`url_of(path) != url` check does not fail loudly, it quietly unlinks a stranger's
note and leaves an entry in the database pointing at nothing; the same shape as
the 19 notes in R12. This is pinned by
`tests/test_pipeline.py::test_a_merge_never_takes_a_note_another_link_now_owns`,
which was verified by mutation — remove the check and the test fails.

**R13.** Some links are not a thing, they are a list of things. A wishlist page
holds thirty or forty shops, and stored as itself it becomes one note named
after a person while every shop inside it stays out of the vault and out of the
dedup. `containers.expand` opens such a page and returns what is inside; the
substitution happens in `pipeline.widen`, before the first row is written, so
everything downstream only ever sees ordinary links. A reader that does not
recognise the url returns None and the link travels on untouched — which is the
normal case.

Two shapes are read so far, and they need opposite tricks:

- **notion.site.** The html is a javascript loader with no links in it. The
  page's own endpoint answers though: `POST https://<sub>.notion.site/api/v3/loadPageChunk`
  with `{"pageId": ..., "limit": 200, "cursor": {"stack": []}, "chunkNumber": 0}`.
  The id has to be hyphenated 8-4-4-4-12 — the api refuses the 32 glued hex
  characters the address bar shows. Addresses live in `format.bookmark_url`,
  `format.display_source`, `format.source`, and as `["a", url]` annotations on
  rich-text runs anywhere in `properties`, so the whole property map is walked,
  not just `title`. A block record is nested `value.value` on this api version
  and `value` on the older one. Notion's own hosts are dropped, and so is
  `attachment:...`, which is a file pointer rather than a url. The reference
  page gives 38 links out of 121 blocks.
- **mywishlist.online.** Server-rendered, but not as markup: the page contains
  no item anchors at all, the browser builds them from `var wishlist_products = {...}`
  printed into a script tag. Each item's `redirect_url` is a
  `/x/<shop-host>/<id>` click counter, and that stub is *not* an http redirect —
  it is a two second `<meta http-equiv="refresh">` with an analytics ping in
  between, so the destination has to be read out of the head by hand. Unwrap it
  in the reader: left alone, the vault fills with notes named after an
  interstitial.

**R15.** A page with no `og:image` usually still has the picture, further down
than the ladder looks. The head fetch stops at `</head>` on purpose, so the
image fallback rides the full-document fetch that `body_text` already made for
links with no description: one request answers both questions
(`enrich.full_page`, 2026-08-03). Picking is the hard half, not fetching — the
first `<img>` on a shop page is the logo, the second a payment badge, and
somewhere below sits a 1×1 tracking pixel. `pictures.pick` scores instead of
taking in order: JSON-LD about the page's own subject first, then the main
column, then declared size, with tracking hosts, svg, `data:` and
logo/icon/badge/payment filenames thrown out. Structured data is trusted about
*which* picture matters but not about *what the file is* — a shop that declares
its header logo as the page image is still declaring a logo, so the filename
filter runs over the JSON-LD candidates too. Measured on the vault's own
imageless entries: 20 of 40 non-social pages give a usable photo, and the misses
are pages that genuinely have none. Below that is Google's Programmable Search
(`pictures.from_search`), which is a tail and not a tier: the free quota is 100
queries a day, so it runs only after the document was read and refused, and no
key at all just ends the ladder one rung earlier. The engine must be created
with "Search the entire web" chosen *in the create form* — the toggle is
permanently disabled afterwards on a site-restricted engine — and "Image search"
turned on, or `searchType=image` answers with nothing.
