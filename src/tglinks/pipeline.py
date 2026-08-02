"""Ties the stages together: dedup, enrich, categorise, write a note."""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import canon, categorize, enrich, llm, triage, vault

log = logging.getLogger("tglinks")

CONTEXT_WINDOW = timedelta(minutes=5)
# how far the walk goes on either side of a link before it gives up on its own
NEIGHBOURS = 15
HAS_URL = re.compile(r"(https?://|www\.)\S+", re.I)

# the gate on privately saved links. a free provider does the reading and
# anthropic catches whatever it cannot, because no verdict means no note
TRIAGE_CHAIN = os.getenv(
    "TRIAGE_CHAIN",
    "groq/llama-3.3-70b-versatile,gemini/gemini-3.5-flash-lite,"
    "anthropic/claude-haiku-4-5-20251001",
)


def store_message(conn: sqlite3.Connection, msg: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO message"
        "(chat_id, msg_id, sent_at, author, text, reply_to, preview_json, private)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (
            msg["chat_id"],
            msg["msg_id"],
            msg["sent_at"],
            msg.get("author"),
            msg.get("text"),
            msg.get("reply_to"),
            json.dumps(msg.get("preview"), ensure_ascii=False) if msg.get("preview") else None,
            1 if msg.get("private") else 0,
        ),
    )


def store_link(conn: sqlite3.Connection, msg: dict, raw_url: str) -> int | None:
    """Insert a link and attach it to a cluster.

    Returns the cluster that now needs a note written, or None when nothing
    changed. A link that is already known is not ignored: someone bringing the
    same thing up again usually says something new about it, and that belongs
    on the existing note rather than in a second one.
    """
    norm = canon.key(raw_url)
    row = conn.execute(
        "SELECT cluster_id FROM link WHERE norm_key = ? AND cluster_id IS NOT NULL LIMIT 1",
        (norm,),
    ).fetchone()

    cur = conn.execute(
        "INSERT OR IGNORE INTO link"
        "(raw_url, norm_key, chat_id, msg_id, first_seen_at, cluster_id, private)"
        " VALUES(?,?,?,?,?,?,?)",
        (raw_url, norm, msg["chat_id"], msg["msg_id"], msg["sent_at"],
         row["cluster_id"] if row else None, 1 if msg.get("private") else 0),
    )
    if cur.rowcount == 0:
        return None   # this exact url in this exact message, seen before
    link_id = cur.lastrowid

    if row:
        # a second sighting of a known thing: the note is rewritten so the new
        # remarks join the old ones instead of starting a duplicate. a refusal
        # by the gate normally stands, but the gate only ever guarded what
        # nobody else had seen — once the group posts the same link there is
        # nothing left to guard, so a public sighting reopens it
        if msg.get("private"):
            conn.execute(
                "UPDATE entry SET status = 'new' WHERE cluster_id = ? AND status <> 'skipped'",
                (row["cluster_id"],),
            )
        else:
            conn.execute(
                "UPDATE entry SET status = 'new' WHERE cluster_id = ?", (row["cluster_id"],)
            )
        return row["cluster_id"]

    # first sighting: this link becomes its own cluster and gets a note
    conn.execute("UPDATE link SET cluster_id = ? WHERE id = ?", (link_id, link_id))
    conn.execute(
        "INSERT OR IGNORE INTO entry(cluster_id, url, domain, status, updated_at)"
        " VALUES(?,?,?,?,?)",
        (link_id, canon.normalise(raw_url), canon.domain(raw_url), "new",
         datetime.now().isoformat(timespec="seconds")),
    )
    return link_id


def _neighbours(
    conn: sqlite3.Connection, anchor: sqlite3.Row, sent: datetime, back: bool
) -> list[sqlite3.Row]:
    """The messages beside the anchor on one side, nearest first.

    Walking outward from the anchor rather than taking the whole window in one
    query, because the window is capped and the cap has to fall on the far end
    of the conversation, not on the anchor itself.
    """
    edge = (sent - CONTEXT_WINDOW if back else sent + CONTEXT_WINDOW).isoformat()
    # two messages can share a second, so the id breaks the tie
    if back:
        sql = (
            "SELECT * FROM message WHERE chat_id = ? AND sent_at >= ?"
            " AND (sent_at < ? OR (sent_at = ? AND msg_id < ?))"
            " ORDER BY sent_at DESC, msg_id DESC LIMIT ?"
        )
    else:
        sql = (
            "SELECT * FROM message WHERE chat_id = ? AND sent_at <= ?"
            " AND (sent_at > ? OR (sent_at = ? AND msg_id > ?))"
            " ORDER BY sent_at, msg_id LIMIT ?"
        )
    return list(conn.execute(sql, (
        anchor["chat_id"], edge, anchor["sent_at"], anchor["sent_at"],
        anchor["msg_id"], NEIGHBOURS,
    )))


