"""Readable text of a page, for links whose metadata says nothing.

og:title and og:description are usually enough. When they are missing or
generic ("An App Store app"), the model needs the page itself — but
not the whole page: menus, cookie banners, footers and button labels are
tokens spent on nothing. This keeps prose and drops chrome.
"""

import json
import re

from selectolax.parser import HTMLParser

# structural furniture. it repeats on every page of a site and never says
# what the page is about
JUNK = (
    "script", "style", "noscript", "svg", "iframe", "form", "button", "select",
    "nav", "header", "footer", "aside", "menu", "template",
)
# the site's own guess at where its content is, best first
CONTENT = ("article", "main", '[role="main"]', "#content", ".content", ".product", "body")

SPACE = re.compile(r"[ \t ]+")
BLANK = re.compile(r"\n{2,}")
# a line that is one or two words is a menu item far more often than prose
SHORT = re.compile(r"^\S+(\s+\S+)?$")

MAX_CHARS = 4000


def readable(html: str, limit: int = MAX_CHARS) -> str:
    """Prose from the page, chrome removed, capped at limit characters."""
    if not html:
        return ""
    tree = HTMLParser(html)
    tree.strip_tags(list(JUNK))

    root = None
    for selector in CONTENT:
        root = tree.css_first(selector)
        if root is not None and len(root.text(separator=" ", strip=True)) > 200:
            break
    if root is None:
        return ""

    lines = []
    for raw in root.text(separator="\n", strip=True).splitlines():
        line = SPACE.sub(" ", raw).strip()
        if not line or SHORT.match(line):
            continue
        if line in lines[-5:]:  # repeated captions and breadcrumbs
            continue
        lines.append(line)
        if sum(len(x) for x in lines) > limit:
            break

    return BLANK.sub("\n", "\n".join(lines))[:limit]


def has_prose(text: str) -> bool:
    """Enough of it to be worth sending to the model."""
    return len(text) >= 120


# youtube renders everything from javascript, but the player payload with the
# real description sits in the html as a json blob
YT_DESC = re.compile(r'"shortDescription":"((?:[^"\\]|\\.)*)"')
# fields worth reading out of schema.org markup, which shops and video sites
# emit even when the visible page is a javascript shell
LD_FIELDS = ("name", "headline", "description", "articleBody", "text")


def from_player(html: str) -> str:
    found = YT_DESC.search(html or "")
    if not found:
        return ""
    try:
        return json.loads(f'"{found.group(1)}"')[:MAX_CHARS]
    except ValueError:
        return ""


def walk_ld(node, out: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            walk_ld(item, out)
    elif isinstance(node, dict):
        for key in LD_FIELDS:
            value = node.get(key)
            if isinstance(value, str) and value.strip() and value not in out:
                out.append(value.strip())
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk_ld(value, out)


def from_jsonld(html: str) -> str:
    """schema.org blocks, the cleanest description a shop page ever gives."""
    if not html:
        return ""
    out: list[str] = []
    for node in HTMLParser(html).css('script[type="application/ld+json"]'):
        try:
            walk_ld(json.loads(node.text()), out)
        except (ValueError, TypeError):
            continue
    return "\n".join(out)[:MAX_CHARS]


def extract(html: str, limit: int = MAX_CHARS) -> str:
    """Everything readable, structured sources first."""
    parts = [from_player(html), from_jsonld(html), readable(html, limit)]
    text = "\n".join(p for p in parts if p)
    return text[:limit]
