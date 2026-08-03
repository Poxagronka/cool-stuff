"""A picture for a card whose page never declared one.

Most sites hand over `og:image` and the ladder is done in one line. The ones
that do not still have the picture on the page — a shop that forgot the meta
tag still shows the product — so the fallback is to read the document and pick.

Picking is the whole problem. The first `<img>` in a shop page is the logo, the
second is a payment badge, and somewhere below them is a tracking pixel with no
pixels. So candidates are scored rather than taken in order: the structured
data a shop publishes about its own product wins outright, then whatever sits
in the main column and is big enough to be worth looking at. Nothing scoring
above zero means no picture, which is a better card than one showing a Visa
logo.
"""

import json
import logging
import re
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from selectolax.parser import HTMLParser

from .config import GOOGLE_CSE_CX, GOOGLE_CSE_KEY, HTTP_TIMEOUT

log = logging.getLogger("tglinks")

# hosts that only ever serve analytics and buttons, never content
OFFSITE_JUNK = (
    "google-analytics.com", "googletagmanager.com", "mc.yandex.ru", "yandex.ru/watch",
    "facebook.com/tr", "facebook.com/plugins", "paypalobjects.com", "gravatar.com",
    "doubleclick.net", "criteo.com", "scorecardresearch.com", "b.stats.paypal.com",
)

# words that name furniture rather than content, in a path or a class
FURNITURE = re.compile(
    r"logo|icon|sprite|badge|avatar|favicon|placeholder|spinner|loader|pixel|"
    r"payment|visa|mastercard|paypal|klarna|social|share|arrow|chevron|burger|"
    r"flag|banner-ad|advert|newsletter|cookie|trustpilot|rating-star",
    re.I,
)

# a shape declared in the url by a cdn: ?width=2048, /800x600/, _1200x.jpg
SIZE_IN_URL = re.compile(r"(?:^|[/_?&-])(?:w|width|h|height)=(\d{2,5})|(?<![\d.])(\d{3,5})x(\d{3,5})(?![\d.])")

# the containers a page puts its actual subject in
MAIN = ("main", "article", '[role="main"]', "#main", "#content", ".product", ".product-media",
        ".product-gallery", ".entry-content", ".post-content")

# below this a picture is a thumbnail or an icon, whatever it is called
MIN_SIDE = 200

# scores above this are trusted enough to use
FLOOR = 1


def _absolute(src: str, base: str) -> str:
    """An address that can actually be fetched, or nothing."""
    src = (src or "").strip()
    if not src or src.startswith(("data:", "blob:", "javascript:", "#")):
        return ""
    full = urljoin(base, src)
    parts = urlsplit(full)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return full


def _plausible(url: str) -> bool:
    if any(junk in url for junk in OFFSITE_JUNK):
        return False
    # an svg is a logo or an interface glyph in every case seen so far, and it
    # renders as a shape on a card rather than a photograph
    return not urlsplit(url).path.lower().endswith(".svg")


def _declared_size(node_attrs: dict, url: str) -> int:
    """The shorter side, as far as anything is willing to say."""
    sides = []
    for key in ("width", "height"):
        raw = (node_attrs.get(key) or "").strip().rstrip("px")
        if raw.isdigit():
            sides.append(int(raw))
    found = SIZE_IN_URL.search(url)
    if found:
        sides += [int(g) for g in found.groups() if g]
    return min(sides) if sides else 0


def _from_jsonld(tree: HTMLParser, base: str) -> list[str]:
    """Images a page publishes about itself in structured data.

    A shop describing its own Product names the product photo here, which is
    exactly the picture wanted and never the logo. Worth walking the whole
    tree: the useful node is often buried in a @graph or an itemListElement.
    """
    out: list[str] = []
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            here = stack.pop(0)
            if isinstance(here, list):
                stack.extend(here)
                continue
            if not isinstance(here, dict):
                continue
            stack.extend(v for v in here.values() if isinstance(v, (dict, list)))
            kind = str(here.get("@type", "")).lower()
            if kind in ("organization", "website", "breadcrumblist", "searchaction"):
                continue   # its "image" is the logo
            for key in ("image", "thumbnailUrl", "contentUrl"):
                got = here.get(key)
                for one in (got if isinstance(got, list) else [got]):
                    if isinstance(one, str):
                        out.append(one)
                    elif isinstance(one, dict) and isinstance(one.get("url"), str):
                        out.append(one["url"])
    # structured data is trusted about which picture matters, not about what
    # the file is: a shop that declares its header logo as the page image is
    # still declaring a logo, and the filename says so
    return [
        u for u in (_absolute(o, base) for o in out)
        if u and _plausible(u) and not FURNITURE.search(u)
    ]


