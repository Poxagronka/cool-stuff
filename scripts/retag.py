"""Bring the notes written under the old six-tag cap up to ten tags.

Six tags on a vault this size left most tags sitting on one link each, which
is a shelf nobody can stand on: the tag web draws the fourteen biggest and the
rest never appear. This asks the model for ten tags per note out of what the
note already holds — title, description, keywords, the tags it has — and
fetches nothing.

    python scripts/retag.py --dry
    python scripts/retag.py
    python scripts/retag.py --only stegi --limit 5

The tags a note already carries are kept unless they are unusable on their own
(a place glued to the kind, or the same thing said twice), so a re-run is cheap
and lands in the same place. Notes already at ten are skipped; `--all` asks
about them anyway.

It drives off the notes rather than the database, because keywords only ever
existed in the front matter, and it writes the database row too when the url
is in it. On the machine that is one source for both:

    flyctl ssh console -a cool-stuff -C "python /app/scripts/retag.py"
"""

import argparse
import asyncio
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from tglinks import categorize, db, llm  # noqa: E402
from tglinks.config import DB_PATH, VAULT_PATH  # noqa: E402

AT_ONCE = 5

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

SYSTEM = f"""You put shelf tags on a link that is already sorted and described.

Answer with exactly {categorize.TAGS} tags, lowercase kebab-case, no hashes,
ENGLISH only even when the note is in Russian.

A tag is a shelf other links will stand on too, not a description of this one.
- The FIRST is the plain broad word for what this is: `music`, `radio`,
  `clothing`, `coffee`. Then the narrower ones.
- Never glue a place or a brand onto the kind. `athens-radio` is one link for
  ever; write `radio` and `athens` and both gather.
- Never say the same thing twice in different words. With `radio` on the note,
  `online-radio` adds nothing.
- Real narrow tags are wanted: `experimental-music`, `ambient`, `gore-tex`,
  `filter-coffee` say something `radio` does not.
- Kind, genre, material, use, audience, city, era — {categorize.TAGS} different
  angles on the thing, not {categorize.TAGS} spellings of one.
- Singular, always: `piano-tutorial`, never `piano-tutorials`. A plural is a
  second shelf holding the same thing.
- A list of the tags the collection already uses comes with the note. Every one
  of those that fits belongs in your answer: a tag spelled the way the rest of
  the vault spells it gathers, a synonym of it does not.

The tags the note already has come first in your answer, in the order they are
given, and you drop one only if it breaks a rule above. Everything else you
add. Do not invent facts the note does not support: a jacket of unknown
material gets no `gore-tex`."""

TOOL = llm.Tool(
    name="retag",
    description="Shelf tags for a link",
    schema={
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": categorize.TAGS,
            },
        },
        "required": ["tags"],
    },
)


def front_of(text: str) -> dict:
    m = FRONT.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def listed(value: object) -> list[str]:
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def wanting(root: Path, only: list[str], every: bool) -> list[tuple[Path, dict]]:
    out = []
    for path in sorted((root / "links").rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            # the vault moves while it is being walked (portal R19)
            continue
        front = front_of(text)
        if not front.get("url"):
            continue
        if only and not any(o.lower() in str(path).lower() for o in only):
            continue
        if not every and len(listed(front.get("tags"))) >= categorize.TAGS:
            continue
        out.append((path, front))
    return out


def vocabulary(notes: list[tuple[Path, dict]], root: Path, wide: int = 140) -> list[str]:
    """The tags the collection already uses, the most-used first.

    Handed to the model with every note. Without it each note is tagged in
    isolation and the vault ends up with `web-app`, `browser-based` and
    `online-software` on three neighbouring links — three shelves of one link
    where one shelf of three was the point.
    """
    count: dict[str, int] = {}
    seen = {path for path, _ in notes}
    fronts = [front for _, front in notes]
    for path in sorted((root / "links").rglob("*.md")):
        if path in seen:
            continue
        try:
            fronts.append(front_of(path.read_text(encoding="utf-8")))
        except OSError:
            continue
    for front in fronts:
        for tag in listed(front.get("tags")):
            count[tag] = count.get(tag, 0) + 1
    ranked = sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))
    return [tag for tag, _ in ranked[:wide]]


