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
pushes to it but never pulls. Anything regenerated on the laptop reaches the
portal only through the `git pull` at startup — it is there in `ensure_clone`,
but after a push to the vault the machine has to be restarted, otherwise the
index stays stale.

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
