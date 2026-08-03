"""Pages that are a list of other people's links rather than a thing of their own.

A wishlist is not a link about something, it is forty links about forty things.
Stored whole it becomes one note titled after somebody's name, and the forty
shops inside it never reach the vault, never dedup against what is already
there, and never turn up in a search. So a container page is opened and thrown
away: what travels on is what was inside it.

A reader recognises one shape of page and returns the urls in it, or None when
the url is not its business. `expand` tries them in turn and hands back an
empty list when nobody claimed the page — which is the ordinary case, since
almost every link is just a link. Adding a third shape is one function and one
line in READERS.
"""

import asyncio
import json
import logging
import re
from urllib.parse import urlsplit

import httpx

from . import canon, enrich
from .config import HTTP_TIMEOUT

log = logging.getLogger("tglinks")

# a page with hundreds of links is somebody's whole browsing history, and every
# link past this one costs a fetch and a model call. the tail is not worth it
MAX_INSIDE = 120

# how many of a wishlist's own redirect stubs to unwrap at once
FANOUT = 6

NOTION_HOSTS = ("notion.site", "notion.so", "notion.com")
# a notion page links its own uploads by their storage address, and an image
# somebody pasted into a wishlist is not one of the things on the wishlist
NOTION_ASSETS = ("amazonaws.com", "notion-static.com")
BARE_UUID = re.compile(r"[0-9a-f]{32}", re.I)
DASHED_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
# where notion keeps an address that points off its own site
NOTION_URL_FIELDS = ("bookmark_url", "display_source", "source")

META_REFRESH = re.compile(
    r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\'][^"\']*?url=([^"\'>]+)',
    re.I,
)


def _outward(urls: list[str], skip: tuple[str, ...] = ()) -> list[str]:
    """Http links that leave the container, in the order they were written."""
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            continue
        host = (urlsplit(url).hostname or "").lower()
        if any(host == s or host.endswith("." + s) for s in skip):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out[:MAX_INSIDE]


def _page_id(url: str) -> str | None:
    """The page uuid notion's own api wants, spelled 8-4-4-4-12.

    The address bar writes it as a slug with the 32 hex characters glued on the
    end, and the api refuses that spelling outright.
    """
    tail = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    dashed = DASHED_UUID.search(tail)
    if dashed:
        return dashed.group(0).lower()
    bare = BARE_UUID.findall(tail.replace("-", ""))
    if not bare:
        return None
    raw = bare[-1].lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def _unwrap(record: object) -> dict:
    """One block out of a recordMap, whichever depth this response nests it at."""
    if not isinstance(record, dict):
        return {}
    inner = record.get("value")
    if isinstance(inner, dict) and isinstance(inner.get("value"), dict):
        return inner["value"]
    return inner if isinstance(inner, dict) else record


def _annotated(properties: object) -> list[str]:
    """Addresses hiding in rich text, where a link is an annotation on a run.

    A run is `["the words", [["a", "https://..."], ["b"]]]`: the text people
    see and a list of marks on it, one of which may be the link. Notion stores
    every property this way, so the whole map is walked rather than `title`.
    """
    found: list[str] = []
    if not isinstance(properties, dict):
        return found
    for runs in properties.values():
        if not isinstance(runs, list):
            continue
        for run in runs:
            if not (isinstance(run, list) and len(run) > 1 and isinstance(run[1], list)):
                continue
            for mark in run[1]:
                if (
                    isinstance(mark, list)
                    and len(mark) == 2
                    and mark[0] == "a"
                    and isinstance(mark[1], str)
                ):
                    found.append(mark[1])
    return found


def links_in_chunk(chunk: dict) -> list[str]:
    """Every outward address in a loadPageChunk answer, page order kept."""
    blocks = ((chunk.get("recordMap") or {}).get("block") or {})
    found: list[str] = []
    for record in blocks.values():
        block = _unwrap(record)
        fmt = block.get("format")
        if isinstance(fmt, dict):
            found.extend(fmt.get(field) for field in NOTION_URL_FIELDS)
        found.extend(_annotated(block.get("properties")))
    return _outward([f for f in found if isinstance(f, str)], skip=NOTION_HOSTS + NOTION_ASSETS)


