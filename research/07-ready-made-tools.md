# Off-the-shelf solutions: what you don't have to write

Before building a pipeline, check whether the whole problem is already solved.

## Karakeep — the closest hit

Formerly Hoarder. A self-hosted bookmark manager: it saves the link, pulls the
metadata itself, makes a full copy of the page itself, tags with an LLM itself
(supports the Anthropic API), full-text search through Meilisearch, OCR on
images.

Which means steps 3, 4 and half of 5 from the plan are already written and
working.

Three components that together nearly cover the task:

- **Karakeep** — the storage plus AI tagging
- **karakeepbot** — a Telegram bot; you drop a link in the chat and it goes to
  Karakeep
- **Karakeep Sync** (an Obsidian plugin) — pulls bookmarks into the vault as `.md`

**What it does NOT solve: backfilling the history.** No off-the-shelf tool can
"read a year and a half of chat and sort it out". You'll have to write the
Telethon script from step 1 either way — but after that you can pour everything
into Karakeep through its API instead of building your own pipeline.

Deployment is docker compose, with Meilisearch alongside. It installs on Fly.io,
but at that point it isn't a "small app" anymore: several containers plus a
volume.

**When to take it:** if there are a lot of links and what you want is a bookmark
manager with a UI, with Obsidian as a secondary view.
**When not to:** if Obsidian is the only interface and you don't want a second
system to maintain.

## Linkwarden

Same class, a Karakeep competitor. Stronger on archiving (PDF, screenshot,
readable, Wayback all at once), weaker on AI tagging. There's a managed cloud.
No Telegram out of the box.

## Raindrop.io

SaaS, a generous free tier, a great UI and mobile apps, auto-tagging and
full-text search (on the paid plan). The API is decent.

The upside is zero maintenance. The downsides: the data isn't yours, getting it
into Obsidian needs a separate script, and there's no Telegram integration.

A reasonable option if the whole point is "so it's searchable" and Obsidian isn't
essential.

## Readwise / Reader

Built around reading articles and highlights; the official Obsidian integration
(the Readwise Official plugin) is best in class. But it's $8–10/mo, and
categorizing clothes and gadgets isn't its job. For a chat full of product links
it's off target.

## What's dead

- **obsidian-telegram-sync** — a plugin that synced Telegram messages into a
  vault. The repo hasn't been updated, it only worked with direct messages to the
  bot and it didn't read history. Don't count on it
- Assorted "Telegram to Notion/Obsidian" chains on Zapier/Make — they run into
  the same Bot API limit: no history, only new messages

## Bottom line

| Solution | History backfill | Categorization | Obsidian | Maintenance |
|---|---|---|---|---|
| Karakeep + karakeepbot + Sync | no (needs your own script) | yes, LLM | plugin | docker compose |
| Linkwarden | no | weak | no | docker compose |
| Raindrop | no | yes, paid | your own script | none |
| Your own pipeline | yes | yes, however you like | native | all on you |

**Recommendation.** Do the recon (step 0) either way. Then it forks:

- Unique links **< 500** → your own script, one evening, no Karakeep
- **500–3000** and Obsidian is all you need → your own pipeline, it pays off
- **> 3000**, or you want a UI and a mobile app → Karakeep, and load the history
  in through its API with the Telethon script