def question(front: dict, known: list[str]) -> str:
    """What the note knows, as data — nothing in it is an instruction."""
    lines = [
        f"URL: {front.get('url', '')}",
        f"Domain: {front.get('domain', '')}",
        f"Title: {front.get('title', '') or '(none)'}",
        f"Category: {front.get('category', '') or 'misc'}",
        f"Description: {front.get('description', '') or '(none)'}",
        f"Search words: {', '.join(listed(front.get('keywords'))) or '(none)'}",
        f"Tags it has now: {', '.join(listed(front.get('tags'))) or '(none)'}",
        "",
        "Tags the collection already uses, most-used first:",
        ", ".join(known) or "(none)",
    ]
    return "\n".join(lines)


def cleaned(tags: list[str], had: list[str]) -> list[str]:
    """Ten tags at most, the ones it already had kept in front, no repeats.

    A plural counts as a repeat: `piano-tutorial` and `piano-tutorials` are two
    shelves holding the same thing, and the model writes both when the note
    gives it the chance.
    """
    seen, out = set(), []
    for tag in [*had, *tags]:
        slug = tag.lstrip("#").strip().lower().replace(" ", "-")
        # only the trailing s, and only where a word is left: `css` and `bass`
        # are not plurals of anything
        stem = slug[:-1] if len(slug) > 4 and slug.endswith("s") else slug
        if not slug or slug in seen or stem in seen:
            continue
        seen.add(slug)
        seen.add(stem)
        out.append(slug)
    return out[: categorize.TAGS]


async def ask(front: dict, known: list[str]) -> list[str]:
    data, _ = await llm.call(
        llm.chain(categorize.CHAIN), SYSTEM, question(front, known), TOOL,
        max_tokens=400, timeout=90, retries=2,
    )
    answered = listed(data.get("tags"))
    # a tag the model dropped it was told to keep is a rule call, so the kept
    # ones are whatever came back that the note already had, in its order
    had = [t for t in listed(front.get("tags")) if t in answered]
    return cleaned(answered, had)


def put_in_note(path: Path, text: str, tags: list[str]) -> bool:
    """Rewrite the tags line and nothing else.

    Re-rendering the note from the database row would also quietly replace
    every other field with whatever the row says today, and the row has no
    keywords at all.
    """
    m = FRONT.match(text)
    if not m:
        return False
    front = front_of(text)
    if not front:
        return False
    front["tags"] = tags
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
    path.write_text(f"---\n{head}\n---\n{text[m.end():]}", encoding="utf-8")
    return True


def put_in_db(conn: sqlite3.Connection, url: str, tags: list[str]) -> bool:
    row = conn.execute("SELECT cluster_id FROM entry WHERE url = ?", (url,)).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE entry SET tags = ? WHERE cluster_id = ?",
        (json.dumps(tags, ensure_ascii=False), row["cluster_id"]),
    )
    return True


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="say what it would write")
    ap.add_argument("--all", action="store_true", help="ask about notes already at ten")
    ap.add_argument("--only", action="append", default=[], help="limit to matching paths")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many notes")
    args = ap.parse_args()

    root = Path(VAULT_PATH)
    notes = wanting(root, args.only, args.all)
    if args.limit:
        notes = notes[: args.limit]
    print(f"{len(notes)} notes to retag", flush=True)
    if not notes:
        return 0

    known = vocabulary(notes, root)
    print(f"{len(known)} tags already in use", flush=True)
    gate = asyncio.Semaphore(AT_ONCE)

    async def one(path: Path, front: dict) -> tuple[Path, list[str]]:
        async with gate:
            try:
                tags = await ask(front, known)
            except llm.Unavailable as err:
                print(f"  ....  {path.name}: {err}"[:160], flush=True)
                return path, []
            print(f"  {len(tags):>2}    {path.name}: {', '.join(tags)}"[:200], flush=True)
            return path, tags

    got = await asyncio.gather(*(one(p, f) for p, f in notes))
    if args.dry:
        return 0

    conn = db.connect(DB_PATH)
    wrote = rows = 0
    for path, tags in got:
        if len(tags) < 2:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if put_in_note(path, text, tags):
            wrote += 1
            rows += put_in_db(conn, str(front_of(text).get("url", "")), tags)
    conn.commit()
    print(f"wrote {wrote} notes, {rows} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
