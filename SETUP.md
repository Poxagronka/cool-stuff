# What is set up

Everything runs on its own. No manual steps are left.

## Infrastructure

| What | Where |
|---|---|
| Pipeline repository | `github.com/Poxagronka/cool-stuff` (private) |
| Vault repository | `github.com/Poxagronka/links-vault` (private) |
| Local vault | `~/links-vault` |
| App on Fly | `cool-stuff.fly.dev`, region fra |
| Volume | `links_data`, 1 GB, fra |
| Bot | `@coolstuff_links_bot`, privacy mode off, in the group |
| Chat | "cool stuff", id `-4092567497` (a plain group, not a supergroup) |
| Deploy key | on `links-vault` with write access; the private half is in `~/.ssh/tg-links-vault-deploy` and in the Fly secrets |
| Fly secrets | `GROQ_API_KEY`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, `ANTHROPIC_API_KEY`, `SSH_KEY`, `VAULT_REPO`, `WEBHOOK_SECRET`, `TG_BOT_TOKEN`, `TG_CHAT` |
| Startup | refuses to boot without `WEBHOOK_SECRET` or `TG_CHAT`: an update is only ours if it came from that chat, and only telegram if it carries that header |
| Telethon session | `data/backfill.session` on the laptop, `/data/backfill.session` on the volume — the same file, copied up |
| Saved Messages | pulled on the server every `SAVED_EVERY_MINUTES` (3 h), plus `POST /api/saved/pull` |

## What was checked live

A link was sent to the group and went the whole way: the webhook took the
update, metadata was pulled off the page, Anthropic returned a category and
tags, the note was committed into `links-vault`, the bot left a reaction. The
logs and the note are both there.

## How to use it

Drop a link into the chat and the rest happens by itself. The bot reacts:
"eyes" means the link was already there, "writing hand" means a note was
created.

The site is called "cool stuff" and lives at the same address as the webhook.
It is invite-only: an invite is a link with a code in it, and opening it is the
signup — pick a name and a password, and that pair is how you come back
afterwards. There is no permanent personal link any more; anything that is not
`/signin` or a live invite shows the sign-in form. Sign-in takes eight attempts
a minute per address, and changing your password on the profile page signs
every other device out. Anyone already inside can mint invites from that same
page, five unused at a time.

The first invite on a fresh machine comes from the command line:

```
flyctl ssh console -a cool-stuff -C "python /app/scripts/invite.py"
flyctl ssh console -a cool-stuff -C "python /app/scripts/invite.py --who"
```

Absolute path on purpose: `-C` does not run through a shell.

Search on the site takes plain questions. A question that is not in English
goes through the free MyMemory endpoint first, under a daily character budget,
and only reaches Haiku when that comes back with nothing.

Above the results is the tag web: the fourteen biggest tags of whatever is
currently on screen, drawn as bubbles on threads. It settles and then holds
still. Clicking one filters by it, which narrows the results, which redraws the
web from what that tag keeps company with — so the next fourteen bubbles are
its neighbours rather than the whole vault again. The button on the right puts
everything back. Tags naming where a link lives — instagram, youtube, tiktok
and the rest — never become bubbles; they stay on the note as context.

A card shows the summary. The small chip with the domain and an arrow is the
only thing that leaves for the site; clicking anywhere else on the card opens
the note itself — the front matter as a table, the description and every chat
quote, the way it looks in Obsidian. Escape closes it.

Everything written into the vault — titles, descriptions, keywords — is
English. The chat quotes stay in whatever language they were said in.

Locally: `cd ~/links-vault && git pull`. In Obsidian, install the Obsidian Git
plugin so it pulls by itself. Open the vault with "Open folder as vault" →
`~/links-vault` and enable the core Bases plugin — the views from `bases/` will
start working.

Inside Obsidian the tags come out in its own built-in tag panel: the `tags`
property in the frontmatter is recognised as real tags. The web on the site is
a separate thing built from the same property.

## Maintenance

```
flyctl logs -a cool-stuff          # what is going on
flyctl status -a cool-stuff        # is the machine asleep
curl https://cool-stuff.fly.dev/health
```

The machine runs with `auto_stop_machines = "suspend"`: it sleeps between
messages and wakes on a webhook in a fraction of a second.

If the bot goes quiet, start here:

```
source .env
curl "https://api.telegram.org/bot$TG_BOT_TOKEN/getWebhookInfo"
```

Look at `last_error_message`.

## Pulling the history again

Already done once. If it is ever needed again:

```
.venv/bin/python scripts/backfill.py --recon     # count
.venv/bin/python scripts/backfill.py --dump      # into sqlite
.venv/bin/python scripts/backfill.py --saved     # the same for Saved Messages
.venv/bin/python scripts/backfill.py --process   # enrich and write the notes
```

