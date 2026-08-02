# Continuous collection: a small app on Fly.io

Instead of n8n. One Python service, one container, one volume.

## What you already have

`/Users/poxagronka/abooks_bot` holds **a working Telegram bot on Fly.io in
webhook mode** — a ready template you can copy wholesale.

### Telegram credentials — already there, nothing to register

`abooks_bot/.env` (the file is in `.gitignore`, the values below are masked):

```
TG_API_ID=322694••••••      <- MTProto, THIS IS WHAT the Telethon backfill needs
TG_API_HASH=07ef4d••••••    <- MTProto, THIS IS WHAT the Telethon backfill needs
TG_BOT_TOKEN=866944••••••   <- the @shoggoth-book-bot bot
TG_BOT_USERNAME=shoggo••••••
```

`api_id` / `api_hash` are issued per **account**, not per application — you can
reuse them for a second project with no limits. The "register on my.telegram.org"
step drops out of the plan.

Reusing `TG_BOT_TOKEN` is **a bad idea**: one bot = one webhook URL. Point the
same token at a new server and the books bot goes down. Create a separate bot in
BotFather (30 seconds) and put its token into Fly secrets.

### fly.toml as a template

From `abooks_bot/fly.toml`, the relevant part:

```toml
app = "shoggoth-book-bot"
primary_region = "fra"

[env]
  BOT_MODE = "webhook"
  BOT_PORT = "8443"
  WEBHOOK_URL = "https://shoggoth-book-bot.fly.dev"

[http_service]
  internal_port = 8443
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 0

[mounts]
  source = "abooks_data"
  destination = "/data"

[[vm]]
  size = "performance-8x"
  memory = "16384"
```

`performance-8x` / 16 GB is for transcoding audiobooks. A link collector needs
two orders of magnitude less.

## fly.toml for the link collector

```toml
app = "cool-stuff"
primary_region = "fra"

[build]
  dockerfile = "Dockerfile"

[env]
  BOT_MODE = "webhook"
  BOT_PORT = "8443"
  WEBHOOK_URL = "https://cool-stuff.fly.dev"
  DB_PATH = "/data/links.db"

[http_service]
  internal_port = 8443
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

[mounts]
  source = "links_data"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512"
```

Secrets (not committed to the repo):

```bash
fly secrets set TG_BOT_TOKEN=... ANTHROPIC_API_KEY=... GITHUB_TOKEN=...
```

### On scale and money

`shared-cpu-1x` / 256 MB fits into Fly's free resources. 512 MB is taken with
headroom: `curl_cffi` and `trafilatura` on a heavy page eat noticeably more than
an echo bot, and chasing an OOM kill at 256 MB is unpleasant.

`auto_stop_machines = "suspend"` + `min_machines_running = 0` — the machine
sleeps between messages and wakes on an incoming webhook. For a chat where a link
gets posted a few times a day, real consumption is close to zero.

An important difference from `abooks_bot`: there `auto_stop_machines = false`,
because that bot stops itself through the Machines API after a long job. Here the
jobs are short — let Fly manage it.

A cold start from suspend takes a fraction of a second, Telegram makes its
timeout. From a fully stopped state it's a few seconds, which is also fine:
Telegram retries the webhook.

**The volume is mandatory.** A Fly machine's filesystem is ephemeral; without
`[mounts]` the SQLite with the link history disappears on the first deploy.
Volumes are pinned to one region and one machine — exactly what a single-user bot
needs, but you can't scale horizontally with one.

## What the service does

```
POST /webhook from Telegram
  -> pull URLs out of text_entities (type: url and text_link)
     plus message.link_preview_options.url
  -> canonicalization (see 02)
  -> dedup on three keys in SQLite on the volume
  -> if new: the enrichment ladder (see 03, 04)
  -> Claude, structured output (see 05)
  -> write the .md into the vault (see below)
  -> a reaction on the chat message as confirmation
```

Answer the webhook **with a 200 immediately** and do the work in the background
(`asyncio.create_task` / `BackgroundTasks`). Telegram waits only a few seconds
and retries on timeout — otherwise slow enrichment gives you duplicates.

An emoji reaction on the original message instead of a reply: the confirmation is
visible and the chat stays clean.

## How notes get into Obsidian

Three options, in increasing order of hassle:

**1. Git (recommended).** The vault is a private GitHub repo. The service clones
it onto the volume at startup, commits the new note and pushes. Locally Obsidian
Git pulls it in.

Pros: version history, works on any device, nothing exposed to the outside.
Cons: conflicts if you edit the vault from both sides at once (in a single-user
scenario this basically never happens).

The token is a fine-grained PAT scoped to one repo, in `fly secrets`.

**2. Obsidian Local REST API.** The plugin runs an HTTP server inside Obsidian.
The service on Fly calls it and creates the note.

The problem is obvious: your laptop has to be reachable from the internet and
switched on. Tailscale or a Cloudflare Tunnel solves it, but that's one more
moving part that will fall over.

**3. An intermediate queue.** The service only writes to SQLite on the volume and
serves `GET /pending`; a local script picks them up on a schedule and lays them
out in the vault.

The most reliable, and it needs no inbound access, but it adds a manual step.

For one person **option 1** is the right compromise. Option 3 makes sense if the
vault lives in iCloud/Obsidian Sync and git won't work there.

## Setting the bot up in the group

- The bot has to be a group **admin**, or have **privacy mode off**
  (BotFather → `/setprivacy` → Disable). Otherwise it only sees commands
  addressed to it personally, and not a single link
- **After changing privacy mode you have to remove the bot from the group and add
  it again** — the setting applies at the moment of adding. This is the trap that
  costs people an hour
- One bot = one webhook URL. `setWebhook` overwrites the previous one silently
- Links arrive in `message.entities` (`type: "url"` — bare text) and
  `type: "text_link"` (a hyperlink, the URL in the `url` field). Forget the
  second one and you lose every link hidden under text
- The preview Telegram pulled itself sits in `link_preview_options` — free
  metadata, usable as tier zero of enrichment

## Deploy

```bash
fly launch --no-deploy          # generates fly.toml, fix it by hand
fly volumes create links_data --region fra --size 1
fly secrets set TG_BOT_TOKEN=... ANTHROPIC_API_KEY=... GITHUB_TOKEN=...
fly deploy
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://cool-stuff.fly.dev/webhook"
```

Check that the webhook took:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

The `last_error_message` field is the first place to look when the bot goes
quiet.

## What this service does NOT do

Backfill the history. The Bot API has no method for reading past messages — not
now and not in prospect (updates are kept 24 hours, after that the data doesn't
exist for the bot).

The history is dumped once, locally, through Telethon from your user account
(step 1 of the plan), and the result is loaded into the same SQLite. There's no
need to run a Telethon userbot on the server permanently, and it's risky for the
account.
