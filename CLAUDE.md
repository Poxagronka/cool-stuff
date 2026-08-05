# cool-stuff

Collects links from the "cool stuff" Telegram chat and from the owner's own
saved messages into an Obsidian vault. The history was pulled once through
Telethon; new links are caught by a bot on Fly.io.

## How it is put together

`src/tglinks/` is the pipeline: `containers` (a wishlist page is opened and
replaced by the links inside it) → `canon` (url canonicalisation and dedup) →
`enrich` (the enrichment ladder, `sites` for per-site resolvers, `pagetext` for
the clean page text) → `triage` (only for privately saved links) → `categorize`
→ `vault` (notes) → `gitvault` (push). Every model call goes through `llm`: one
forced tool call, free provider first, Anthropic as the fallback. Everything the
model writes into the vault — titles, descriptions, keywords — is English; the
chat quotes keep the language they were said in.
`app.py` is the webhook and the site (`portal` for the index, `textsearch` for
the matching, `web` for the page, `graph` for the tag web it draws on a canvas,
`sheet` for the panel that opens on a card and shows the whole note,
`ask` for turning a question into search words, `translate` for a non-english
query in the plain search box: the free MyMemory endpoint under a daily
character budget first, a model only when that finds nothing). The site is
invite-only: `accounts` (invites, passwords, sessions), `authweb` (the sign-in,
join and profile pages), and `scripts/invite.py` which mints the first invite on
the machine. One account is an admin (`scripts/admin.py` grants it) and can take
a card off the site; `hidden` keeps those urls and the profile page puts them
back. You arrive on an invite link and pick a name and a password; you
come back through `/signin`. `brand` holds the favicon and the header glyph.
`saved` is the scheduled pull of the owner's Saved Messages: the Telethon
session off the volume, a watermark in `state`, one run at a time, and the
clusters handed to the same triage gate the backfill uses.
`scripts/backfill.py` is the one-off dump, `--saved` for Saved Messages.
Details in `research/` and `PLAN.md`, the state of the environment in
`SETUP.md`.

## Paths already stepped on

- The Bot API cannot see history and there is no way around it. MTProto only →
  [knowledge/telegram/rules.md](knowledge/telegram/rules.md) R1
- Turn the bot's privacy mode off BEFORE adding it to the group, otherwise it
  stays silent → same file, R2
- "cool stuff" is a plain group, not a supergroup: `t.me/c/` links do not exist
  for it → same file, R4
- HTTP 200 does not mean a real page: challenge stubs come back with a 200 and
  a plausible title →
  [knowledge/scraping/rules.md](knowledge/scraping/rules.md) R1
- Run the dump from the laptop, not the server: shops give a datacentre IP less
  → same file, R4
- `accept-encoding: br` without a decompressor breaks everything: the server
  sends compressed bytes, httpx will not unpack them, metadata comes out empty
  → same file, R7
- Instagram/TikTok/Spotify/App Store are only readable through their own
  endpoints; Pinterest is not readable at all → same file, R8
- A profile page gives no picture, so the brand's own site is guessed from the
  handle — and the guess is checked by backlink, never by name: matching the
  name put Oracle on an account called `_____portal` → same file, R16
- "This project does not have the access to Custom Search JSON API" is Google's
  own clock, not a setting: enabled api, correctly scoped key, still 403 →
  same file, R17
- Context stops at the next link, otherwise the description ends up on the
  wrong thing →
  [knowledge/telegram/rules.md](knowledge/telegram/rules.md) R8
- A signed webhook call is not proof of where the update started: a stranger's
  DM is signed the same way, so the chat is checked too →
  [knowledge/telegram/rules.md](knowledge/telegram/rules.md) R9
- Privacy belongs to the message, not the cluster: a link the group also posted
  publishes only its public half → same file, R10
- A fetch checks the resolved address on every redirect hop, and a blocked url
  degrades like an unreachable one →
  [knowledge/scraping/rules.md](knowledge/scraping/rules.md) R10
- Clusters merge on the resolved url; the old note is deleted only when the url
  inside it proves whose it is → same file, R11
- And the note a merge gives up can already belong to another link, so
  `retire()` reads the url out of the file before unlinking → same file, R14
- A wishlist is not a link, it is forty links: the page is swapped for its
  contents before the first row is written, and neither notion nor
  mywishlist.online puts those contents in the html → same file, R13
- A title that only changed case is one file on a mac, and deleting the "old"
  name threw away 19 notes in one run → same file, R12
- The root filesystem of a Fly machine is ephemeral, state lives on the volume
  only → [knowledge/deployment/rules.md](knowledge/deployment/rules.md) R1
- Fly health checks keep the machine awake, so there are none → same file, R5
- And `suspend` stays over `stop`: 0.65s to resume against 9.1s to boot cold →
  same file, R14. The memory is measured, not guessed → same file, R15
- An open ssh session is not traffic: a long job on the machine is suspended
  under you, resumes intact when something wakes it, and needs a `/health` poke
  beside it to finish → same file, R12
- And therefore no timer in the app either: a frozen process has no clock, so
  the periodic work hangs off the wakes and the cron lives on the Fly side →
  same file, R12
- The saved-messages session cannot be created on the server, and a login that
  is gone reads an empty history exactly like a healthy run does →
  [knowledge/telegram/rules.md](knowledge/telegram/rules.md) R12
