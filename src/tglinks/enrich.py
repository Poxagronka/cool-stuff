"""Metadata enrichment ladder. Everything here is free: no proxies, no paid api.

tier 0  telegram's own link preview, if the message carried one
tier 1  oembed for the sites that offer it
tier 2  plain fetch with a full chrome header set, aborted at </head>
tier 3  social-crawler user agents, tried in order
tier 4  curl_cffi tls impersonation

Tier 5 (headless browser) and tier 6 (paid unlocker) are deliberately absent:
they cost money or a lot of cpu, and cover only a few percent of links.
"""

import asyncio
import html
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

import httpx
from selectolax.parser import HTMLParser

from . import canon, pagetext, sites
from .config import HTTP_TIMEOUT

CHROME_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,ru;q=0.8",
    # no br or zstd: httpx cannot decompress either without extra packages,
    # and the server takes us at our word — the body comes back as binary mush
    # that parses into empty metadata
    "accept-encoding": "gzip, deflate",
    "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not?A_Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

# no single agent covers everything; whatsapp is the widest, so it leads
CRAWLER_AGENTS = [
    "WhatsApp/2.23.20.0",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Twitterbot/1.0",
    "TelegramBot (like TwitterBot)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
]

OEMBED = {
    "youtube.com": "https://www.youtube.com/oembed?format=json&url={u}",
    "youtu.be": "https://www.youtube.com/oembed?format=json&url={u}",
    "vimeo.com": "https://vimeo.com/api/oembed.json?url={u}",
    "x.com": "https://publish.x.com/oembed?url={u}",
    "tiktok.com": "https://www.tiktok.com/oembed?url={u}",
    "instagram.com": "https://graph.facebook.com/v25.0/instagram_oembed?url={u}",
    "reddit.com": "https://www.reddit.com/oembed?url={u}",
    "soundcloud.com": "https://soundcloud.com/oembed?format=json&url={u}",
    "open.spotify.com": "https://open.spotify.com/oembed?url={u}",
    "flickr.com": "https://www.flickr.com/services/oembed?format=json&url={u}",
    "bsky.app": "https://embed.bsky.app/oembed?url={u}",
    "figma.com": "https://www.figma.com/api/oembed?url={u}",
    "loom.com": "https://www.loom.com/v1/oembed?url={u}",
}

HEAD_END = re.compile(rb"</head\s*>", re.I)
MAX_BYTES = 512 * 1024

# challenge and interstitial pages return http 200 with a plausible title, so
# they pass a naive "did we get metadata" check. these markers catch them.
BLOCKED_MARKERS = re.compile(
    r"please wait|just a moment|verify you are|are you a robot|checking your browser"
    r"|attention required|access denied|enable javascript|security check"
    r"|доступ ограничен|проверка браузера",
    re.I,
)
TAGS = re.compile(r"<[^>]+>")


@dataclass
class Meta:
    url: str
    title: str = ""
    description: str = ""
    image: str = ""
    site_name: str = ""
    price: str = ""
    tier: str = ""
    http_status: int = 0
    fields: dict = field(default_factory=dict)

    def blocked(self) -> bool:
        return bool(BLOCKED_MARKERS.search(f"{self.title} {self.description}"))

    def ok(self) -> bool:
        return bool(self.title or self.description) and not self.blocked()


def _from_html(html: str, url: str) -> Meta:
    tree = HTMLParser(html)
    props: dict[str, str] = {}
    for node in tree.css("meta"):
        name = node.attributes.get("property") or node.attributes.get("name") or ""
        content = node.attributes.get("content") or ""
        if name and content and name not in props:
            props[name.lower()] = content.strip()

    title_node = tree.css_first("title")
    return Meta(
        url=url,
        title=props.get("og:title") or props.get("twitter:title")
        or (title_node.text(strip=True) if title_node else ""),
        description=props.get("og:description") or props.get("twitter:description")
        or props.get("description", ""),
        image=props.get("og:image") or props.get("twitter:image", ""),
        site_name=props.get("og:site_name", ""),
        price=props.get("product:price:amount") or props.get("og:price:amount", ""),
        fields=props,
    )


async def _fetch_head(client: httpx.AsyncClient, url: str, headers: dict) -> tuple[int, str]:
    """Stream the response and stop reading once </head> is in.

    Average full page is ~550 KB, average head ~47 KB. Worth the extra code.
    """
    buf = bytearray()
    async with client.stream("GET", url, headers=headers) as resp:
        if resp.status_code >= 400:
            return resp.status_code, ""
        async for chunk in resp.aiter_bytes():
            buf.extend(chunk)
            if HEAD_END.search(buf) or len(buf) > MAX_BYTES:
                break
        return resp.status_code, buf.decode(resp.encoding or "utf-8", errors="replace")


