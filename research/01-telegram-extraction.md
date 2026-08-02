# Pulling messages and links out of Telegram

Checked 2026-08-02.

## The key fact

Getting the history and collecting new stuff are **two different technologies**.
A bot on the Bot API physically cannot read anything that happened before it was
added to the group. A userbot over MTProto can read everything, but running one
24/7 risks a ban.

Hence the hybrid: a userbot once for the backfill, a bot forever for what comes
next.

## Summary table

| Method | Backfill | Live | Link previews | Risk |
|---|---|---|---|---|
| Telegram Desktop export JSON | yes | no | **no**, URL only | none |
| `tdl` (Go CLI, MTProto) | yes | by cron | partial | userbot |
| **Telethon 1.44 / Kurigram** | **yes** | yes | **yes, full** | account ban |
| Bot API / n8n Telegram Trigger | **impossible** | yes | yes | none |
| TDLib (Pytdbot) | yes | yes | yes | same + complexity |
| Zapier / Make / Readwise / Raindrop | no | yes | — | — |

## 1. Official Telegram Desktop export

Settings → Advanced → Export Telegram data, or right-click a chat →
Export chat history. Schema: [core.telegram.org/import-export](https://core.telegram.org/import-export).

Message fields: `id`, `type` (`message`/`service`), `date`, `date_unixtime`,
`edited`, `from`, `from_id` (format `user123456`), `reply_to_message_id`,
`forwarded_from`, `saved_from`, `via_bot`, `author`.

**The text sits in two parallel fields:**
- `text` — a string, or an array of strings and entity objects (legacy, awkward)
- `text_entities` — a flat array of `{type, text}` covering the whole text

**You need `text_entities` for links**, types `link` (bare URL) and `text_link`
(hidden hyperlink, href in a separate field).

Full list of entity types: `mention`, `hashtag`, `bot_command`, `link`, `email`,
`bold`, `italic`, `code`, `pre`, `plain`, `text_link`, `mention_name`, `phone`,
`cashtag`, `underline`, `strikethrough`, `blockquote`, `bank_card`, `spoiler`,
`custom_emoji`, `unknown`.

### The main downside

**Link previews are not exported at all.** The schema has no webpage object — no
title, no description, no og image. Only the URL in the text. You have to fetch
the metadata yourself.

### Limits

- The default media size threshold is small (~8 MB), the slider goes up to ~4 GB.
  **Files above the threshold are skipped silently** — the JSON has a warning
  string instead of a path.
- No limits on message count or history depth.
- A full export of a large account takes anywhere from minutes to an hour or more.
- Telegram Desktop only, mobile clients don't have the feature.
- The first full-export request may be delayed by a waiting period.

### Incremental — partly

- For **a single chat** you can pick a date range (From/To).
- For a **bulk** "export all data" there is **no** range. Open feature
  request: [tdesktop#30463](https://github.com/telegramdesktop/tdesktop/issues/30463)
  (opened 2026-03-20, PR #30618 still hanging).
- Can't be automated: GUI only, no CLI.

### CLI alternative — `tdl`

[docs.iyear.me/tdl](https://docs.iyear.me/tdl/guide/tools/export-messages/), Go,
MTProto under the hood.

```
tdl chat export -c CHAT -T time -i <unix_from>,<unix_to>
```

Also `-T id` / `-T last`, plus expression-level filters. Works under cron.
Technically this is already a userbot — it needs api_id/api_hash.

## 2. Bot API

[core.telegram.org/bots/api](https://core.telegram.org/bots/api). Current
version as of mid-2026 is **9.4**.

### Can a bot read everything in a group

Yes, under one of two conditions:

1. **Privacy mode turned off** via @BotFather (`/setprivacy` → Disable).
   It's on by default: with it the bot only sees `/cmd` commands, replies to its
   own messages, and service events.
2. **The bot is an admin** — admins always get everything regardless of privacy
   mode.

⚠️ **After changing privacy mode you have to remove the bot from the group and
add it again**, otherwise the setting won't take effect.

It will never get **messages from other bots** (loop protection).

### No history after the fact

A hard limit. The Bot API has no "get chat history" method. Updates are kept on
the server for **no longer than 24 hours** and are deleted as soon as they're
acknowledged (`getUpdates` with an `offset` above their `update_id`).

Everything that happened before the bot was added does not exist for it.

### getUpdates vs webhook

Mutually exclusive: while a webhook is set, `getUpdates` returns an error.

- `getUpdates` — at most 100 updates per call, long polling via `timeout`
- webhook — HTTPS only, ports 443/80/88/8443, max 100 connections
  (`max_connections`), type filter via `allowed_updates`
- **One webhook per bot** — the key pain point for n8n

### Sending limits

Incoming isn't limited. Outgoing: ~30 msg/sec total, ~1 msg/sec to a single
chat, ~20 msg/min into a group.

## 3. Userbot / MTProto

You need **api_id + api_hash** from [my.telegram.org](https://my.telegram.org)
and phone-number auth. The session is saved to a file or a string.

### Library status — a lot moved in 2026

**Telethon (Python)**
- The LonamiWebs/Telethon repo was **archived 2026-02-21**, read-only
- Development moved to **Codeberg: `codeberg.org/Lonami/Telethon`**
- Stable **v1.44.0 from 2026-06-15**, in maintenance mode (bugfixes + layer)
- **v2 is still alpha** (`2.0.0a0`, October 2025), no backwards compatibility
- Take v1

**Pyrogram is dead.** Successor: [Kurigram](https://github.com/KurimuzonAkuma/kurigram)
2.2.24 (2026-07-11), Python ≥3.8, LGPL-3.0, drop-in replacement (`import pyrogram`
works), supports Gifts/Stories/Topics/Business. The other fork,
`pyrotgfork`, is less popular.

**GramJS (Node/TS) — archived 2026-07-14.** The npm package `telegram` is
unmaintained. Successor is **`teleproto`**, a "largely compatible" fork; migration
is a package swap.

**Bottom line:** Python → Telethon v1.44 or Kurigram 2.2.x. Node → teleproto.

### Reading history

```python
client.iter_messages(chat, limit=None, offset_id=..., reverse=True)  # Telethon
client.get_chat_history()                                            # Kurigram
```

They pull **the entire history**, including messages from before you joined (for
public groups), in batches of 100. With `min_id`/`offset_id` incremental runs are
trivial.

**Full link previews live here too:** `MessageMediaWebPage` with `title`,
`description`, `site_name`, `url`, `photo`. That's the main argument for MTProto
if the task is about links.

Plus `search` over a chat with the `InputMessagesFilterUrl` filter — pull **only
the messages with links** without downloading the whole chat.

### Rate limits and bans

- `FloodWaitError` is throttling, not a ban. From seconds to 24+ hours. Telethon
  sleeps on its own if the wait is <60 sec (`flood_sleep_threshold`).
- Telegram doesn't publish exact limits. In practice: **1–2 sec between requests
  runs stably forever**.
- The real risk is **an account ban**. Triggers: a fresh account, joining many
  chats at once, a sudden start at high speed, lots of `ResolveUsername`.
- Mitigation: an account with history, not your main SIM, variable delays, ramp
  up gradually, one session per account.
- Formally, bulk collection goes against the spirit of the ToS.

## 4. TDLib

[core.telegram.org/tdlib](https://core.telegram.org/tdlib). The official C++
library, the one the clients themselves are built on. Local DB, cache, full
MTProto, works both as user and as bot.

Upside: official, reliable, handles updates correctly, local storage. Downside:
heavy, needs compiling, low-level API.

**Python wrappers still alive in 2026:**
- **Pytdbot** — async, released 2026-02-22, recommended in the tdlib README
- **tdjson** (AYMENJD) — low-level binding, April 2026, prebuilts for
  Linux x64/ARM64, Windows x64, macOS M-series. Pytdbot is built on top of it
- **aiotdlib** — also in the recommendations, moves more slowly
- **python-telegram** (alexander-akhmetov) — Python 3.10+, no Windows
- `tdlib-python` (JunaidBabu) — old, don't take it

⚠️ `telegram-bot-api` (a self-hosted Bot API server on TDLib) lifts some Bot API
limits (files up to 2000 MB), **but gives no access to history** — it's still the
same Bot API.

## 5. n8n

### Built-in nodes

**Telegram Trigger** — Bot API webhook only. 23+ update types:
`message`, `channel_post`, `edited_message`, business events, callback/inline
queries, poll, reactions, `chat_member`, chat boosts. By default it's subscribed
to everything except Chat Member, Message Reaction, Message Reaction Count.
There's a Download Images/Files option and filters by chat ID / user ID.

**Telegram node** — sendMessage, getFile, getChat, admin operations. No "get
history" method (it doesn't exist in the Bot API).

### Limitations

1. **Inherits everything from the Bot API** → a retroactive backfill is
   impossible in principle
2. **One webhook per bot** → one Telegram Trigger node. Two workflows on one
   chat means either a second bot or a Switch inside
3. **Test URL overrides Production URL**: while you're testing, production gets
   no events. The most common complaint in the issues
4. **Self-hosted**: `WEBHOOK_URL` (or `N8N_HOST`/`N8N_PROTOCOL`) pointing at a
   public address is mandatory. Behind a reverse proxy you need websocket
   proxying, otherwise the editor hangs on "listening". HTTPS is required
5. `chat_member`, reactions and boosts require bot admin rights

### Community nodes with MTProto

If you need the backfill inside n8n:

- **`n8n-nodes-telegram-grampro`** — MTProto via teleproto. Has **Get Chat
  History**, Read Messages History, time filters, session encryption, built-in
  rate limiting. The most current one
- **`n8n-nodes-telegram-mtproto`** (veezex) — listens for new messages
- **`n8n-nodes-telegram-mtproto-client`** — a client node for a user account
- **Telepilot** — a userbot node on TDLib

All of them require installing community packages on self-hosted and storing the
userbot session string in credentials — effectively full access to the account
sitting in n8n.

## 6. SaaS and bridges

**All of them are built on the Bot API → none can do history.** The model is
"forward a message to the bot → it gets saved".

**Zapier.** New Message trigger. Limits: DMs only, plus groups where the bot was
added with privacy off; **one bot = one Zap**; **doesn't fire on messages from
the bot's owner**; the Chat ID dropdown only shows chats active in the last
24 hours.

**Make.com.** Same thing on top of the Bot API, more flexible transforms, cheaper
per operation.

**Readwise Reader.** No official TG bot (there's a Discord bot, an extension, an
email inbox). A community `@SaveToReadwiseBot` is going around. The clean path is
your own bot + the [Reader API](https://readwise.io/reader_api) (`POST /save`).

**Raindrop.io.** The official path is **through IFTTT**: you message the
`@IFTTT` bot with a `#save` hashtag. No bot of their own. The community
[OlegWock/raindrop-telegram-bot](https://github.com/OlegWock/raindrop-telegram-bot)
died 2024-08-21. There is a decent [REST API](https://developer.raindrop.io/) —
your own bridge is an evening's work.

**Notion.** No official bot. Only homegrown ones on the Notion API, or a chain
through n8n/Make.

## Conclusion for this task

1. **Backfill** — Telethon 1.44 with `InputMessagesFilterUrl`. It gives full
   link previews along the way. 1–2 sec between iterations, not from the main
   account.
   The fast no-code alternative is a Desktop export of the chat to JSON and
   parsing `text_entities` (but then you fetch previews yourself).
2. **Continuous collection** — n8n Telegram Trigger + the bot as admin.

There's no need to keep a userbot running 24/7 — a bot is safer and steadier.
