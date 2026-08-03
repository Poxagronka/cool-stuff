"""The owner's Saved Messages, pulled on the server instead of by hand.

Everything else in this project arrives through the bot, and the bot cannot see
Saved Messages at all — the Bot API has no history and no access to a private
chat with yourself (telegram R1). So this half runs on the owner's own account
through mtproto, with a telethon session file that a human signed in once from
a laptop. Nothing here can sign in: telegram wants a code typed into a terminal,
and there is no terminal on a fly machine. A missing or revoked session is
therefore not a state to recover from, it is a state to shout about — the
alternative is a pull that reads zero messages every three hours and looks
perfectly healthy while the vault quietly stops growing.

Two things make a repeat run safe. A watermark in the `state` table remembers
the newest message already taken in, so a run reads forward from there rather
than walking the history again; it moves message by message, committed with the
rows it stands for, so a machine suspended mid-run resumes where it stopped
instead of losing or redoing the lot. And a single lock makes a second trigger
a no-op rather than a queue — two pulls over one sqlite connection would
interleave their commits, and the second one has nothing to add anyway.

What comes out of here still faces the triage gate. Nothing in this module
decides whether a saved link deserves a note; it stores messages and hands the
clusters to `pipeline.process_entry`, which is where the gate lives.
"""

import asyncio
import contextlib
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, pipeline, urls
from .config import SAVED_EVERY_MINUTES, TG_API_HASH, TG_API_ID, TG_SESSION

log = logging.getLogger("tglinks")

# saved messages answers to "me": whichever account the session belongs to
PEER = "me"

# the newest saved message already taken in, and when a run last finished or
# gave up. the watermark tracks progress, the timestamp throttles attempts
MARK = "saved_msg_id"
RAN = "saved_ran_at"


class SessionTrouble(RuntimeError):
    """The mtproto session cannot be used, and nobody here can fix it."""


class SessionMissing(SessionTrouble):
    pass


class SessionRevoked(SessionTrouble):
    pass


