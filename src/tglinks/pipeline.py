"""Ties the stages together: dedup, enrich, categorise, write a note."""

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import canon, categorize, enrich, vault

CONTEXT_WINDOW = timedelta(minutes=5)
HAS_URL = re.compile(r"(https?://|www\.)\S+", re.I)


def store_message(conn: sqlite3.Connection, msg: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO message"
        "(chat_id, msg_id, sent_at, author, text, reply_to, preview_json)"
        " VALUES(?,?,?,?,?,?,?)",
        (
            msg["chat_id"],
            msg["msg_id"],
            msg["sent_at"],
            msg.get("author"),
            msg.get("text"),
            msg.get("reply_to"),
            json.dumps(msg.get("preview"), ensure_ascii=False) if msg.get("preview") else None,
        ),
    )


def store_link(conn: sqlite3.Connection, msg: dict, raw_url: str) -> int | None:
    """Insert a link and attach it to a cluster. Returns cluster_id if new."""
    norm = canon.key(raw_url)
    row = conn.execute(
        "SELECT cluster_id FROM link WHERE norm_key = ? AND cluster_id IS NOT NULL LIMIT 1",
        (norm,),
    ).fetchone()

    cur = conn.execute(
        "INSERT OR IGNORE INTO link"
        "(raw_url, norm_key, chat_id, msg_id, first_seen_at, cluster_id)"
        " VALUES(?,?,?,?,?,?)",
        (raw_url, norm, msg["chat_id"], msg["msg_id"], msg["sent_at"],
         row["cluster_id"] if row else None),
    )
    if cur.rowcount == 0:
        return None
    link_id = cur.lastrowid

    if row:
        return None

    # first sighting: this link becomes its own cluster and gets a note
    conn.execute("UPDATE link SET cluster_id = ? WHERE id = ?", (link_id, link_id))
    conn.execute(
        "INSERT OR IGNORE INTO entry(cluster_id, url, domain, status, updated_at)"
        " VALUES(?,?,?,?,?)",
        (link_id, canon.normalise(raw_url), canon.domain(raw_url), "new",
         datetime.now().isoformat(timespec="seconds")),
    )
    return link_id


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
        lo = (sent - CONTEXT_WINDOW).isoformat()
        hi = (sent + CONTEXT_WINDOW).isoformat()
        stream = list(conn.execute(
            "SELECT * FROM message WHERE chat_id = ? AND sent_at BETWEEN ? AND ?"
            " ORDER BY sent_at LIMIT 30",
            (chat_id, lo, hi),
        ))
        here = next(
            (i for i, r in enumerate(stream) if r["msg_id"] == anchor["msg_id"]), None
        )
        if here is not None:
            # another link nearby starts its own conversation: everything past
            # it belongs to that link, not to this one. taking the whole window
            # made comments about the neighbour read as comments about this url
            for side in (reversed(stream[:here]), stream[here + 1:]):
                for row in side:
                    if HAS_URL.search(row["text"] or ""):
                        break
                    picked.setdefault(row["msg_id"], row)

    return [dict(r) for r in sorted(picked.values(), key=lambda r: r["sent_at"])]


async def process_entry(conn: sqlite3.Connection, cluster_id: int, vault_root: Path) -> Path | None:
    entry = conn.execute(
        "SELECT * FROM entry WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    if not entry:
        return None

    link = conn.execute(
        "SELECT * FROM link WHERE cluster_id = ? ORDER BY first_seen_at LIMIT 1", (cluster_id,)
    ).fetchone()
    if not link:
        return None

    msg = conn.execute(
        "SELECT * FROM message WHERE chat_id = ? AND msg_id = ?",
        (link["chat_id"], link["msg_id"]),
    ).fetchone()
    preview = json.loads(msg["preview_json"]) if msg and msg["preview_json"] else None

    meta = await enrich.enrich(entry["url"], preview)
    resolved = enrich.final_url(entry["url"], meta)
    dead = not meta.ok() and (meta.http_status >= 400 or meta.http_status == 0)

    # a title and no description says nothing about what the link is. going
    # after the page text costs one extra fetch and turns a generic app-store
    # placeholder into an actual description
    page = (meta.fields or {}).get("page_text", "")
    if not page and not dead and len(meta.description) < 60:
        page = await enrich.body_text(resolved)

    context = context_for(conn, link["chat_id"], link["msg_id"])
    result = await categorize.classify(
        resolved,
        {
            "domain": entry["domain"],
            "title": meta.title,
            "description": meta.description,
            "site_name": meta.site_name,
            "page_text": page,
        },
        context,
    )

    record = {
        "url": resolved,
        "domain": entry["domain"],
        "title": result["title"],
        "description": result["description"],
        "category": result["category"],
        "tags": result["tags"],
        "confidence": result["confidence"],
        "image": meta.image,
        "price": meta.price,
        "shared_by": msg["author"] if msg else "",
        "shared_at": link["first_seen_at"],
        "status": "dead" if dead else "ok",
        "tg_link": vault.tg_link(link["chat_id"], link["msg_id"]),
    }
    path = vault.write(vault_root, record, context)

    conn.execute(
        "UPDATE entry SET url=?, title=?, description=?, image=?, site_name=?, price=?,"
        " category=?, tags=?, confidence=?, status=?, enrich_tier=?, http_status=?,"
        " note_path=?, updated_at=? WHERE cluster_id=?",
        (
            resolved, result["title"], result["description"], meta.image, meta.site_name,
            meta.price, result["category"], json.dumps(result["tags"], ensure_ascii=False),
            result["confidence"], record["status"], meta.tier, meta.http_status,
            str(path.relative_to(vault_root)), datetime.now().isoformat(timespec="seconds"),
            cluster_id,
        ),
    )
    if meta.tier:
        conn.execute(
            "INSERT INTO domain_tier(domain, tier, ok) VALUES(?,?,1)"
            " ON CONFLICT(domain) DO UPDATE SET tier=excluded.tier, ok=domain_tier.ok+1",
            (entry["domain"], meta.tier),
        )
    conn.commit()
    return path
