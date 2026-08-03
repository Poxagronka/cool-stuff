#!/usr/bin/env python3
"""Step 0 and step 1: read the chat history once, via a user account.

    python scripts/backfill.py --recon          just count, change nothing
    python scripts/backfill.py --dump           store links and the talk around them
    python scripts/backfill.py --saved          the same for Saved Messages
    python scripts/backfill.py --process        enrich, categorise, write notes

Bot api cannot read history at all, so this runs on your own account through
mtproto. Run it from a laptop on a residential ip: the same fetch that returns
nothing from a datacentre often returns full metadata from home.
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telethon import TelegramClient  # noqa: E402
from telethon.tl.types import InputMessagesFilterUrl  # noqa: E402

from tglinks import canon, db, pipeline, saved, vault  # noqa: E402
from tglinks.config import (  # noqa: E402
    DB_PATH,
    TG_API_HASH,
    TG_API_ID,
    TG_CHAT,
    TG_SESSION,
    VAULT_PATH,
)

# the same file the server uses, named by TG_SESSION so a laptop run and the
# scheduled pull cannot end up on two different logins. telethon wants the
# path without the suffix it appends itself
SESSION = str(TG_SESSION.with_suffix(""))

# reading links out of a telethon message is the same job here and in the
# scheduled pull, and it was worth exactly one copy
_parent = saved.parent_of
_urls_of = saved.urls_of


async def iter_links(client, chat, limit: int | None):
    """Yield (message, [urls]) for every message that carries a link."""
    async for msg in client.iter_messages(chat, filter=InputMessagesFilterUrl, limit=limit):
        found = _urls_of(msg)
        if found:
            yield msg, found


async def iter_in_scope(client, chat, limit: int | None):
    """Yield (message, [urls]) for everything a note could ever quote.

    Telegram can hand back only the messages with a url in them, and that used
    to be all the dump kept. But the sentence explaining a link usually holds
    no link itself — "runs two sizes small" is the whole point of the note and
    would never be stored. So the history is walked in full and a message is
    kept when it carries a link, sits within the context window of one, or is
    somewhere up the reply chain of a message already kept. The rest is talk no
    note will ever look at.

    Telegram walks the history newest first, which is why a message that might
    still turn out to be a neighbour waits in `pending`: the link that would
    claim it is older, so it has not been seen yet.
    """
    pending: list = []
    wanted: set[int] = set()
    floor = None      # everything down to here is inside some link's window

    def keep(msg, found):
        # a reply is context wherever it sits, and its parent is always older,
        # so it is still ahead of us in the walk
        parent = _parent(msg)
        if parent:
            wanted.add(parent)
        return msg, found

    async for msg in client.iter_messages(chat, limit=limit):
        # a waiting message that even this one is too far below can no longer
        # be reached by any link, older being all that is left to come
        pending = [p for p in pending if msg.date >= p.date - pipeline.CONTEXT_WINDOW]
        found = _urls_of(msg)
        if found:
            yield keep(msg, found)
            for waiting in pending:
                yield keep(waiting, [])
            pending = []
            floor = msg.date - pipeline.CONTEXT_WINDOW
        elif msg.id in wanted or (floor is not None and msg.date >= floor):
            yield keep(msg, [])
        else:
            pending.append(msg)


async def author_of(client, msg, cache: dict) -> str:
    uid = getattr(msg.from_id, "user_id", None) if msg.from_id else None
    if uid is None:
        return ""
    if uid not in cache:
        try:
            user = await client.get_entity(uid)
            cache[uid] = (user.first_name or user.username or str(uid)).strip()
        except Exception:
            cache[uid] = str(uid)
    return cache[uid]


async def list_chats(client, limit: int | None = None, needle: str = "") -> None:
    """Print group dialogs with their ids, so the chat can be picked by name.

    Default is every dialog: a small private group can sit far down the list,
    below hundreds of channels, and a capped listing quietly hides it.
    """
    print(f"{'id':>16}  {'kind':<8}  name")
    print("-" * 70)
    async for dialog in client.iter_dialogs(limit=limit):
        if not (dialog.is_group or dialog.is_channel):
            continue
        if needle and needle.lower() not in (dialog.name or "").lower():
            continue
        kind = "group" if dialog.is_group else "channel"
        print(f"{dialog.id:>16}  {kind:<8}  {dialog.name}")
    print("\nCopy the id you need into .env as TG_CHAT=...")


async def recon(client, chat, limit):
    total, keys, domains, raw = 0, set(), Counter(), 0
    async for msg, found in iter_links(client, chat, limit):
        total += 1
        for url in found:
            raw += 1
            keys.add(canon.key(url))
            domains[canon.domain(url)] += 1
        if total % 200 == 0:
            print(f"  ...{total} messages, {len(keys)} unique", file=sys.stderr)

    print(f"\nMessages with links   : {total}")
    print(f"Links in total        : {raw}")
    print(f"Unique after canon    : {len(keys)}")
    print(f"Domains               : {len(domains)}\n")
    print("Top 25 domains:")
    for host, count in domains.most_common(25):
        print(f"  {count:5d}  {host}")

    unique = len(keys)
    print("\nVerdict:")
    if unique < 500:
        print("  <500 — no pipeline needed, one --dump --process run is enough.")
    elif unique < 3000:
        print("  500-3000 — an own pipeline pays off, carry on with the plan.")
    else:
        print("  >3000 — worth a look at Karakeep, see research/07.")


async def is_self(client, chat) -> bool:
    """Whether this peer is the owner talking to himself.

    Saved Messages is reachable as "me", as your own @username and as your
    numeric id, and links from there are notes to self: they face the triage
    gate before a note is written. Which command line flag was typed says
    nothing about that, so ask telegram who the peer actually resolved to.
    """
    try:
        entity = await client.get_entity(chat)
    except Exception:
        # an unresolvable peer is about to fail anyway, and the safe reading
        # of "no idea whose chat this is" is that it might be the owner's
        return True
    me = await client.get_me()
    return getattr(entity, "id", None) == getattr(me, "id", None)


async def dump(client, chat, limit, conn):
    """Store the links, and every message around them that a note might quote.

    A run over Saved Messages is marked private: those links go through the
    triage gate before a note is written, and their text is only quoted in a
    note the gate let through. A link saved privately that the group also
    posted stops being private, so the flag lives on the link row.
    """
    private = await is_self(client, chat)
    if private:
        print("this chat is your own Saved Messages: links from it are triaged")
    cache: dict[int, str] = {}
    stored = talk = new = 0
    async for msg, found in iter_in_scope(client, chat, limit):
        record = {
            "chat_id": msg.chat_id,
            "msg_id": msg.id,
            "sent_at": msg.date.isoformat(timespec="seconds"),
            "author": await author_of(client, msg, cache),
            "text": msg.message or "",
            "reply_to": _parent(msg),
            "preview": None,
            "private": private,
        }
        pipeline.store_message(conn, record)
        stored += 1
        if not found:
            talk += 1
        for url in await pipeline.widen(list(found)):
            if pipeline.store_link(conn, record, url):
                new += 1
        if stored % 100 == 0:
            conn.commit()
            print(f"  ...{stored} messages, {new} new links", file=sys.stderr)
        if found:
            # the same pacing as before the dump started keeping plain talk:
            # one breath per link, not per message, or a long history crawls
            await asyncio.sleep(0.05)
    conn.commit()
    print(f"Stored messages: {stored} ({talk} of them context), new unique links: {new}")


async def process(conn, vault_root, limit):
    vault.scaffold(vault_root)
    rows = conn.execute(
        "SELECT cluster_id FROM entry WHERE status = 'new' ORDER BY cluster_id LIMIT ?",
        (limit or 1_000_000,),
    ).fetchall()
    print(f"To process: {len(rows)}", flush=True)

    # most of the wall clock is network wait, so run a few at a time. sqlite
    # writes stay safe: asyncio is single threaded and each entry commits once
    gate = asyncio.Semaphore(4)
    done = 0

    async def one(i: int, cluster_id: int) -> None:
        nonlocal done
        async with gate:
            try:
                path = await pipeline.process_entry(conn, cluster_id, vault_root)
            except Exception as exc:
                print(f"  [{i}] failed on cluster {cluster_id}: {exc}", file=sys.stderr,
                      flush=True)
                return
            done += 1
            if path:
                print(f"  [{done}/{len(rows)}] {path.name}", flush=True)

    await asyncio.gather(*(one(i, r["cluster_id"]) for i, r in enumerate(rows, 1)))
    print(f"Done: {done} of {len(rows)}.", flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-chats", action="store_true", help="list chats with their ids")
    ap.add_argument("--recon", action="store_true", help="only count")
    ap.add_argument("--dump", action="store_true", help="dump into sqlite")
    ap.add_argument("--saved", action="store_true",
                    help="dump your own Saved Messages, triaged for privacy")
    ap.add_argument("--process", action="store_true", help="enrich and write notes")
    ap.add_argument("--chat", default=TG_CHAT)
    # a dump reads the whole history now, so this counts messages, not links
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--find", default="", help="filter by name for --list-chats")
    args = ap.parse_args()

    if not (args.list_chats or args.recon or args.dump or args.saved or args.process):
        ap.error("need at least one of --list-chats / --recon / --dump / --saved / --process")

    conn = db.connect(DB_PATH)
    vault_root = Path(VAULT_PATH)

    if args.list_chats or args.recon or args.dump or args.saved:
        if not TG_API_ID or not TG_API_HASH:
            print("TG_API_ID / TG_API_HASH are not set, see .env.example", file=sys.stderr)
            return 1
        if not (args.list_chats or args.saved) and not args.chat:
            print("no chat given: --chat or TG_CHAT in .env", file=sys.stderr)
            return 1
        Path(SESSION).parent.mkdir(parents=True, exist_ok=True)
        client = TelegramClient(SESSION, TG_API_ID, TG_API_HASH)
        await client.connect()
        # a session file appears on the first attempt even if the login never
        # finished, so ask telegram itself instead of trusting the file
        if not await client.is_user_authorized():
            await client.disconnect()
            print(
                "Telegram login is not finished.\n"
                "  python scripts/login.py --phone +7...\n"
                "  python scripts/login.py --code <code from Telegram>",
                file=sys.stderr,
            )
            return 1
        try:
            if args.list_chats:
                await list_chats(client, needle=args.find)
            if args.recon or args.dump:
                chat = int(args.chat) if args.chat.lstrip("-").isdigit() else args.chat
                if args.recon:
                    await recon(client, chat, args.limit)
                if args.dump:
                    await dump(client, chat, args.limit, conn)
            if args.saved:
                # "me" is the saved messages chat: your own notes to yourself
                await dump(client, "me", args.limit, conn)
        finally:
            await client.disconnect()

    if args.process:
        await process(conn, vault_root, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
