# Deployment — rules

**R1.** The root filesystem of a Fly machine is ephemeral. Anything that has to
survive a restart (sqlite, ssh key, vault clone) must live on a `[mounts]` volume.

**R2.** Grant write access to someone else's repo with a deploy key, not a
personal token: the key is scoped to one repository, the token to the whole
account.

**R3.** The webhook answers 200 right away and does the work in the background.
Telegram treats a slow reply as a delivery failure and retries the update.

**R4.** Secrets set via `flyctl secrets set` trigger a machine redeploy. Set them
all in one command, not one at a time.

**R5.** `[[http_service.checks]]` and sleeping are incompatible: the proxy hits
`/health` once a minute, the machine is never idle and `auto_stop_machines` never
fires. If the app should sleep until the first request, there must be no checks.

**R6.** Public search answers from memory: vault notes are read into an index at
startup and re-read after a new note is written. The machine uses the same disk
as the collector, so there is no second source of truth.

**R7.** The vault clone on the machine is one-way by default: the collector
pushes to it but never pulls. Anything regenerated on the laptop used to reach
the portal only through the `git pull` in `ensure_clone` at startup, so a push
to the vault meant restarting the machine or serving the old notes. It does not
any more: `Index.stale()` compares the shape of the tree — how many notes there
are and when the newest one was written — against what was read, at most twice
a minute, and reloads when the two differ. A restart is no longer part of
publishing.

**R8.** The image carries `src/` and `scripts/`. Anything documented as
"`flyctl ssh console -C ...`" has to be in it — for a while the invite script
was not, and the documented command answered "can't open file". Run those with
an absolute path (`python /app/scripts/invite.py`): `-C` does not go through a
shell and the working directory is not worth betting on.

**R9.** The app refuses to start without `WEBHOOK_SECRET` and `TG_CHAT`. On fly
that turns a forgotten secret into a machine that will not boot, which is loud
and immediate. The alternative — booting with an unauthenticated webhook that
accepts any chat — fails silently and writes into the vault repo.

**R10.** Fly has no rename. `flyctl apps move` changes the organisation, not
the name, so renaming an app means creating a new one, creating its volume,
copying every secret, deploying, moving the data over and destroying the old
one. Two things bite on the way:

- `set -a && . ./.env` looks like it copies the secrets and does not. A key
  the file declares empty (`TG_BOT_TOKEN=`) and a key the file never mentions
  at all (`SSH_KEY`, which is read from `~/.ssh/`) both arrive as the empty
  string, and `flyctl secrets list` shows them with the same digest — which
  is the tell. Compare digests against the old app before trusting the copy.
- A secret that only exists on the machine can still be recovered from it:
  `flyctl ssh console -a old -C "printenv TG_BOT_TOKEN"`. Fly injects secrets
  as environment variables, so the running machine is the backup.

Nothing follows the app automatically. The Telegram webhook still points at
the old hostname until `setWebhook` is called again, and until it is, links
posted to the chat are collected by an app that is about to be destroyed.

**R11.** The volume is the database, and uploading a new one over it wipes
whatever the app wrote there — accounts included. The vault notes live in git
and come back with a clone; the `account`, `session` and `invite` tables do
not exist anywhere else. Pull the old file down first
(`flyctl ssh sftp get /data/links.db`, plus `-wal`, then checkpoint locally),
copy those three tables into the file that is going up, and only then push it.

**R12.** There is no timer in the app, and there cannot be one. `suspend` plus
no health checks (R5) means the process is frozen between requests, so a
`sleep(3h)` either never fires or has to hold the machine awake to fire —
which is what R5 exists to prevent. Anything periodic hangs off the wakes that
happen anyway: on boot and after every webhook update, the app asks a
timestamp in the `state` table whether the job is due. The clock, when a quiet
day needs one, lives on the Fly side — a scheduled machine that pokes
`/health` and exits. `/health` is on the open list, so the poke carries no
credentials; the app decides for itself whether anything happens.

The corollary is that a long job can be suspended halfway through. It is not a
crash to be prevented, it is normal operation, and the job has to be written to
resume — see telegram R13.

**R13.** Carrying the laptop's vault onto the volume is not a copy, it is a
merge between two filesystems that disagree, and both disagreements produce
duplicate notes on the site.

A `tar czf` on a mac packs an AppleDouble `._name.md` beside every file that
carries an extended attribute, and `com.apple.provenance` puts one on
everything downloaded or written by a sandboxed process. Linux has no idea what
those are and `ls` will not show them, so the count looks right while `find`
sees twice as many. `COPYFILE_DISABLE=1 tar czf ...`, or delete `._*` after
unpacking.

The second is R12 in the scraping rules seen from the other side: a title that
only changed case never renamed its file on the mac, so the laptop's vault
still carries the old spelling. Unpacked onto a case-sensitive volume that old
spelling becomes a second note, indistinguishable on the site from the first.
`entry.note_path` settles it — it records the file the cluster owns, and every
other note claiming the same url is a leftover. 21 of them came over in the
saved-messages import (2026-08-03).

**R14.** `suspend` is worth what it costs. Measured 2026-08-03 on the live
machine: resuming from suspend and answering takes **0.65 s**, a cold boot from
`stopped` takes **9.1 s**. Switching to `stop` would save the storage of the
memory snapshot and buy nine seconds of staring at a blank page on the first
visit after a quiet hour, so it stays on `suspend`. The idle wait before the
proxy suspends is not tunable from `fly.toml`, so "sleep sooner" is not a lever
either.

**R15.** The memory to buy is measured, not guessed. Everything on the machine
together is ~100 MB resident, and the heavy end — the backfill — runs from the
laptop and never lands here (R4 in scraping). On 256 MB that leaves ~90 MB
genuinely free, and parsing a deliberately fat 1.6 MB shop page costs ~20 MB
on top of that. So 256 MB, not 512: the ceiling is paid for twice, once while
awake and once in the suspend snapshot. Fly takes memory in multiples of 256,
so there is no middle setting — if an OOM ever shows up in the logs the only
step up is back to 512.
