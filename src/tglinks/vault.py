"""Markdown note generation for the Obsidian vault."""

import hashlib
import re
from datetime import datetime
from pathlib import Path

import yaml

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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
    name = slug(entry["title"] or entry["domain"]) or "ссылка"
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
    shared the same day all become "TikTok видео" — and without this the last
    one silently overwrites the rest.
    """
    path = note_path(root, entry)
    if not path.exists() or url_of(path) == entry["url"]:
        return path
    tail = hashlib.sha1(entry["url"].encode()).hexdigest()[:6]
    return path.with_name(f"{path.stem} {tail}.md")


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
        "status": entry.get("status", "ok"),
        "confidence": entry.get("confidence", "low"),
    }
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

    quoted = [m for m in context if (m.get("text") or "").strip()]
    if quoted:
        body.append("## Из чата\n")
        for msg in quoted:
            author = msg.get("author") or "кто-то"
            when = msg.get("sent_at", "")[11:16]
            text = msg["text"].strip().replace("\n", "\n> ")
            body.append(f"> **{author}**, {when}\n> {text}\n>")
        body.append("")

    if entry.get("tg_link"):
        body.append(f"[Открыть в Telegram]({entry['tg_link']})\n")

    return "\n".join(body)


def write(root: Path, entry: dict, context: list[dict]) -> Path:
    path = free_path(root, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(entry, context), encoding="utf-8")
    return path


ALL_LINKS_BASE = """filters:
  and:
    - file.hasProperty("url")
views:
  - type: table
    name: Все ссылки
    order:
      - file.name
      - category
      - tags
      - description
      - domain
      - shared_by
      - shared_at
    sort:
      - property: shared_at
        direction: DESC
  - type: cards
    name: Витрина
    image: image
    order:
      - file.name
      - category
      - tags
      - description
  - type: table
    name: По категориям
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
    name: Разобрать
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
