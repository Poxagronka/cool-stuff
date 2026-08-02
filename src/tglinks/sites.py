"""Per-site resolvers for pages the generic ladder cannot read.

Instagram, TikTok, Spotify and the App Store all render from javascript and
give a crawler either nothing or a placeholder. Each of them, though, has one
public endpoint that answers in plain html or json. This module knows those
endpoints; everything else goes through the generic ladder in enrich.
"""

import html as htmllib
import json
import re
from urllib.parse import quote, urlsplit

import httpx

from . import canon

APP_ID = re.compile(r"/id(\d+)")
IG_SHORTCODE = re.compile(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")

CRAWLER = "WhatsApp/2.23.20.0"


def strip(text: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(text or "")).strip()


async def appstore(client: httpx.AsyncClient, url: str, host: str) -> dict | None:
    """App Store pages need javascript; the lookup api answers plain json."""
    if host != "apps.apple.com":
        return None
    found = APP_ID.search(url)
    if not found:
        return None
    resp = await client.get(f"https://itunes.apple.com/lookup?id={found.group(1)}")
    results = resp.json().get("results") or []
    if not results:
        return None
    app = results[0]
    kind = "Game" if app.get("primaryGenreName") == "Games" else "App"
    return {
        "title": app.get("trackName", ""),
        "description": (app.get("description") or "")[:600],
        "image": app.get("artworkUrl512") or app.get("artworkUrl100", ""),
        "site_name": "App Store",
        "price": str(app.get("formattedPrice") or ""),
        "text": f"{kind}, {app.get('primaryGenreName', '')}, "
                f"by {app.get('artistName', '')}",
    }


async def tiktok(client: httpx.AsyncClient, url: str, host: str) -> dict | None:
    """vm.tiktok.com links have to be followed before oembed will take them."""
    if not host.endswith("tiktok.com"):
        return None
    target = url
    if host != "www.tiktok.com":
        resp = await client.get(url)
        target = str(resp.url).split("?")[0]
    resp = await client.get(f"https://www.tiktok.com/oembed?url={quote(target, safe='')}")
    if resp.status_code != 200:
        return None
    data = resp.json()
    caption = strip(data.get("title", ""))
    author = data.get("author_name") or ""
    if not caption and not author:
        return None
    return {
        "title": caption[:90] or f"TikTok, {author}",
        "description": caption,
        "image": data.get("thumbnail_url", ""),
        "site_name": "TikTok",
        "text": f"A TikTok video by {author}. Caption: {caption}",
    }


async def instagram(client: httpx.AsyncClient, url: str, host: str) -> dict | None:
    """The embed page carries the caption and the account, with no login."""
    if not host.endswith("instagram.com"):
        return None
    found = IG_SHORTCODE.search(urlsplit(url).path)
    if not found:
        # a profile link: the handle is all there is, and that is fine
        handle = urlsplit(url).path.strip("/").split("/")[0]
        if not handle:
            return None
        return {
            "title": f"Instagram @{handle}",
            "description": f"The Instagram account @{handle}.",
            "site_name": "Instagram",
            "text": f"The Instagram profile @{handle}",
        }

    resp = await client.get(
        f"https://www.instagram.com/p/{found.group(1)}/embed/captioned/",
        headers={"user-agent": CRAWLER},
    )
    if resp.status_code != 200:
        return None
    page = resp.text
    account = re.search(r'class="UsernameText">([^<]+)<', page)
    caption = re.search(r'class="Caption".*?</a>(.*?)</div>', page, re.S)
    body = strip(re.sub(r"<[^>]+>", " ", caption.group(1))) if caption else ""
    # the embed ends the caption with the like count and a "view comments" tail
    body = re.split(r"\bView all \d+ comments|\d+[.,]?\d*[km]? likes", body)[0].strip()
    handle = account.group(1) if account else ""
    if not body and not handle:
        return None
    return {
        "title": (body[:80] or f"Instagram @{handle}"),
        "description": body[:400] or f"A post by @{handle}.",
        "site_name": "Instagram",
        "text": f"An Instagram post by @{handle}. Caption: {body}",
    }


async def spotify(client: httpx.AsyncClient, url: str, host: str) -> dict | None:
    """Spotify hands a crawler the artist, the year and the track count."""
    if host != "open.spotify.com":
        return None
    resp = await client.get(url, headers={"user-agent": CRAWLER})
    if resp.status_code != 200:
        return None
    props = dict(re.findall(
        r'<meta[^>]+property="og:(title|description|image)"[^>]+content="([^"]*)"',
        resp.text,
    ))
    title = strip(props.get("title", "")).removesuffix(" | Spotify")
    if not title:
        return None
    kind = urlsplit(url).path.strip("/").split("/")[0]
    return {
        "title": title,
        "description": strip(props.get("description", "")),
        "image": props.get("image", ""),
        "site_name": "Spotify",
        "text": f"Spotify, {kind}: {title}. {strip(props.get('description', ''))}",
    }


async def direct_image(client: httpx.AsyncClient, url: str, host: str) -> dict | None:
    """A link straight to a jpeg has no page to read at all."""
    if not re.search(r"\.(jpe?g|png|gif|webp|avif)$", urlsplit(url).path, re.I):
        return None
    return {
        "title": f"An image from {host}",
        "description": "An image with no page around it.",
        "image": url,
        "site_name": host,
        "text": "",
    }


RESOLVERS = (appstore, tiktok, instagram, spotify, direct_image)


async def probe(client: httpx.AsyncClient, url: str) -> dict | None:
    """First resolver that recognises the url and gets an answer, or None."""
    host = canon.domain(url)
    for resolver in RESOLVERS:
        try:
            found = await resolver(client, url, host)
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
            continue
        if found:
            return found
    return None
