# Archiving pages: is it needed

Links from a chat rot. A product goes out of stock, an article moves behind a
paywall, a shop closes. The question is whether to keep a copy of the page, and
at what cost.

## Short answer

For a second brain built from a chat, **metadata plus the image is enough**.
Archiving every page in full costs disproportionately much in disk and time, and
gets used once a year.

The exception is articles (`category: article`). There the text *is* the value,
and `trafilatura` already pulled it during enrichment. Putting the markdown text
straight into the note body gives you the archive and full-text search at once,
for free.

## If you do need full copies

### monolith

`monolith` 2.10.1 — a Rust CLI that packs a page into **one self-contained HTML
file**: CSS, images and fonts inlined as base64.

```bash
brew install monolith
monolith -o page.html https://example.com
```

Measured on real pages: a typical result is **0.5–3 MB** per page. A product page
with a photo gallery goes to 5–8 MB.

Pros: one file, opens in a browser ten years later, sits next to the note in
`attachments/`.
Cons: JS isn't executed — on an SPA (Zara and friends) you get an empty shell.
Those need browser rendering.

### single-file-cli

`single-file-cli` — the same idea but through a real Chrome, so it saves SPAs
correctly. Pricier: it drags in a headless browser, 3–10 seconds per page.

The sensible way is **selective**: monolith by default, single-file for the
domains where monolith came back empty.

### ArchiveBox — skip it

A full archiving system: WARC, PDF, screenshot, DOM, media via yt-dlp, its own
web UI. Powerful and serious.

For our task it's overkill. A separate service with a database and a scheduler,
tens of gigabytes, all for something you'll hardly ever open. If the task turns
into "keep everything forever", come back to it.

### Wayback Machine

`web.archive.org/save/<url>` — Save Page Now. **It now requires S3-style keys**
(created in an archive.org account); anonymous saves are throttled hard.

The point is that someone else does the storing. Writing the archive copy's URL
into frontmatter (`wayback_url`) is cheap and more reliable than your own disk.

Checking for an existing copy is free and keyless:

```
https://archive.org/wayback/available?url=<url>
```

Worth filling this field in for every link: if a copy already exists, you got the
archive for free.

### archive.today

Write it off. Aggressive anti-automation, captchas, an unstable API, periodic
region blocks. By hand yes, in a pipeline no.

## Practical recommendation

```
category: article  → markdown text in the note body (trafilatura, already there)
everything else    → og:image locally in attachments/ + wayback_url
status: dead       → try to find it in Wayback, put the archive link in
```

The local image matters on its own: an `og:image` from a shop goes stale along
with the product, and the picture is exactly how you recognize a thing in the
Bases card view. One image is 50–200 KB, so 2000 links means 100–400 MB.
Acceptable.

Turn on full archiving through monolith case by case — for the links you marked
important by hand.
