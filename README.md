# Telegram → Obsidian: a link base out of a group chat

Research from 2026-08-02. The problem: people have been dropping links into a
group chat for years (clothes, gear, cool sites, articles), and all of it sinks
and cannot be found. We need a base with categories and a search that works.

## The whole thing in five lines

1. History and new messages are **two different technologies**. The Bot API
   does not hand over history at all, so a userbot is needed once.
2. Enrichment: **oEmbed → social crawler UA → curl_cffi**. A browser is almost
   never needed.
3. The main landmine: dead short links redirect to the front page instead of
   returning a 404.
4. LLM categorisation costs about $3 for a couple of thousand links. Not the
   place to save money.
5. Obsidian: one note per link, plus Bases and Omnisearch. Do not install
   Dataview.

## Navigation

| File | About |
|---|---|
| [SETUP.md](SETUP.md) | What is running now: the bot, the site, how to use it |
| [CLAUDE.md](CLAUDE.md) | The code as built, and the traps it already hit |
| [PLAN.md](PLAN.md) | Step-by-step rollout plan, where to start |
| [research/01-telegram-extraction.md](research/01-telegram-extraction.md) | Getting the messages out: export, Bot API, Telethon, TDLib |
| [research/02-url-canonicalization.md](research/02-url-canonicalization.md) | URL normalisation, ClearURLs, redirect resolution, dedup |
| [research/03-url-metadata.md](research/03-url-metadata.md) | oEmbed, meta tag parsing, hosted services and prices |
| [research/04-anti-bot.md](research/04-anti-bot.md) | Blocked sites, TLS fingerprinting, proxies, RU marketplaces |
| [research/05-llm-categorization.md](research/05-llm-categorization.md) | Taxonomy, prompting, cost estimate, stitching context together |
| [research/06-obsidian-vault.md](research/06-obsidian-vault.md) | Vault layout, frontmatter, Bases, search, plugins, sync |
| [research/07-ready-made-tools.md](research/07-ready-made-tools.md) | Karakeep, Linkwarden, Raindrop, existing bots and plugins |
| [research/08-archiving.md](research/08-archiving.md) | monolith, SingleFile, ArchiveBox, Wayback SPN |
| [research/09-deployment-flyio.md](research/09-deployment-flyio.md) | A Fly.io app for new links, credentials we already have, the abooks_bot template |

## Two strategies

**Off the shelf (almost no code).** Karakeep + karakeepbot + the Karakeep Sync
plugin. All three are alive and named in the project's own documentation. The
chat history still has to be pulled separately with Telethon.
→ [07-ready-made-tools.md](research/07-ready-made-tools.md)

**Our own (full control).** A Python pipeline: Telethon → canonicalisation →
enrichment → LLM categorisation → `.md` generated into the vault. Then a small
Fly.io app catches new links, with the template copied from `abooks_bot`.
→ [PLAN.md](PLAN.md), [09-deployment-flyio.md](research/09-deployment-flyio.md)

They do not exclude each other: the backfill is the same either way. The second
one is what was actually built — the state of it is in [SETUP.md](SETUP.md).

## What was checked by hand

Some of the conclusions come from live tests on 2026-08-02 rather than from
documentation: Claude API prices, how link shorteners behave (HEAD vs GET), the
table of social crawler UAs per site, monolith timings, the state of the oEmbed
providers. Those spots are marked in the text.

## A note on language

The global CLAUDE.md asks for English under `knowledge/`. This research was
written in Russian first and translated afterwards, so wording here is a step
removed from the original. The folder is called `research/`, not `knowledge/`.