ADVICE = (
    "Sign in on a laptop and copy the file onto the volume — SETUP.md, "
    '"Saved Messages on the server".'
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@contextlib.asynccontextmanager
async def session():
    """A connected, authorised telethon client, or a loud failure.

    The file appearing on disk proves nothing (telegram R7): telethon writes it
    on the first login attempt, finished or not, and a session can also be
    killed later from any other device. Both cases look identical from here —
    a client that connects and reads an empty history — so telegram is asked
    outright before a single message is fetched.
    """
    if not TG_API_ID or not TG_API_HASH:
        raise SessionMissing("TG_API_ID / TG_API_HASH are not set, see .env.example")
    if not TG_SESSION.exists():
        raise SessionMissing(f"no telegram session at {TG_SESSION}. {ADVICE}")

    from telethon import TelegramClient

    client = TelegramClient(str(TG_SESSION.with_suffix("")), TG_API_ID, TG_API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SessionRevoked(
                f"the telegram session at {TG_SESSION} is not authorised any more. {ADVICE}"
            )
        yield client
    finally:
        await client.disconnect()


def entities_of(msg) -> list[dict]:
    """Telethon entities in the shape `urls.from_entities` reads."""
    out = []
    for ent in msg.entities or []:
        name = type(ent).__name__
        if name == "MessageEntityTextUrl":
            out.append({"type": "text_link", "url": ent.url})
        elif name == "MessageEntityUrl":
            out.append({"type": "url", "offset": ent.offset, "length": ent.length})
    return out


def parent_of(msg) -> int | None:
    reply = getattr(msg, "reply_to", None)
    return getattr(reply, "reply_to_msg_id", None) if reply else None


def urls_of(msg) -> list[str]:
    """Every link in a telethon message, the preview counting as one."""
    found = urls.from_entities(msg.message or "", entities_of(msg))
    if not found and getattr(msg, "web_preview", None):
        preview_url = getattr(msg.web_preview, "url", None)
        if preview_url:
            found = [preview_url]
    return found


def watermark(conn: sqlite3.Connection) -> int:
    """The newest saved message already taken in.

    An empty state key does not mean an empty history. The first import ran
    from a laptop through `scripts/backfill.py --saved` and its rows are
    already in this database, so starting from zero would drag years of saved
    messages back through the gate on the very first scheduled run. The floor
    is what the database already holds.
    """
    mark = db.get_state(conn, MARK, "")
    if mark:
        return int(mark)
    row = conn.execute("SELECT MAX(msg_id) AS top FROM message WHERE private = 1").fetchone()
    return int(row["top"] or 0)


def due(conn: sqlite3.Connection, now: datetime | None = None) -> bool:
    """Has enough time passed since the last attempt to try again?

    Attempts rather than successes: a session nobody has fixed yet would
    otherwise be retried on every wake, and the complaint about it belongs in
    the log a few times a day, not a few times a minute.
    """
    if SAVED_EVERY_MINUTES <= 0:
        return False
    last = db.get_state(conn, RAN, "")
    if not last:
        return True
    try:
        when = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (now or _now()) - when >= timedelta(minutes=SAVED_EVERY_MINUTES)


def waiting(conn: sqlite3.Connection) -> list[int]:
    """Clusters nobody but the owner has seen that still have no note.

    Fresh from this run, and anything a previous run stored before it was
    interrupted: the watermark has already moved past those messages, so this
    query is the only thing that will ever come back for them.
    """
    rows = conn.execute(
        "SELECT cluster_id FROM entry WHERE status = 'new' AND cluster_id IN"
        " (SELECT cluster_id FROM link WHERE cluster_id IS NOT NULL"
        "  GROUP BY cluster_id HAVING MIN(private) = 1)"
        " ORDER BY cluster_id"
    ).fetchall()
    return [r["cluster_id"] for r in rows]


async def collect(client, conn: sqlite3.Connection, since: int, writes) -> int:
    """Store every saved message newer than the watermark, oldest first.

    Oldest first on purpose: the watermark is written after each message, and
    it can only mean "everything up to here is in" if the walk never skips
    forward. Messages with neither a link nor any text are still counted and
    still move the mark — a photo with no caption is nothing a note could ever
    quote, and leaving the mark behind it would make every run reread it.

    Everything with text is kept, link or not, exactly as the webhook does for
    the group: the sentence explaining a link rarely holds one, and a message
    that was never stored cannot be read back as context (telegram R8).
    """
    me = await client.get_me()
    author = (getattr(me, "first_name", "") or getattr(me, "username", "") or "").strip()
    seen = 0
    async for msg in client.iter_messages(PEER, min_id=since, reverse=True):
        found = urls_of(msg)
        record = {
            "chat_id": msg.chat_id,
            "msg_id": msg.id,
            "sent_at": msg.date.isoformat(timespec="seconds"),
            "author": author,
            "text": msg.message or "",
            "reply_to": parent_of(msg),
            "preview": None,
            # saved by the owner where nobody else can see it, so the triage
            # gate stands between every one of these links and the vault
            "private": True,
        }
        async with writes:
            if found or record["text"]:
                pipeline.store_message(conn, record)
                for url in found:
                    pipeline.store_link(conn, record, url)
            # commits the rows above along with the mark that stands for them
            db.set_state(conn, MARK, str(msg.id))
        seen += 1
    return seen


async def write_notes(
    conn: sqlite3.Connection, vault_root: Path, clusters: list[int], writes
) -> list[Path]:
    """Run each cluster through the pipeline, one at a time.

    One at a time and holding the write lock, which is the same granularity the
    webhook uses: the app has a single sqlite connection, and a commit from
    either side would otherwise land in the middle of the other's transaction.
    A cluster that throws is logged and left at `new`, so the next run picks it
    up again rather than losing it.
    """
    written: list[Path] = []
    for cluster_id in clusters:
        async with writes:
            try:
                path = await pipeline.process_entry(conn, cluster_id, vault_root)
            except Exception:
                log.exception("saved: cluster %s failed, left for the next run", cluster_id)
                continue
        if path:
            written.append(path)
    return written


_running = asyncio.Lock()
_writes = asyncio.Lock()


async def pull(
    conn: sqlite3.Connection,
    vault_root: Path,
    *,
    opening=session,
    writes: asyncio.Lock | None = None,
) -> dict:
    """One pass over the saved messages nobody has read yet.

    A pull already in flight makes this a no-op. Not a queue: the run in flight
    walks forward to the newest message there is, so by the time it finishes
    there is nothing left for the trigger that arrived while it worked, and two
    of them sharing one sqlite connection would tangle their commits. Asking
    the lock whether it is held and then taking it is safe here because an
    uncontended `asyncio.Lock` is handed over without yielding, so no other
    task can slip in between the two lines.
    """
    if _running.locked():
        log.info("saved: a pull is already in flight, this trigger does nothing")
        return {"ran": False, "why": "already running", "seen": 0, "notes": []}

    async with _running:
        gate = _writes if writes is None else writes
        since = watermark(conn)
        try:
            async with opening() as client:
                seen = await collect(client, conn, since, gate)
        finally:
            # written even when the pull blew up: this timestamp paces the
            # attempts, and a broken session must not be retried every wake
            db.set_state(conn, RAN, _now().isoformat(timespec="seconds"))
        notes = await write_notes(conn, vault_root, waiting(conn), gate)
        return {"ran": True, "why": "", "seen": seen, "from": since,
                "mark": watermark(conn), "notes": notes}