- The saved pull reads forward from a watermark, and an empty watermark means
  "what the laptop already imported", not zero → same file, R13
- The image ships `scripts/` too, and `ssh console -C` needs an absolute path
  → same file, R8
- No `WEBHOOK_SECRET` or `TG_CHAT` means the app will not boot, on purpose →
  same file, R9
- The site's door is shut by default, and a new route is protected by not being
  on the open list → [knowledge/accounts/rules.md](knowledge/accounts/rules.md)
  R7
- There is no permanent personal link: it was a bearer token living forever in
  browser history → same file, R1
- Spending an invite and creating the account are one transaction → same file,
  R5
- An account from before passwords cannot sign in and still holds its name →
  same file, R11
- Admin is a column granted from the machine, never a name compared inside a
  handler, and the button on the card is not the check → same file, R12
- Hiding is a decision about the site, so it lives in the database and the
  collector never learns of it: a hidden link still deduplicates and still
  collects context →
  [knowledge/portal/rules.md](knowledge/portal/rules.md) R18
- The model in the site search writes no answer, it only calls `search` →
  [knowledge/portal/rules.md](knowledge/portal/rules.md) R1
- The model's category guess is a hint, not a filter: on zero hits the search
  runs again without it → same file, R5.2
- The tag web is a canvas because tag strings are model-written text off the
  web, and nothing off the web is parsed as markup → same file, R8
- The web draws fourteen bubbles, not sixty — that, not the drifting, is what
  made it unreadable. It does drift, on purpose: the search ends in a couple of
  seconds and then the layout crawls at a pixel a frame, for ever
  → same file, R7.1–R7.3, R7.10
- The web as it looks when it is right, with every number and what each one
  replaced: `fcfcde7`, written down in
  [knowledge/portal/knowledge.md](knowledge/portal/knowledge.md). Restore
  `graph.py` from there rather than tuning it again
- Fourteen is what a laptop holds. Every length in the web is a share of the
  room one bubble has, and a bubble is a rectangle the width of its label —
  circles that clear each other still had their words running together
  → same file, R7.3, R7.5, R7.6
- And a settled layout is not a readable one: real counts sit within a factor of
  three of each other, the overlaps the solver leaves come out by hand, and the
  web is tugged out to a box that grew for the crowd. The three hundred frames
  of searching are the animation, though — solving them off screen was quicker
  and dead → same file, R7.7–R7.9
- One stylesheet in one string, so a class name used twice is a silent bug: a
  second `.mark` laid an invisible absolute box over the profile link
  → same file, R15.1
- A card is not a link. Only the domain chip leaves for the site, and the
  handler order tag → anchor → card is what keeps that true → same file, R10
- A card is not a button either: the title inside it is, because a button
  holding four buttons and a link is read out as one control → same file, R15
- A placeholder nobody filled in ships as the literal text `{sheet_js}` and
  breaks nothing loudly, so a test looks for it → same file, R12
- `instagram` is the biggest tag in the vault and says nothing, and neither
  does `brand`: where a link lives, and what shape it is, never become bubbles
  → same file, R7.4
- A lookup table indexed with a model-written key answers `__proto__`, and
  `esc()` says nothing about `javascript:` → same file, R13
- Every request takes a ticket: a late reply from the previous filter would
  otherwise append to the new results → same file, R14
- The vault moves while it is being walked: a `git pull --rebase` deletes notes
  out from under `rglob`, so a file that cannot be stat'd is skipped, not fatal
  → same file, R19
- Fly has no rename, `.env` copies empty secrets silently, and the webhook
  keeps pointing at the old host →
  [knowledge/deployment/rules.md](knowledge/deployment/rules.md) R10
- Uploading a database over the volume takes the accounts with it: they exist
  nowhere else → same file, R11
- And carrying the laptop's vault over doubles notes twice over: mac `tar`
  packs `._*` siblings, and every case-only rename the mac declined lands as a
  second note. `entry.note_path` says which one is real → same file, R13
- Every input to the search has a ceiling: the cost is the vocabulary walk
  behind each word → same file, R9
- A model asked for an array will sometimes send a comma-separated string.
  Coercing it is not politeness, discarding it once cost 316 notes their
  keywords → [knowledge/models/rules.md](knowledge/models/rules.md) R5
- A provider that answers with anything but a well-formed tool call counts as
  unavailable and the chain moves on → same file, R2
- A tag is a shelf, not a description: a model tagging one note at a time
  writes `athens-radio` and `online-software`, so it is shown the tags the
  vault already uses and the broad word is asked for by position → same file, R9
- A tool payload is checked against the declared schema first: `{"keep":
  "false"}` is truthy and would publish a private link → same file, R7
- Anything built out of the vault goes in the user turn as data, never in the
  system message → same file, R8
- The triage gate is the only thing between a saved-messages link and the
  vault, so no verdict drops the link → same file, R6
- Which free model can actually do which job, and which ones look free but are
  not → [knowledge/models/knowledge.md](knowledge/models/knowledge.md)

## Locally

```
.venv/bin/python -m pytest tests/ -q
ruff check src scripts tests
```

Comments in the code are in English and start with a lowercase letter (a hook
checks this). Emoji in the sources only as escape sequences.