def _carry_links(conn: sqlite3.Connection, chat_id: int, msg_ids: list[int]) -> set[int]:
    """Which of these messages are on record as having posted a link."""
    if not msg_ids:
        return set()
    marks = ",".join("?" * len(msg_ids))
    rows = conn.execute(
        f"SELECT DISTINCT msg_id FROM link WHERE chat_id = ? AND msg_id IN ({marks})",
        (chat_id, *msg_ids),
    )
    return {r["msg_id"] for r in rows}


def context_for(conn: sqlite3.Connection, chat_id: int, msg_id: int) -> list[dict]:
    """The message itself, its reply chain, and neighbours within five minutes."""
    anchor = conn.execute(
        "SELECT * FROM message WHERE chat_id = ? AND msg_id = ?", (chat_id, msg_id)
    ).fetchone()
    if not anchor:
        return []

    picked: dict[int, sqlite3.Row] = {anchor["msg_id"]: anchor}

    parent_id = anchor["reply_to"]
    for _ in range(5):
        if not parent_id:
            break
        parent = conn.execute(
            "SELECT * FROM message WHERE chat_id = ? AND msg_id = ?", (chat_id, parent_id)
        ).fetchone()
        if not parent:
            break
        picked[parent["msg_id"]] = parent
        parent_id = parent["reply_to"]

    try:
        sent = datetime.fromisoformat(anchor["sent_at"])
    except ValueError:
        sent = None
    if sent:
        sides = [
            _neighbours(conn, anchor, sent, back=True),
            _neighbours(conn, anchor, sent, back=False),
        ]
        carriers = _carry_links(
            conn, chat_id, [row["msg_id"] for side in sides for row in side]
        )
        # another link nearby starts its own conversation: everything past it
        # belongs to that link, not to this one. taking the whole window made
        # comments about the neighbour read as comments about this url.
        # what counts as a link is what the link table remembers, because
        # telegram hides urls behind display text and a message reading "this
        # jacket" is no less of a link than one spelling the address out
        for side in sides:
            for row in side:
                if row["msg_id"] in carriers or HAS_URL.search(row["text"] or ""):
                    break
                picked.setdefault(row["msg_id"], row)

    return [dict(r) for r in sorted(picked.values(), key=lambda r: r["sent_at"])]


def context_for_cluster(conn: sqlite3.Connection, cluster_id: int) -> list[dict]:
    """Everything said around every mention of this link, oldest first.

    One thing can be posted in the group and later saved again privately, or
    brought up twice months apart. All of it is the same note, so all of it is
    the context that note is written from.
    """
    picked: dict[tuple[int, int], dict] = {}
    rows = conn.execute(
        "SELECT chat_id, msg_id FROM link WHERE cluster_id = ? ORDER BY first_seen_at",
        (cluster_id,),
    ).fetchall()
    for row in rows:
        for msg in context_for(conn, row["chat_id"], row["msg_id"]):
            picked[(msg["chat_id"], msg["msg_id"])] = msg
    return sorted(picked.values(), key=lambda m: m["sent_at"])


