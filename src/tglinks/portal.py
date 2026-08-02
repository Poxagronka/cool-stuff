"""Read-only search over the vault notes.

The vault on disk is the single source of truth: the same files Obsidian
shows are what the portal serves. Notes are parsed once into memory — 400
files is nothing — and reparsed when the collector writes a new one.

Notes carry the chat quotes around each link, and those go out with the rest:
the chat is a place people recommend things, the context is half the value.

Matching itself lives in `textsearch`: words folded to latin, resolved through
prefix and near-spelling, and weighted by how rare they are. What this module
adds on top is where the word was found — a brand in the title means the note
is about it, the same brand in someone's aside means it is not.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .textsearch import Terms, tokens

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
    source: str = "chat"
    status: str = "ok"
    quotes: list[dict] = field(default_factory=list)
    # every word of the note, each flagged with whether it says what the thing
    # is (title, domain, tags, keywords) or merely stands near it
    words: dict[str, bool] = field(default_factory=dict)

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
            "saved": self.source == "saved",
            "date": self.shared_at[:10],
            "dead": self.status == "dead",
            "quotes": self.quotes,
        }


def quotes_of(text: str) -> list[dict]:
    """The chat fragment saved under the quotes heading, if there is one."""
    for heading in ("\n## From the chat\n", "\n## Saved to myself\n", "\n## Из чата\n"):
        _, _, tail = text.partition(heading)
        if tail:
            break
    else:
        return []
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
    keywords = data.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    item = Item(
        url=str(data["url"]),
        title=str(data.get("title") or ""),
        description=str(data.get("description") or ""),
        domain=str(data.get("domain") or ""),
        category=str(data.get("category") or "misc"),
        tags=[str(t) for t in tags],
        image=str(data.get("image") or ""),
        shared_by=str(data.get("shared_by") or ""),
        source=str(data.get("source") or "chat"),
        shared_at=str(data.get("shared_at") or ""),
        status=str(data.get("status") or "ok"),
        quotes=quotes_of(text),
    )
    # the weak half first, then the strong half over the top of it: a word in
    # both ends up strong, which is what someone typing it would expect
    for word in tokens(" ".join(
        [item.description, item.url, item.shared_by, *(q["text"] for q in item.quotes)]
    )):
        item.words.setdefault(word, False)
    for word in tokens(" ".join(
        [item.title, item.domain, *item.tags, *[str(k) for k in keywords]]
    )):
        item.words[word] = True
    return item


class Index:
    """In-memory view of the vault, rebuilt when the note count changes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.items: list[Item] = []
        self.terms = Terms()

    def load(self) -> int:
        found = []
        for path in sorted((self.root / "links").rglob("*.md")):
            item = parse(path)
            if item:
                found.append(item)
        found.sort(key=lambda i: i.shared_at, reverse=True)
        self.items = found
        terms = Terms()
        for item in found:
            terms.add(set(item.words))
        terms.finish()
        self.terms = terms
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

    def related(self, items: list[Item], chosen: list[str],
                limit: int = 40) -> list[tuple[str, int]]:
        """Tags that keep company with the ones already picked.

        This is what makes the cloud walkable: pick "shoes" and the tags of
        everything tagged shoes come up — hoka, nike, running — so the next
        click narrows by something that actually exists in the results.
        """
        counts: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                if tag not in chosen:
                    counts[tag] = counts.get(tag, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]

    def graph(self, items: list[Item], chosen: list[str],
              limit: int = 60) -> dict:
        """The same tags as a web: who is there, and who hangs next to whom.

        `related` answers "what could I pick next" as a flat list, which is all
        a cloud needs. A graph also needs the lines between them, and those are
        just the pairs that turn up on the same note. Tags already picked stay
        in the web — dropping them would cut the path you walked in on.
        """
        counts: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                counts[tag] = counts.get(tag, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        # a picked tag can sit outside the top slice once the results narrow,
        # and a web missing the node you are standing on reads as a bug
        keep = dict(ranked[:limit])
        for tag in chosen:
            if tag in counts:
                keep[tag] = counts[tag]

        pairs: dict[tuple[str, str], int] = {}
        for item in items:
            here = sorted(t for t in set(item.tags) if t in keep)
            for i, one in enumerate(here):
                for other in here[i + 1:]:
                    pairs[(one, other)] = pairs.get((one, other), 0) + 1
        edges = sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))

        nodes = sorted(keep.items(), key=lambda kv: (-kv[1], kv[0]))
        return {
            "nodes": [{"tag": t, "count": n} for t, n in nodes],
            "edges": [[a, b, n] for (a, b), n in edges],
            "picked": [t for t in chosen if t in keep],
        }

    def find(self, query: str, category: str = "", tags: list[str] | None = None,
             mode: str = "all") -> list[Item]:
        """Everything that matches, in order. The caller slices it.

        A person typing into the box means all of it ("nike jacket"). A
        question turned into keywords by the model is a guess at synonyms, and
        demanding all of them finds nothing — there ranking wins.
        """
        return self._match(tokens(query), category, list(tags or []), mode)

    def search(self, query: str, category: str = "", tags: list[str] | None = None,
               offset: int = 0, limit: int = 60,
               mode: str = "all") -> tuple[list[Item], int]:
        hits = self.find(query, category, tags, mode)
        return hits[offset:offset + limit], len(hits)

    def _match(self, words: list[str], category: str, tags: list[str],
               mode: str = "all") -> list[Item]:
        # what each typed word could mean, worked out once against the whole
        # vocabulary rather than once per note
        plan = [self.terms.expand(w) for w in words]
        scored = []
        for item in self.items:
            if category and item.category != category:
                continue
            if any(t not in item.tags for t in tags):
                continue
            score, matched = 0.0, 0
            for options in plan:
                best = 0.0
                for term, quality in options:
                    strong = item.words.get(term)
                    if strong is None:
                        continue
                    # a word in the title or the tags is worth three of the
                    # same word in a passing remark, and a word only two notes
                    # carry is worth more than one half the vault carries
                    best = max(best, self.terms.idf(term) * quality * (3.0 if strong else 1.0))
                if best:
                    matched += 1
                    score += best
            if words and (not matched if mode == "any" else matched < len(words)):
                continue
            scored.append((score, item))
        if words:
            # stable sort keeps the newest first inside one score
            scored.sort(key=lambda p: -p[0])
        return [item for _, item in scored]
