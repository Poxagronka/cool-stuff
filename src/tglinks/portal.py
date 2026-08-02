"""Read-only search over the vault notes.

The vault on disk is the single source of truth: the same files Obsidian
shows are what the portal serves. Notes are parsed once into memory — 400
files is nothing — and reparsed when the collector writes a new one.

Notes carry the chat quotes around each link, and those go out with the rest:
the chat is a place people recommend things, the context is half the value.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
QUOTE_HEAD = re.compile(r"^>\s*\*\*(.+?)\*\*,\s*(\S*)\s*$")


@dataclass
class Item:
    url: str = ""
    title: str = ""
    description: str = ""
    domain: str = ""
    category: str = "misc"
    tags: list[str] = field(default_factory=list)
    image: str = ""
    shared_by: str = ""
    shared_at: str = ""
    status: str = "ok"
    quotes: list[dict] = field(default_factory=list)
    haystack: str = ""

    def public(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "category": self.category,
            "tags": self.tags,
            "image": self.image,
            "by": self.shared_by,
            "date": self.shared_at[:10],
            "dead": self.status == "dead",
            "quotes": self.quotes,
        }


def quotes_of(text: str) -> list[dict]:
    """The chat fragment saved under the "Из чата" heading, if there is one."""
    _, _, tail = text.partition("\n## Из чата\n")
    if not tail:
        return []
    found: list[dict] = []
    for line in tail.splitlines():
        if not line.strip() and not found:
            continue  # blank line between the heading and the first quote
        if not line.startswith(">"):
            break
        head = QUOTE_HEAD.match(line)
        if head:
            found.append({"author": head.group(1), "at": head.group(2), "text": ""})
            continue
        body = line.lstrip(">").strip()
        if body and found:
            found[-1]["text"] += (" " if found[-1]["text"] else "") + body
    return [q for q in found if q["text"]]


def parse(path: Path) -> Item | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = FRONT.match(text)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or not data.get("url"):
        return None

    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    item = Item(
        url=str(data["url"]),
        title=str(data.get("title") or ""),
        description=str(data.get("description") or ""),
        domain=str(data.get("domain") or ""),
        category=str(data.get("category") or "misc"),
        tags=[str(t) for t in tags],
        image=str(data.get("image") or ""),
        shared_by=str(data.get("shared_by") or ""),
        shared_at=str(data.get("shared_at") or ""),
        status=str(data.get("status") or "ok"),
        quotes=quotes_of(text),
    )
    item.haystack = " ".join(
        [item.title, item.description, item.domain, item.url, item.shared_by,
         *item.tags, *(q["text"] for q in item.quotes)]
    ).lower()
    return item


class Index:
    """In-memory view of the vault, rebuilt when the note count changes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.items: list[Item] = []

    def load(self) -> int:
        found = []
        for path in sorted((self.root / "links").rglob("*.md")):
            item = parse(path)
            if item:
                found.append(item)
        found.sort(key=lambda i: i.shared_at, reverse=True)
        self.items = found
        return len(found)

    def categories(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.category] = counts.get(item.category, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    def top_tags(self, limit: int = 40) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for item in self.items:
            for tag in item.tags:
                counts[tag] = counts.get(tag, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]

    def search(self, query: str, category: str = "", tag: str = "", offset: int = 0,
               limit: int = 60, mode: str = "all") -> tuple[list[Item], int]:
        """Typed queries want every word; questions want the best match.

        A person typing into the box means all of it ("nike куртка"). A
        question turned into keywords by the model is a guess at synonyms, and
        demanding all of them finds nothing — there ranking wins.
        """
        words = [w for w in query.lower().split() if w]
        hits = self._match(words, category, tag, mode)
        if words and not hits:
            # russian endings: "куртка" should still find "куртки". retried
            # only when the exact words found nothing, so precision comes first
            stems = [w[:-2] if len(w) > 5 else w for w in words]
            if stems != words:
                hits = self._match(stems, category, tag, mode)
        return hits[offset:offset + limit], len(hits)

    def _match(self, words: list[str], category: str, tag: str,
               mode: str = "all") -> list[Item]:
        scored = []
        for item in self.items:
            if category and item.category != category:
                continue
            if tag and tag not in item.tags:
                continue
            score = sum(1 for w in words if w in item.haystack)
            if words and (score == 0 if mode == "any" else score < len(words)):
                continue
            scored.append((score, item))
        if mode == "any" and words:
            # stable sort keeps the newest first inside one score
            scored.sort(key=lambda p: -p[0])
        return [item for _, item in scored]