def _src_of(attrs: dict) -> str:
    """Whatever this `<img>` will actually load, lazy attributes included."""
    for key in ("src", "data-src", "data-original", "data-lazy-src"):
        got = (attrs.get(key) or "").strip()
        if got and not got.startswith("data:"):
            return got
    for key in ("srcset", "data-srcset"):
        raw = attrs.get(key) or ""
        # widest candidate last by convention, and the widest is the one wanted
        best = [c.strip().split(" ")[0] for c in raw.split(",") if c.strip()]
        if best and not best[-1].startswith("data:"):
            return best[-1]
    return ""


def _in_main(tree: HTMLParser) -> set[str]:
    """Sources sitting inside the page's main column."""
    inside: set[str] = set()
    for selector in MAIN:
        for holder in tree.css(selector):
            for img in holder.css("img"):
                got = _src_of(img.attributes)
                if got:
                    inside.add(got)
    return inside


def candidates(html: str, base: str) -> list[tuple[int, str]]:
    """Every picture on the page worth considering, best score first."""
    tree = HTMLParser(html)
    scored: dict[str, int] = {}

    def offer(url: str, score: int) -> None:
        if url and score > scored.get(url, -1):
            scored[url] = score

    # structured data is the page telling us which picture is the subject
    for url in _from_jsonld(tree, base):
        offer(url, 6)

    main = _in_main(tree)
    for img in tree.css("img"):
        attrs = img.attributes
        raw = _src_of(attrs)
        url = _absolute(raw, base)
        if not url or not _plausible(url):
            continue

        described = f"{raw} {attrs.get('class') or ''} {attrs.get('id') or ''} {attrs.get('alt') or ''}"
        if FURNITURE.search(described):
            continue

        side = _declared_size(attrs, url)
        if side and side < MIN_SIDE:
            continue

        score = 1 if raw in main else 0
        if side >= 600:
            score += 2
        elif side >= MIN_SIDE:
            score += 1
        # an image the page bothered to describe is usually the subject
        if len(attrs.get("alt") or "") > 8:
            score += 1
        offer(url, score)

    return sorted(((s, u) for u, s in scored.items() if s >= FLOOR), key=lambda p: -p[0])


def pick(html: str, base: str) -> str:
    """The one picture to put on the card, or nothing when none convinces."""
    if not html:
        return ""
    found = candidates(html, base)
    return found[0][1] if found else ""


# ---------- the tail: when the page itself gave nothing ----------

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# path pieces that name the shop's filing system rather than the thing
PATH_NOISE = re.compile(
    r"^(products?|collections?|shop|store|item|items|p|en|de|fr|pl|ru|us|uk|"
    r"catalog|category|categories|pages?|blog|post|article|index|default|home|"
    r"[a-z]{2}-[a-z]{2}|\d+)$",
    re.I,
)


def words_in(url: str) -> str:
    """What the address itself says the page is about.

    A shop writes the product into the path — `/products/fanghorn-ii-extrait`
    — so the slug is the description of last resort. Prefixed with the domain,
    because "fanghorn ii extrait" alone finds a fantasy wiki.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    pieces = [unquote(p) for p in parts.path.split("/") if p]
    said = [
        re.sub(r"[-_+]+", " ", p.rsplit(".", 1)[0]).strip()
        for p in pieces
        if not PATH_NOISE.match(p)
    ]
    tail = " ".join(w for w in said if len(w) > 2)[-120:]
    return f"{host} {tail}".strip()


async def from_search(url: str, title: str = "") -> str:
    """Ask google for a picture of the thing, when nothing on the page was one.

    Last in line and metered: the free tier of the custom search api is a
    hundred queries a day, which is a backfill of one afternoon and then
    nothing. So this runs only after the document has been read and refused,
    and no key at all just means the ladder ends one rung earlier.
    """
    if not GOOGLE_CSE_KEY or not GOOGLE_CSE_CX:
        return ""
    # the title is what the page called itself, which beats a slug when it
    # exists; the domain goes in either way, or the search leaves the shop
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    query = f"{host} {title}".strip() if len(title) > 4 else words_in(url)
    if not query:
        return ""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(SEARCH_URL, params={
                "key": GOOGLE_CSE_KEY, "cx": GOOGLE_CSE_CX, "q": query,
                "searchType": "image", "num": 5, "safe": "off",
            })
    except httpx.HTTPError:
        return ""
    if resp.status_code != 200:
        # 429 is the daily quota, and it is the ordinary end of a backfill
        log.info("image search for %s: http %s", url, resp.status_code)
        return ""
    for item in (resp.json().get("items") or []):
        found = item.get("link") or ""
        if found.startswith("https://") and _plausible(found):
            return found
    return ""
