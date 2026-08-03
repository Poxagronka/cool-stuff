"""Open a container link that is already stored as a link of its own.

`pipeline.widen` swaps a wishlist for its contents at the moment a message
turns into rows, which does nothing for the pages collected before it existed:
they sit in the database as one card named after a person. This walks back over
them — expand the page, store what was inside against the same message, and
process the new clusters as if they had arrived that way.

    python scripts/unpack.py 393
    python scripts/unpack.py 675 --tag wishlist --tag vesna

`--tag` marks everything that came out of one page, which is the only thing the
categoriser cannot know: whose list it was on.
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from tglinks import canon, containers, db, pipeline, vault  # noqa: E402
from tglinks.config import DB_PATH, VAULT_PATH  # noqa: E402


def source_message(conn: sqlite3.Connection, cluster_id: int) -> dict | None:
    """The message the container arrived in, shaped the way store_link wants.

    Not private, whatever the message was. The triage gate stands between a
    link nobody asked for and the vault, and it reads the words around the
    link: a wishlist saved with "притащить из Осло" beside it looks like a
    private errand and every shop on the page is refused. Running this script
    is the owner saying he wants what is on that page, which is the decision
    the gate was there to ask about — so it is not asked twice.
    """
    row = conn.execute(
        "SELECT l.chat_id, l.msg_id, l.first_seen_at"
        " FROM link l WHERE l.cluster_id = ? ORDER BY l.id LIMIT 1",
        (cluster_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "chat_id": row["chat_id"],
        "msg_id": row["msg_id"],
        "sent_at": row["first_seen_at"],
        "private": False,
    }


def add_tags(conn: sqlite3.Connection, root: Path, cluster_id: int, tags: list[str]) -> bool:
    """Put tags on an entry and on the note it wrote, keeping the order stable."""
    row = conn.execute(
        "SELECT tags, note_path FROM entry WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    if not row:
        return False
    have = json.loads(row["tags"]) if row["tags"] else []
    merged = have + [t for t in tags if t not in have]
    if merged == have:
        return False
    conn.execute(
        "UPDATE entry SET tags = ? WHERE cluster_id = ?",
        (json.dumps(merged, ensure_ascii=False), cluster_id),
    )
    if not row["note_path"]:
        return True
    note = root / row["note_path"]
    if not note.exists():
        return True
    # the note is frontmatter then body, and only the tag list changes; the
    # body is handed back byte for byte rather than re-rendered from the row
    text = note.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return True
    front = yaml.safe_load(parts[1]) or {}
    front["tags"] = merged
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
    note.write_text(f"---\n{head}\n---\n{parts[2]}", encoding="utf-8")
    return True


def reopen(conn: sqlite3.Connection, url: str) -> int | None:
    """Put a link this script already stored back in the queue, unguarded."""
    row = conn.execute(
        "SELECT cluster_id FROM link WHERE norm_key = ? AND cluster_id IS NOT NULL LIMIT 1",
        (canon.key(url),),
    ).fetchone()
    if not row:
        return None
    conn.execute("UPDATE link SET private = 0 WHERE cluster_id = ?", (row["cluster_id"],))
    conn.execute("UPDATE entry SET status = 'new' WHERE cluster_id = ?", (row["cluster_id"],))
    return row["cluster_id"]


async def unpack(conn: sqlite3.Connection, root: Path, cluster_id: int) -> list[int]:
    entry = conn.execute(
        "SELECT url FROM entry WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    msg = source_message(conn, cluster_id)
    if not entry or not msg:
        print(f"cluster {cluster_id}: no such link", file=sys.stderr)
        return []

    inside = await containers.expand(entry["url"])
    if not inside:
        print(f"cluster {cluster_id}: {entry['url']} is not a container")
        return []
    print(f"cluster {cluster_id}: {len(inside)} links inside")

    touched: list[int] = []
    for url in inside:
        got = pipeline.store_link(conn, msg, url)
        if got is None:
            # already carried over by an earlier run of this script; reopen it
            # rather than leaving it at whatever the gate decided last time
            got = reopen(conn, url)
        if got is not None and got not in touched:
            touched.append(got)
    # the page itself stops being a card: what it was about is the links now
    pipeline.skipped(conn, cluster_id, entry["url"], "a container, unpacked")
    print(f"cluster {cluster_id}: {len(touched)} clusters to write")
    return touched


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="+", type=int, help="cluster ids to open")
    ap.add_argument("--tag", action="append", default=[],
                    help="tag every link that came out of the page")
    args = ap.parse_args()

    conn = db.connect(DB_PATH)
    root = Path(VAULT_PATH)
    vault.scaffold(root)

    touched: list[int] = []
    for cluster_id in args.clusters:
        touched += await unpack(conn, root, cluster_id)

    gate = asyncio.Semaphore(4)
    written: list[int] = []

    async def one(cluster_id: int) -> None:
        async with gate:
            try:
                path = await pipeline.process_entry(conn, cluster_id, root)
            except Exception as exc:
                print(f"  cluster {cluster_id} failed: {exc}", file=sys.stderr, flush=True)
                return
            written.append(cluster_id)
            print(f"  [{len(written)}/{len(touched)}] {path.name if path else 'skipped'}",
                  flush=True)

    await asyncio.gather(*(one(c) for c in touched))
    conn.commit()

    if args.tag:
        tagged = sum(add_tags(conn, root, c, args.tag) for c in written)
        conn.commit()
        print(f"tagged {tagged} notes with {', '.join(args.tag)}")
    print(f"Done: {len(written)} of {len(touched)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
