"""Pull urls out of a telegram message.

Two entity types carry links and missing either one loses real data:
`url` is a bare link in the text, `text_link` hides the url behind words.
"""

import re

BARE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.I)
TRAILING = ".,;:!?»\"'”’)]}"


def _clean(url: str) -> str:
    url = url.strip().rstrip(TRAILING)
    # a closing bracket only counts if it has an opener inside the url
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def from_entities(text: str, entities: list[dict] | None) -> list[str]:
    """Bot api style: message.entities plus utf-16 offsets."""
    found: list[str] = []
    if entities:
        units = text.encode("utf-16-le")
        for ent in entities:
            kind = ent.get("type")
            if kind == "text_link" and ent.get("url"):
                found.append(_clean(ent["url"]))
            elif kind == "url":
                start, length = ent["offset"] * 2, ent["length"] * 2
                found.append(_clean(units[start:start + length].decode("utf-16-le")))
    if not found:
        found = [_clean(m.group(0)) for m in BARE.finditer(text or "")]

    seen, out = set(), []
    for url in found:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def from_message(msg: dict) -> list[str]:
    """Everything link-ish in a bot api update: text, caption, preview."""
    urls: list[str] = []
    for body, key in ((msg.get("text"), "entities"), (msg.get("caption"), "caption_entities")):
        if body:
            urls.extend(from_entities(body, msg.get(key)))

    preview = (msg.get("link_preview_options") or {}).get("url")
    if preview:
        urls.append(_clean(preview))

    seen, out = set(), []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out