async def notion(client: httpx.AsyncClient, url: str, host: str) -> list[str] | None:
    """A public notion page is a javascript shell; the links live in an api call.

    Fetching the html gives a loader and nothing else. The same endpoint the
    page itself calls, `loadPageChunk`, answers a plain post with the whole
    record map, and every link on the page is somewhere in it.
    """
    if not any(host == h or host.endswith("." + h) for h in NOTION_HOSTS):
        return None
    page_id = _page_id(url)
    if not page_id:
        return None
    resp = await client.post(
        f"https://{urlsplit(url).hostname}/api/v3/loadPageChunk",
        json={
            "pageId": page_id,
            "limit": 200,
            "cursor": {"stack": []},
            "chunkNumber": 0,
            "verticalColumns": False,
        },
        headers={"content-type": "application/json", "user-agent": enrich.CRAWLER_AGENTS[0]},
    )
    if resp.status_code != 200:
        return None
    return links_in_chunk(resp.json()) or None


def wishlist_items(page: str) -> list[dict]:
    """The item list mywishlist.online prints into the page as a javascript var.

    Nothing on that page is an anchor: the markup is built in the browser out
    of `var wishlist_products = {...}`, which the server does render in full.
    Reading the json is the whole trick, and it carries the prices and titles
    as well, though only the addresses are wanted here.
    """
    at = page.find("var wishlist_products")
    if at < 0:
        return []
    brace = page.find("{", at)
    if brace < 0:
        return []
    data, _ = json.JSONDecoder().raw_decode(page, brace)
    if not isinstance(data, dict):
        return []
    return [item for item in data.values() if isinstance(item, dict)]


async def _clickout(client: httpx.AsyncClient, url: str) -> str:
    """Follow one `/x/<shop>/<id>` stub to the shop it stands for.

    The stub is not an http redirect — it is a two second meta refresh with an
    analytics ping in between, so nothing follows it on our behalf and the
    destination has to be read out of the head.
    """
    try:
        resp = await client.get(url, headers=enrich.CHROME_HEADERS)
    except httpx.HTTPError:
        return ""
    if resp.status_code != 200:
        return ""
    found = META_REFRESH.search(resp.text)
    return found.group(1).strip() if found else ""


async def mywishlist(client: httpx.AsyncClient, url: str, host: str) -> list[str] | None:
    """mywishlist.online wraps every item in its own click counter."""
    if host != "mywishlist.online" or not urlsplit(url).path.startswith("/w/"):
        return None
    resp = await client.get(url, headers=enrich.CHROME_HEADERS)
    if resp.status_code != 200:
        return None
    stubs = [
        item["redirect_url"]
        for item in wishlist_items(resp.text)
        if isinstance(item.get("redirect_url"), str)
    ][:MAX_INSIDE]
    if not stubs:
        return None

    gate = asyncio.Semaphore(FANOUT)

    async def one(stub: str) -> str:
        async with gate:
            return await _clickout(client, stub)

    # a stub that will not open is dropped rather than kept: the note it would
    # write is named after the interstitial and says nothing about the thing
    shops = await asyncio.gather(*(one(stub) for stub in stubs))
    return _outward([s for s in shops if s], skip=(host,)) or None


READERS = (notion, mywishlist)


async def expand(url: str) -> list[str]:
    """The links inside a container page, or nothing when it is not one."""
    host = canon.domain(url)
    limits = httpx.Limits(max_connections=FANOUT)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        limits=limits,
        max_redirects=enrich.MAX_HOPS,
        transport=enrich.GuardedTransport(httpx.AsyncHTTPTransport(limits=limits)),
    ) as client:
        for reader in READERS:
            try:
                found = await reader(client, url, host)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                continue
            if found:
                log.info("%s is a container: %s links inside", url, len(found))
                return found
    return []
