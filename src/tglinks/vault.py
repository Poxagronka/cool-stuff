"""Markdown note generation for the Obsidian vault."""

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
    sent = entry["shared_at"]
    day = sent[:10]
    name = slug(f"{day} {entry['domain']} — {entry['title'] or entry['domain']}")
    return root / "links" / sent[:4] / f"{name}.md"


def tg_link(chat_id: int, msg_id: int) -> str:
    """Deep link to the source message. Private groups drop the -100 prefix."""
    raw = str(chat_id)
    if raw.startswith("-100"):
        raw = raw[4:]
    return f"https://t.me/c/{raw}/{msg_id}"


def render(entry: dict, context: list[dict]) -> str:
    front = {
        "url": entry["url"],
        "domain": entry["domain"],
        "title": entry.get("title", ""),
        "category": entry.get("category", "misc"),
        "tags": entry.get("tags", []),
        "shared_by": entry.get("shared_by", ""),
        "shared_at": entry["shared_at"],
        "status": entry.get("status", "ok"),
        "confidence": entry.get("confidence", "low"),
        "tg_link": entry.get("tg_link", ""),
    }
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
    path = note_path(root, entry)
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
      - domain
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