async def tier_oembed(client: httpx.AsyncClient, url: str) -> Meta | None:
    host = canon.domain(url)
    endpoint = OEMBED.get(host)
    if not endpoint:
        return None
    try:
        resp = await client.get(endpoint.format(u=quote(url, safe="")))
        if resp.status_code != 200 or "json" not in resp.headers.get("content-type", ""):
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    # x, bluesky and mastodon have no title field: the post text lives in html
    body = TAGS.sub(" ", data.get("html", "") or "")
    body = html.unescape(re.sub(r"\s+", " ", body)).strip()
    author = data.get("author_name", "")
    return Meta(
        url=url,
        title=data.get("title") or author or host,
        description=body[:400] if body else author,
        image=data.get("thumbnail_url", ""),
        site_name=data.get("provider_name", host),
        tier="oembed",
        http_status=200,
        fields=data,
    )


async def tier_site(client: httpx.AsyncClient, url: str) -> Meta | None:
    """Sites with a known public endpoint, resolved before the generic ladder."""
    found = await sites.probe(client, url)
    if not found:
        return None
    return Meta(
        url=url,
        title=found.get("title", ""),
        description=found.get("description", ""),
        image=found.get("image", ""),
        site_name=found.get("site_name", ""),
        price=found.get("price", ""),
        tier="site",
        http_status=200,
        fields={"page_text": found.get("text", "")},
    )


async def tier_chrome(client: httpx.AsyncClient, url: str) -> Meta | None:
    try:
        status, html = await _fetch_head(client, url, CHROME_HEADERS)
    except httpx.HTTPError:
        return None
    if not html:
        return Meta(url=url, tier="chrome", http_status=status)
    meta = _from_html(html, url)
    meta.tier, meta.http_status = "chrome", status
    return meta


async def tier_crawlers(client: httpx.AsyncClient, url: str) -> Meta | None:
    for agent in CRAWLER_AGENTS:
        headers = {**CHROME_HEADERS, "user-agent": agent}
        try:
            status, html = await _fetch_head(client, url, headers)
        except httpx.HTTPError:
            continue
        if not html:
            continue
        meta = _from_html(html, url)
        if meta.ok():
            meta.tier = f"crawler:{agent.split('/')[0]}"
            meta.http_status = status
            return meta
    return None


async def tier_impersonate(url: str) -> Meta | None:
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None
    try:
        async with AsyncSession() as session:
            resp = await session.get(
                url, impersonate="chrome", timeout=HTTP_TIMEOUT, allow_redirects=True
            )
    except Exception:
        return None
    if resp.status_code >= 400 or not resp.text:
        return None
    meta = _from_html(resp.text, url)
    meta.tier, meta.http_status = "curl_cffi", resp.status_code
    return meta


async def enrich(url: str, preview: dict | None = None) -> Meta:
    """Walk the ladder until something usable comes back."""
    if preview and (preview.get("title") or preview.get("description")):
        return Meta(
            url=url,
            title=preview.get("title", ""),
            description=preview.get("description", ""),
            image=preview.get("image", ""),
            site_name=preview.get("site_name", ""),
            tier="tg_preview",
            http_status=200,
        )

    limits = httpx.Limits(max_connections=10)
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=HTTP_TIMEOUT, limits=limits, http2=False
    ) as client:
        best = Meta(url=url)

        meta = await tier_site(client, url)
        if meta and meta.ok():
            return meta

        meta = await tier_oembed(client, url)
        if meta and meta.ok():
            return meta

        # tiers 2 and 3 are cheap, so race them instead of chaining
        results = await asyncio.gather(
            tier_chrome(client, url), tier_crawlers(client, url), return_exceptions=True
        )
        for res in results:
            if isinstance(res, Meta):
                if res.ok():
                    return res
                if res.http_status and not best.http_status:
                    best = res

    meta = await tier_impersonate(url)
    if meta and meta.ok():
        return meta
    return best


async def body_text(url: str) -> str:
    """Readable text of the page, for links whose metadata says nothing.

    Deliberately outside the ladder: the ladder stops at </head>, this asks
    for the whole document, so it only runs when the head turned out empty.
    """
    raw = ""
    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession() as session:
            resp = await session.get(
                url, impersonate="chrome", timeout=HTTP_TIMEOUT, allow_redirects=True
            )
        if resp.status_code < 400:
            raw = resp.text
    except Exception:
        raw = ""

    if not raw:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=HTTP_TIMEOUT
            ) as client:
                resp = await client.get(url, headers=CHROME_HEADERS)
            if resp.status_code < 400:
                raw = resp.text
        except httpx.HTTPError:
            return ""

    if not raw or BLOCKED_MARKERS.search(raw[:4000]):
        return ""
    # a link straight to a jpeg decodes into replacement characters, and those
    # would go to the model as if they were text
    if raw[:2000].count("�") > 20 or "<" not in raw[:2000]:
        return ""
    return pagetext.extract(raw)


def final_url(url: str, meta: Meta) -> str:
    """Prefer og:url when the site declares one, unless it is a bare root."""
    declared = meta.fields.get("og:url", "") if meta.fields else ""
    if declared.startswith("http") and not canon.is_bare_root(declared):
        if urlsplit(declared).hostname == urlsplit(url).hostname:
            return declared
    return url