def private_only(conn: sqlite3.Connection, cluster_id: int) -> bool:
    """True when nobody but the owner has ever seen this link."""
    row = conn.execute(
        "SELECT MIN(private) AS all_private FROM link WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    return bool(row and row["all_private"])


def anchor(conn: sqlite3.Connection, cluster_id: int):
    """The entry, its oldest link, and the message that link arrived in."""
    entry = conn.execute(
        "SELECT * FROM entry WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    link = conn.execute(
        "SELECT * FROM link WHERE cluster_id = ? ORDER BY first_seen_at LIMIT 1", (cluster_id,)
    ).fetchone()
    msg = None
    if link:
        msg = conn.execute(
            "SELECT * FROM message WHERE chat_id = ? AND msg_id = ?",
            (link["chat_id"], link["msg_id"]),
        ).fetchone()
    return entry, link, msg


def fold_resolved(
    conn: sqlite3.Connection, cluster_id: int, resolved: str, vault_root: Path
) -> int:
    """Put every cluster that turned out to point at the same page into one.

    A shortener and the shop url behind it look like two different links until
    somebody follows them, and two clusters with the same title will happily
    write the same filename — the second one wins and the first entry is left
    pointing at a note about something else. The oldest cluster keeps the id,
    because that is the one the vault and the index already know about.
    """
    rkey = canon.key(resolved)
    conn.execute(
        "UPDATE link SET resolved_url = ?, resolved_key = ? WHERE cluster_id = ?",
        (resolved, rkey, cluster_id),
    )
    others = [
        r["cluster_id"]
        for r in conn.execute(
            "SELECT DISTINCT cluster_id FROM link"
            " WHERE resolved_key = ? AND cluster_id IS NOT NULL AND cluster_id <> ?",
            (rkey, cluster_id),
        )
    ]
    if not others:
        return cluster_id

    keep = min([cluster_id, *others])
    for gone in sorted(c for c in [cluster_id, *others] if c != keep):
        row = conn.execute(
            "SELECT url, note_path FROM entry WHERE cluster_id = ?", (gone,)
        ).fetchone()
        conn.execute("UPDATE link SET cluster_id = ? WHERE cluster_id = ?", (keep, gone))
        conn.execute("DELETE FROM entry WHERE cluster_id = ?", (gone,))
        if row and row["note_path"] and not vault.retire(vault_root, row["note_path"], row["url"]):
            log.info("merged cluster %s, left its note alone: %s", gone, row["note_path"])
    conn.commit()
    log.info("clusters %s resolve to %s, folded into %s", [cluster_id, *others], resolved, keep)
    return keep


def skipped(conn: sqlite3.Connection, cluster_id: int, url: str, why: str) -> None:
    conn.execute(
        "UPDATE entry SET status = 'skipped', updated_at = ? WHERE cluster_id = ?",
        (datetime.now().isoformat(timespec="seconds"), cluster_id),
    )
    conn.commit()
    log.info("kept out of the vault: %s (%s)", url, why)


async def process_entry(conn: sqlite3.Connection, cluster_id: int, vault_root: Path) -> Path | None:
    entry, link, msg = anchor(conn, cluster_id)
    if not entry or not link:
        return None

    # the cheap half of the gate is a string check, and it settles the matter
    # for a bank login or an adult host. asking it first means the one kind of
    # link that must never be published is not even fetched
    if private_only(conn, cluster_id) and triage.obviously_private(entry["url"]):
        return skipped(conn, cluster_id, entry["url"], "private by host")

    preview = json.loads(msg["preview_json"]) if msg and msg["preview_json"] else None

    meta = await enrich.enrich(entry["url"], preview)
    resolved = enrich.final_url(entry["url"], meta)
    dead = not meta.ok() and (meta.http_status >= 400 or meta.http_status == 0)

    merged = fold_resolved(conn, cluster_id, resolved, vault_root)
    if merged != cluster_id:
        cluster_id = merged
        entry, link, msg = anchor(conn, cluster_id)
        if not entry or not link:
            return None
    # the shortener's own host is not what the note is about, and it is what
    # the index would otherwise show as the domain of the link
    domain = canon.domain(resolved)

    # a title and no description says nothing about what the link is. going
    # after the page text costs one extra fetch and turns a generic app-store
    # placeholder into an actual description
    page = (meta.fields or {}).get("page_text", "")
    if not page and not dead and len(meta.description) < 60:
        page = await enrich.body_text(resolved)

    context = context_for_cluster(conn, cluster_id)
    saved = private_only(conn, cluster_id)
    if not saved:
        # the group has seen the link, but not what the owner wrote beside it
        # in his own saved messages. that half of the context never faced the
        # gate, so it is not published and it is not shown to a model either
        context = [m for m in context if not m["private"]]
    if saved:
        note = " ".join((m.get("text") or "") for m in context)
        allowed, why = await triage.keep(resolved, {
            "domain": domain, "title": meta.title,
            "description": meta.description, "page_text": page,
        }, note, llm.chain(TRIAGE_CHAIN))
        if not allowed:
            return skipped(conn, cluster_id, resolved, why)

    result = await categorize.classify(
        resolved,
        {
            "domain": domain,
            "title": meta.title,
            "description": meta.description,
            "site_name": meta.site_name,
            "page_text": page,
        },
        context,
    )

    record = {
        "url": resolved,
        "domain": domain,
        "title": result["title"],
        "description": result["description"],
        "category": result["category"],
        "tags": result["tags"],
        "keywords": result["keywords"],
        "confidence": result["confidence"],
        "image": meta.image,
        "price": meta.price,
        "shared_by": msg["author"] if msg else "",
        "shared_at": link["first_seen_at"],
        "status": "dead" if dead else "ok",
        "source": "saved" if saved else "chat",
        "tg_link": vault.tg_link(link["chat_id"], link["msg_id"]),
    }
    path = vault.write(vault_root, record, context)
    here = str(path.relative_to(vault_root))

    conn.execute(
        "UPDATE entry SET url=?, domain=?, title=?, description=?, image=?, site_name=?, price=?,"
        " category=?, tags=?, confidence=?, status=?, enrich_tier=?, http_status=?,"
        " note_path=?, updated_at=? WHERE cluster_id=?",
        (
            resolved, domain, result["title"], result["description"], meta.image, meta.site_name,
            meta.price, result["category"], json.dumps(result["tags"], ensure_ascii=False),
            result["confidence"], record["status"], meta.tier, meta.http_status,
            here, datetime.now().isoformat(timespec="seconds"),
            cluster_id,
        ),
    )
    if meta.tier:
        conn.execute(
            "INSERT INTO domain_tier(domain, tier, ok) VALUES(?,?,1)"
            " ON CONFLICT(domain) DO UPDATE SET tier=excluded.tier, ok=domain_tier.ok+1",
            (domain, meta.tier),
        )
    conn.commit()

    # the note is named after the title, so a better title moves the file. the
    # replacement is on disk by now, and what is left at the old name is a
    # note nobody links to that search still answers with
    if entry["note_path"] and entry["note_path"] != here:
        if not vault.retire(vault_root, entry["note_path"], entry["url"]):
            log.info("old note is not provably ours, left alone: %s", entry["note_path"])
    return path
