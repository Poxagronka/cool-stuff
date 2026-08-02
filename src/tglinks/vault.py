"""Markdown note generation for the Obsidian vault."""

import hashlib
import re
from datetime import datetime
from pathlib import Path

import yaml

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
LINK = re.compile(r"(?:https?://|www\.)\S+", re.I)

# the heading over the quotes, by where they were said
SAID_UNDER = {"chat": "From the chat", "saved": "Saved to myself"}


def speech(text: str) -> str:
    """What a person actually said, with the urls taken out.

    One message in the chat was a list of twenty instagram profiles under the
    word "clo". Quoted whole, it became the visible context of every one of
    those twenty links and dragged all their domains into the search index —
    searching for one brand returned the other nineteen.
    """
    stripped = LINK.sub(" ", text)
    return re.sub(r"[ \t]+", " ", stripped).strip(" \n-—·,")


def slug(text: str, limit: int = 60) -> str:
    cleaned = ILLEGAL.sub("", text).replace("\n", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:limit].rstrip(" .")


def note_path(root: Path, entry: dict) -> Path:
    """Named after the thing itself.

    The date and the domain used to lead the name, and in a list of results
    every line started with noise instead of what the link is. Both are still
    properties, so nothing is lost.
    """
    sent = entry["shared_at"]
    name = slug(entry["title"] or entry["domain"]) or "link"
    return root / "links" / sent[:4] / f"{name}.md"


def url_of(path: Path) -> str:
    """The url a note already on disk points at, empty if it has none."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:12]:
            if line.startswith("url:"):
                return line[4:].strip().strip("'\"")
    except OSError:
        pass
    return ""


def free_path(root: Path, entry: dict) -> Path:
    """Path for the note, sidestepping a name another link already took.

    Links with no metadata collapse into the same name — several TikToks
    shared the same day all become "TikTok video" — and without this the last
    one silently overwrites the rest.
    """
    path = note_path(root, entry)
    if not path.exists() or url_of(path) == entry["url"]:
        return path
    tail = hashlib.sha1(entry["url"].encode()).hexdigest()[:6]
    return path.with_name(f"{path.stem} {tail}.md")


def recase(path: Path) -> None:
    """Make the name on disk match the name we mean, letter for letter.

    Only does anything where the filesystem folds case, which is every mac and
    every windows. There a note whose title went from "Gnuhr" to "GNUHR" is
    written straight into the old file and the old spelling stays in the
    directory, so the vault and the database disagree about what the note is
    called from then on.
    """
    if not path.parent.is_dir():
        return
    for other in path.parent.iterdir():
        if other.name != path.name and other.name.lower() == path.name.lower():
            other.rename(path)
            return


def retire(root: Path, rel_path: str, url: str, keeping: Path | None = None) -> bool:
    """Take away a note an entry has moved off, if it is provably that entry's.

    A renamed link leaves its old file behind, still indexed and still found
    by search, saying whatever it said before. The name proves nothing —
    free_path hands two different links the same stem with a hash on the end —
    so the url inside the file is the only proof of whose note it is. The vault
    is a git repo that gets pushed, so a guess here deletes someone's note for
    good; refusing is always the cheaper mistake.

    `keeping` is the note that has just been written. Two names that differ
    only in case are two names for one file on a mac, so a title recapitalised
    is a move on paper and nothing at all on disk: the url inside the "old"
    file is the new note's url, it matches, and the delete takes the note that
    was just saved. Nineteen of them went that way in one run.
    """
    path = root / rel_path
    if not path.is_file() or url_of(path) != url:
        return False
    if keeping is not None and keeping.is_file() and path.samefile(keeping):
        return False
    path.unlink()
    return True


def tg_link(chat_id: int, msg_id: int) -> str:
    """Deep link to the source message, empty when no such link can exist.

    Only supergroups and channels have t.me/c/ links, and their ids carry the
    -100 prefix that has to come off. A basic group id gets no link at all:
    building one anyway would put a dead url in every note.
    """
    raw = str(chat_id)
    if not raw.startswith("-100"):
        return ""
    return f"https://t.me/c/{raw[4:]}/{msg_id}"


def render(entry: dict, context: list[dict]) -> str:
    front = {
        "url": entry["url"],
        "domain": entry["domain"],
        "title": entry.get("title", ""),
        # duplicated into the body below, but only a property shows up as a
        # column in bases and in the hover preview
        "description": entry.get("description", ""),
        "category": entry.get("category", "misc"),
        "tags": entry.get("tags", []),
        "shared_by": entry.get("shared_by", ""),
        "shared_at": entry["shared_at"],
        # where it came from. a note saved to yourself reads differently from
        # one the group discussed, and the vault should say which it is
        "source": entry.get("source", "chat"),
        "status": entry.get("status", "ok"),
        "confidence": entry.get("confidence", "low"),
    }
    # search only, never displayed: russian and english words for the same
    # thing, so the language a note happens to be written in stops mattering
    if entry.get("keywords"):
        front["keywords"] = entry["keywords"]
    # basic groups have no deep link, and an empty property is noise in bases
    if entry.get("tg_link"):
        front["tg_link"] = entry["tg_link"]
    if entry.get("image"):
        front["image"] = entry["image"]
    if entry.get("price"):
        front["price"] = str(entry["price"])

    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
    body = [f"---\n{head}\n---\n"]

    if entry.get("image"):
        body.append(f"![]({entry['image']})\n")
    if entry.get("description"):
        body.append(f"{entry['description']}\n")

    body.append(f"[{entry['domain']}]({entry['url']})\n")

    quoted = [(m, speech(m.get("text") or "")) for m in context]
    quoted = [(m, said) for m, said in quoted if said]
    if quoted:
        body.append(f"## {SAID_UNDER.get(entry.get('source'), 'From the chat')}\n")
        for msg, said in quoted:
            author = msg.get("author") or "someone"
            when = msg.get("sent_at", "")[11:16]
            wrapped = said.replace("\n", "\n> ")
            body.append(f"> **{author}**, {when}\n> {wrapped}\n>")
        body.append("")

    if entry.get("tg_link"):
        body.append(f"[Open in Telegram]({entry['tg_link']})\n")

    return "\n".join(body)


def write(root: Path, entry: dict, context: list[dict]) -> Path:
    path = free_path(root, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    recase(path)
    path.write_text(render(entry, context), encoding="utf-8")
    return path


ALL_LINKS_BASE = """filters:
  and:
    - file.hasProperty("url")
views:
  - type: table
    name: All links
    order:
      - file.name
      - category
      - tags
      - description
      - domain
      - shared_by
      - source
      - shared_at
    sort:
      - property: shared_at
        direction: DESC
  - type: cards
    name: Gallery
    image: image
    order:
      - file.name
      - category
      - tags
      - description
  - type: table
    name: By category
    groupBy: category
    order:
      - file.name
      - tags
      - description
      - domain
    sort:
      - property: category
        direction: ASC
"""

INBOX_BASE = """filters:
  or:
    - status == "inbox"
    - category == "misc"
    - confidence == "low"
views:
  - type: table
    name: To sort
    order:
      - file.name
      - category
      - domain
      - confidence
      - shared_at
"""


def scaffold(root: Path) -> None:
    """Create the vault skeleton if it is not there yet."""
    for sub in ("links", "bases", "attachments"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "bases" / "All Links.base").write_text(ALL_LINKS_BASE, encoding="utf-8")
    (root / "bases" / "Inbox.base").write_text(INBOX_BASE, encoding="utf-8")
    year = str(datetime.now().year)
    (root / "links" / year).mkdir(parents=True, exist_ok=True)
