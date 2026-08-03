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
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .textsearch import Terms, query_tokens, tokens

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
QUOTE_HEAD = re.compile(r"^>\s*\*\*(.+?)\*\*,\s*(\S*)\s*$")

# where a link lives, and what shape it arrived in. these stay on the note as
# context, but they are not what anything is about: "instagram" is the biggest
# tag in the vault and knowing it tells you nothing, so it never becomes a
# bubble and never reaches the model as a tag worth searching by
SOURCE_TAGS = frozenset({
    "aliexpress", "amazon", "app-store", "apple-music", "appstore", "behance",
    "bluesky", "discord", "dribbble", "etsy", "facebook", "flickr", "github",
    "gif", "google-play", "image", "instagram", "kickstarter", "linkedin",
    "medium", "netflix", "patreon", "photo", "pinterest", "podcast", "reddit",
    "shopify", "snapchat", "soundcloud", "spotify", "substack", "telegram",
    "threads", "tiktok", "tumblr", "twitch", "twitter", "video", "vimeo", "vk",
    "whatsapp", "wikipedia", "x", "youtube",
})

# a shape rather than a subject. "brand" sat on 16 notes and every one of them
# was a shop selling something: it is the seventh biggest tag in the vault and
# narrows nothing, so it goes the same way as the platforms
VAGUE_TAGS = frozenset({"brand"})

OFF_WEB = SOURCE_TAGS | VAGUE_TAGS


def merge_hits(*runs: list["Item"]) -> list["Item"]:
    """Several result lists as one, each note at its best place in any of them.

    A query in another alphabet is searched twice — as it was typed, which
    reaches the russian captions the vault kept, and translated, which reaches
    everything written in english. Neither half is the right answer on its own.
    """
    best: dict[str, tuple[int, Item]] = {}
    for run in runs:
        for rank, item in enumerate(run):
            seen = best.get(item.url)
            if seen is None or rank < seen[0]:
                best[item.url] = (rank, item)
    return [item for _, item in sorted(best.values(), key=lambda pair: pair[0])]


def _ranked(items: list["Item"]) -> list[tuple[str, int]]:
    """Subject tags of these items, biggest first, ties broken by name."""
    counts: dict[str, int] = {}
    for item in items:
        for tag in item.tags:
            if tag not in OFF_WEB:
                counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass
class Item:
    url: str = ""
    title: str = ""
    description: str = ""
    domain: str = ""
    category: str = "misc"
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    confidence: str = ""
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
            # the rest is only read by the panel that opens on a card, and that
            # panel is the note itself, so it carries the whole front matter
            "keywords": self.keywords,
            "confidence": self.confidence,
            "at": self.shared_at,
            "source": self.source,
            "status": self.status,
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
        keywords=[str(k) for k in keywords],
        confidence=str(data.get("confidence") or ""),
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
        [item.title, item.domain, *item.tags, *item.keywords]
    )):
        item.words[word] = True
    return item


class Index:
    """In-memory view of the vault, rebuilt when the note count changes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.items: list[Item] = []
        self.terms = Terms()
        self.stamp = (0, 0.0)
        self._checked = 0.0

    def _shape(self) -> tuple[int, float]:
        """How many notes there are and when the newest one was written."""
        times = [p.stat().st_mtime for p in (self.root / "links").rglob("*.md")]
        return len(times), max(times, default=0.0)

    def stale(self) -> bool:
        """Have the notes moved on disk since they were read?

        The collector reloads the index itself when it writes a note, so the
        only way the two drift apart is a vault that changed underneath the
        process: a `git pull` on the machine, or a rewrite pushed from the
        laptop. That is how an afternoon of regenerated notes went on being
        served in their old form. One walk of the tree is cheap, but not on
        every keystroke, so it is asked at most twice a minute.
        """
        now = time.monotonic()
        if now - self._checked < 30:
            return False
        self._checked = now
        return self._shape() != self.stamp

    def load(self) -> int:
        self.stamp = self._shape()
        self._checked = time.monotonic()
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

    def top_tags(self, limit: int = 40) -> list[tuple[str, int]]:
        return _ranked(self.items)[:limit]

    def graph(self, items: list[Item], chosen: list[str],
              limit: int = 14) -> dict:
        """The tags of these items as a web: who is there, and who hangs next
        to whom.

        The nodes are the subject tags the current results carry — `OFF_WEB`
        never makes it in — and the lines are the pairs that turn up on the same
        note. Tags already picked stay in the web, dropping them would cut the
        path you walked in on.

        Only the biggest handful. Sixty bubbles in a box this size sat on top
        of each other and their labels ran together; a dozen is a picture you
        can read, and picking one of them narrows `items` so the next dozen is
        drawn from what that tag actually keeps company with.
        """
        ranked = _ranked(items)
        counts = dict(ranked)
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
        return self._match(query_tokens(query), category, list(tags or []), mode)

    def search(self, query: str, category: str = "", tags: list[str] | None = None,
               offset: int = 0, limit: int = 60,
               mode: str = "all") -> tuple[list[Item], int]:
        hits = self.find(query, category, tags, mode)
        return hits[offset:offset + limit], len(hits)

    def _match(self, words: list[tuple[str, bool]], category: str, tags: list[str],
               mode: str = "all") -> list[Item]:
        # what each typed word could mean, worked out once against the whole
        # vocabulary rather than once per note. a word folded out of cyrillic
        # only ever means itself: see textsearch.query_tokens
        plan = [self.terms.expand(w, no_guessing=folded) for w, folded in words]
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
