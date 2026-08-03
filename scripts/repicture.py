"""Find a picture for the notes that were written before the picker existed.

Every entry the ladder finished without an image is opened again — the whole
document this time, not just the head — and whatever `pictures` can pick out of
it goes on the entry and into the note. Nothing else about the note changes.

    python scripts/repicture.py --dry
    python scripts/repicture.py
    python scripts/repicture.py --only shop.com --only outlier.nyc

Run it from the laptop rather than the machine: a shop gives a datacentre ip
less, which is scraping R4 and the reason the backfill lives here at all. What
it finds is then carried over as a list of url/image pairs, so the server never
has to fetch anything.
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from tglinks import db, enrich, pictures  # noqa: E402
from tglinks.config import DB_PATH, VAULT_PATH  # noqa: E402

# no fetch will ever get a picture out of these, and the site draws a tile for
# them instead. asking anyway costs a timeout each
HOPELESS = ("instagram.com", "pinterest.com", "t.me", "x.com", "twitter.com")

AT_ONCE = 6


def wanting(conn: sqlite3.Connection, only: list[str]) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT cluster_id, url, title, note_path FROM entry"
        " WHERE status = 'ok' AND (image IS NULL OR image = '')"
        " ORDER BY cluster_id"
    ).fetchall()
    keep = []
    for row in rows:
        host = (urlsplit(row["url"]).hostname or "").removeprefix("www.")
        if any(host == h or host.endswith("." + h) for h in HOPELESS):
            continue
        if only and not any(o in host for o in only):
            continue
        keep.append(row)
    return keep


def put_in_note(root: Path, note_path: str, image: str) -> bool:
    """Add the picture to a note already on disk, changing nothing else.

    Re-rendering from the row would be simpler and would also quietly rewrite
    every other field from whatever the database says today. The note is the
    thing people read, so it is patched rather than replaced: one line in the
    front matter, one line at the top of the body.
    """
    if not note_path:
        return False
    note = root / note_path
    if not note.exists():
        return False
    text = note.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return False
    front = yaml.safe_load(parts[1]) or {}
    if front.get("image"):
        return False
    front["image"] = image
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
    note.write_text(f"---\n{head}\n---\n\n![]({image})\n{parts[2]}", encoding="utf-8")
    return True


async def look(row: sqlite3.Row) -> tuple[int, str, str]:
    """The best picture this page will give up, or an empty string."""
    try:
        raw = await asyncio.wait_for(enrich.full_page(row["url"]), 45)
    except Exception:
        raw = ""
    found = pictures.pick(raw, row["url"]) if raw else ""
    if not found:
        found = await pictures.from_search(row["url"], row["title"] or "")
    return row["cluster_id"], row["url"], found


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="say what it found, write nothing")
    ap.add_argument("--only", action="append", default=[], help="limit to these hosts")
    ap.add_argument("--out", help="write the url/image pairs here as json")
    ap.add_argument("--apply", help="take the pairs out of this json instead of fetching")
    args = ap.parse_args()

    conn = db.connect(DB_PATH)
    root = Path(VAULT_PATH)

    if args.apply:
        found = json.loads(Path(args.apply).read_text())
    else:
        rows = wanting(conn, args.only)
        print(f"{len(rows)} entries with no picture")
        gate = asyncio.Semaphore(AT_ONCE)

        async def one(row):
            async with gate:
                got = await look(row)
                print(f"  {'found' if got[2] else '  -  '}  {got[1][:70]}", flush=True)
                return got

        got = await asyncio.gather(*(one(r) for r in rows))
        found = {url: image for _, url, image in got if image}

    print(f"{len(found)} pictures")
    if args.out:
        Path(args.out).write_text(json.dumps(found, indent=1, ensure_ascii=False))
    if args.dry:
        return 0

    noted = 0
    for url, image in found.items():
        row = conn.execute(
            "SELECT cluster_id, note_path FROM entry WHERE url = ?", (url,)
        ).fetchone()
        if not row:
            continue
        conn.execute(
            "UPDATE entry SET image = ? WHERE cluster_id = ?", (image, row["cluster_id"])
        )
        noted += put_in_note(root, row["note_path"], image)
    conn.commit()
    print(f"wrote {len(found)} rows, {noted} notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
