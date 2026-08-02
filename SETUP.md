# What is set up

Everything runs on its own. No manual steps are left.

## Infrastructure

| What | Where |
|---|---|
| Pipeline repository | `github.com/Poxagronka/tg-links-secondbrain` (private) |
| Vault repository | `github.com/Poxagronka/links-vault` (private) |
| Local vault | `~/links-vault` |
| App on Fly | `tg-links-collector.fly.dev`, region fra |
| Volume | `links_data`, 1 GB, fra |
| Bot | `@coolstuff_links_bot`, privacy mode off, in the group |
| Chat | "cool stuff", id `-4092567497` (a plain group, not a supergroup) |
| Deploy key | on `links-vault` with write access; the private half is in `~/.ssh/tg-links-vault-deploy` and in the Fly secrets |
| Fly secrets | `ANTHROPIC_API_KEY`, `SSH_KEY`, `VAULT_REPO`, `WEBHOOK_SECRET`, `TG_BOT_TOKEN`, `TG_CHAT` |
| Startup | refuses to boot without `WEBHOOK_SECRET` or `TG_CHAT`: an update is only ours if it came from that chat, and only telegram if it carries that header |
| Telethon session | `data/backfill.session`, signed in |

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
flyctl ssh console -a tg-links-collector -C "python /app/scripts/invite.py"
flyctl ssh console -a tg-links-collector -C "python /app/scripts/invite.py --who"
```

Absolute path on purpose: `-C` does not run through a shell.

Search on the site takes plain questions. A question that is not in English
goes through the free MyMemory endpoint first, under a daily character budget,
and only reaches Haiku when that comes back with nothing. Above the results is
the tag web — the tags of whatever is currently on screen, drawn as bubbles on
threads that drift about; clicking one filters by it.

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
flyctl logs -a tg-links-collector          # what is going on
flyctl status -a tg-links-collector        # is the machine asleep
curl https://tg-links-collector.fly.dev/health
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

## About the cost

Not free, contrary to the original idea — Anthropic instead of a local model
was a deliberate choice.

- Fly: `shared-cpu-1x`/512 MB with sleep, plus a 1 GB volume. Pennies a month,
  added to the existing `abooks_bot` bill
- Anthropic: about $0.002 per link. Working through 388 links of history cost
  less than a dollar, and it is cents a month after that
- GitHub, Obsidian: free

If going back to zero ever looks attractive: the Anthropic work is isolated in
`categorize.py`, and swapping in a local model is an edit in one file.