Run it from the laptop, not from the server: a home IP is residential, and
shops hand it metadata they will not hand a datacentre.

Saved Messages are marked private on the way in, and the mark comes from the
peer telegram resolved rather than from what was typed on the command line —
`me`, your own @username and your numeric id all count. A private link only
reaches the vault if the triage gate lets it, and what you wrote next to it is
dropped from the note the moment the same link turns out to have been posted in
the group too.

## Saved Messages on the server

Anything you save to yourself in Telegram becomes a note by itself, the same
way a link dropped in the group does. It takes a detour, though: the Bot API
cannot see Saved Messages at all, so this half runs on your own account over
MTProto and needs the Telethon session file to be sitting on the volume.

### Getting the session up there

Signing in cannot happen on the server — Telegram sends a code and something
has to type it into a terminal, and `flyctl ssh console` is not where you want
to be doing that. So it is created on the laptop once and copied up.

```
.venv/bin/python scripts/login.py --phone +7...
.venv/bin/python scripts/login.py --code 12345      # the code arrives in Telegram
```

That writes `data/backfill.session`. Put it on the volume under the name the
app expects, and restart so the app picks it up:

```
flyctl ssh sftp shell -a cool-stuff
put data/backfill.session /data/backfill.session
exit
flyctl machine restart -a cool-stuff
```

Check it took:

```
flyctl ssh console -a cool-stuff -C "ls -l /data/backfill.session"
flyctl logs -a cool-stuff | grep "saved messages"
```

A session is one login, and Telegram will not let two clients share one: run
`scripts/backfill.py` on the laptop while the server holds the same session and
one of them gets thrown off. Copy the file up when you are done with it, not
while you are still using it.

### When it says the session is gone

The app never shrugs this off. A missing file, an unfinished login, or a
session you killed from Telegram's own "Devices" screen all produce the same
thing in the log, and `POST /api/saved/pull` answers 503 with the same text:

```
no telegram session at /data/backfill.session
the telegram session at /data/backfill.session is not authorised any more
```

Both mean the same repair: sign in again on the laptop, copy the file up. The
reason for the noise is that the quiet version of this failure is
indistinguishable from a healthy run — a client with no login connects fine and
reads an empty history, forever.

### What drives the schedule

Nothing inside the app sits on a timer. The machine suspends when nothing is
talking to it and carries no health checks precisely so that it can, and a
suspended process has no clock: a three-hour sleep would either never fire, or
have to keep the machine awake to fire, which is the thing we were avoiding.

So the pull hangs off the wakes that happen anyway. On boot and after every
update from the chat, the app asks whether `SAVED_EVERY_MINUTES` have passed
since the last attempt, and pulls if they have. On a busy day that is enough on
its own. For a guaranteed clock, something outside has to do the waking — a
scheduled machine that pokes `/health` and goes away again:

```
flyctl machine run curlimages/curl:latest -a cool-stuff \
  --schedule hourly --restart no \
  -- -fsS https://cool-stuff.fly.dev/health
```

`/health` is on the open list, so the poke needs no credentials; the app's own
watermark and interval decide whether anything actually happens. The trigger
route is the other way in and is not open — it wants a session cookie like
everything else on the site:

```
curl -X POST -b cookies.txt https://cool-stuff.fly.dev/api/saved/pull
```

Two runs never overlap. A trigger that arrives while a pull is in flight
answers `{"ran": false, "why": "already running"}` and does nothing: the run
already going walks forward to the newest message there is, so there would be
nothing left for a second one. A watermark in the `state` table
(`saved_msg_id`) remembers how far the last run got, message by message, so a
machine suspended mid-pull resumes there instead of rereading the history.

Everything that comes in this way is marked private and faces the triage gate
before a note is written, exactly like the laptop backfill.

## About the cost

Close to free. Every model call goes through a chain that tries the free
providers first — Groq, Gemini, Cerebras — and only reaches Anthropic when they
are out of quota, down, or answer with something that is not a well-formed tool
call. Regenerating all 388 notes ran on the free half of the chain.

- Fly: `shared-cpu-1x`/512 MB with sleep, plus a 1 GB volume. Pennies a month,
  added to the existing `abooks_bot` bill
- Groq, Gemini, Cerebras: free daily allowances, no card
- Anthropic: the fallback, about $0.002 per link when it is used at all
- Translation: MyMemory, free, under a daily character budget; Haiku only when
  it comes back with nothing
- GitHub, Obsidian: free

Falling through to a paid provider is deliberate rather than stingy. A provider
that answers with nonsense is treated as unavailable, because a bad note stays
in the vault and one paid request does not.
