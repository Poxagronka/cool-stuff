# Rollout plan

## Step 0. Recon (one evening) — before anything else

Pull the chat with Telethon using the `InputMessagesFilterUrl` filter and count:

- how many messages contain links at all
- how many unique URLs are left after canonicalisation
- the top domains
- how many links are already dead (a quick HEAD run)

**Everything else depends on this.** If there are 300 unique links, no pipeline
is needed — an evening script and manual sorting will do. If there are 5000,
building one makes sense.

You need an `api_id` / `api_hash` — **we already have them** in
`/Users/poxagronka/abooks_bot/.env` (`TG_API_ID`, `TG_API_HASH`). They are
issued per account, not per app, so they can be reused freely. Nothing to
register.

## Step 1. Backfill the history

Telethon 1.44 (from Codeberg, not GitHub — that one is an archive),
`iter_messages` filtered by URL. One or two seconds of pause between
iterations. Not from the main account.

Store the raw material as is in SQLite: `raw_url`, `chat_msg_id`, author, date,
message text, reply_to, `MessageMediaWebPage` if there is one.

**Do not normalise at this step.** The rules will change and the keys will have
to be recomputed, so an untouched original is needed.

→ [research/01-telegram-extraction.md](research/01-telegram-extraction.md)

## Step 2. Canonicalisation and dedup

The order of operations is strict:

```
expand ClearURLs redirections (offline, no network)
  → RFC normalisation (url-normalize 3.0.0, WITHOUT filter_params)
  → ClearURLs rules + rawRules
  → our own canonicalisers (Amazon /dp/ASIN, AliExpress item/<id>.html, YouTube watch?v=)
  → parameter sorting (last step!)
```

Then resolve redirects, with a detector for "resolved to the bare domain root =
failure". Without it every dead affiliate link collapses into one record.

Three dedup keys: `norm_key` / `resolved_key` / `canonical_key`, with union-find
on top.

→ [research/02-url-canonicalization.md](research/02-url-canonicalization.md)

## Step 3. Metadata enrichment

A ladder; run tiers 2 and 3 in parallel:

```
0. cache (negative results too, with a shorter TTL)
1. oEmbed                                       ~$0, covers social networks entirely
2. httpx + the full set of Chrome headers + cut off at </head>  ~$0, ~55%
2b. chain of social crawler UAs                 ~$0, +a large chunk
3. curl_cffi impersonate="chrome"               ~$0, ~85%  ← stop here
4. residential proxy                            +pennies
5. SeleniumBase --uc --cdp                      JS shells only (Zara)
6. Bright Data Web Unlocker                     the 2-5% that keep resisting
```

A hard time cap per URL. Record which tier a domain came in on, so next time it
starts there.

Mark dead links `status: dead`, **do not throw them away**: the name and the
chat discussion are still there, and that is what people search by later.

→ [research/03-url-metadata.md](research/03-url-metadata.md),
[research/04-anti-bot.md](research/04-anti-bot.md)

## Step 4. Categorisation

Sonnet 5 through the Batch API, structured output with a schema. ~$3 per 2000
links.

Context for the model: the whole reply chain plus messages within ±5 minutes
from the same and neighbouring authors. Without that, "here's a link" stays
without a description.

Output: `category` (one of 8) + `tags` (free-form) + `description` (one sentence
in the model's own words, not a copy of og:description).

→ [research/05-llm-categorization.md](research/05-llm-categorization.md)

## Step 5. Generate the vault

The script writes `.md` straight into `links/YYYY/`. Obsidian picks it up on
start.

File name: `2024-11-03 arcteryx — Beta LT Jacket.md`.

Into the body of the note go **the chat lines word for word**. That is what
turns up when you remember "something about Norway and a membrane" rather than
the model name.

Then:
- turn off Graph view
- install Omnisearch
- assemble `All Links.base` in the UI, then tidy the YAML by hand

Trap: the note is named after the title, so a better title moves the file — and
on a mac a title that changed only in case moves nothing at all, because the
filesystem folds case. After any bulk run, count the note paths in the database
against the files on disk. They must be equal.

→ [research/06-obsidian-vault.md](research/06-obsidian-vault.md)

## Step 6. Work through the inbox

Filter by `status: inbox` and `category: misc` and go in batches. The Bases
table supports multi-select on cells and pasting down a column — an evening's
work.

If `misc` holds more than 10%, a category is missing.

## Step 7. Continuous collection — the Fly.io app

One Python service in webhook mode: Telegram → URL parsing → the same
enrichment ladder → Claude → commit the `.md` into the vault git repository.

The template is copied from `/Users/poxagronka/abooks_bot`, which runs a working
Fly.io bot in webhook mode. Cut the VM from `performance-8x` down to
`shared-cpu-1x` / 512 MB and set `auto_stop_machines = "suspend"`: the machine
sleeps between messages and there is practically nothing to pay for.

Do this **after** the history is in place and the schema has settled.

Traps:
- the bot must be an admin OR have privacy mode off; **after changing privacy
  the bot has to be removed from the group and added again**
- a separate bot from BotFather, do not reuse the book bot's token — one token
  means one webhook, and the old bot will drop off
- answer the webhook with 200 immediately and do the work in the background,
  otherwise Telegram retries and you get duplicates
- `[mounts]` is mandatory, otherwise SQLite dies on the first deploy
- catch both entity types: `url` and `text_link`
- the webhook secret proves telegram sent the update, not which chat it came
  from; check the chat as well, and refuse to start when either is unset —
  missing config must not mean an open door
- whatever the ssh console is documented to run has to be inside the image

→ [research/09-deployment-flyio.md](research/09-deployment-flyio.md)

## Step 8. A month from now

Smart Connections (local embeddings), if full-text search turns out not to be
enough. Not earlier — the data has to pile up first.

---

## Priority order if time is short

1. Step 0 (recon) — mandatory, it decides everything
2. Steps 1 and 5 in their smallest form: pull the messages and drop them into
   `.md` with no enrichment at all. Already better than searching the chat.
3. The rest as the need shows up

The worst case is starting to build the full pipeline without knowing the
volume.
