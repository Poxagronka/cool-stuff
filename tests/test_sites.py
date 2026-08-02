"""Per-site resolvers, driven by canned responses instead of the live web."""

import asyncio
import json

import httpx

from tglinks import sites

IG_EMBED = """<html><body>
<a class="UsernameText">wild_bear_outdoor</a>
<div class="Caption"><a href="#">wild_bear_outdoor</a>
  Поход выходного дня, палатка и котелок на костре
  <span>3,642 likes</span> View all 44 comments</div>
</body></html>"""

SPOTIFY = """<html><head>
<meta property="og:title" content="Opponent Stims - EP by Clark | Spotify">
<meta property="og:description" content="Clark · EP · 2026 · 7 songs">
<meta property="og:image" content="https://i.scdn.co/x.jpg">
</head><body></body></html>"""


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def run(coro):
    return asyncio.run(coro)


def test_instagram_post_gives_the_caption_and_the_account():
    async def go():
        async with client_for(lambda r: httpx.Response(200, text=IG_EMBED)) as c:
            return await sites.probe(c, "https://instagram.com/p/DY-2O9BgSZQ")

    found = run(go())
    assert "Поход выходного дня" in found["description"]
    assert "wild_bear_outdoor" in found["text"]
    # the like count and the comment tail are not part of the caption
    assert "likes" not in found["description"]
    assert "comments" not in found["description"]


def test_instagram_profile_link_has_no_caption_to_find():
    async def go():
        async with client_for(lambda r: httpx.Response(404)) as c:
            return await sites.probe(c, "https://instagram.com/kawa.club")

    assert run(go())["title"] == "Instagram @kawa.club"


def test_spotify_reads_the_crawler_meta():
    async def go():
        async with client_for(lambda r: httpx.Response(200, text=SPOTIFY)) as c:
            return await sites.probe(c, "https://open.spotify.com/album/3mPAuP")

    found = run(go())
    assert found["title"] == "Opponent Stims - EP by Clark"
    assert found["description"] == "Clark · EP · 2026 · 7 songs"


def test_appstore_uses_the_lookup_api():
    payload = {"results": [{"trackName": "Lab.zip", "description": "Visual research",
                            "primaryGenreName": "Graphics & Design", "artistName": "Lab",
                            "artworkUrl512": "https://a/x.png", "formattedPrice": "Free"}]}

    async def go():
        handler = lambda r: httpx.Response(200, text=json.dumps(payload))  # noqa: E731
        async with client_for(handler) as c:
            return await sites.probe(c, "https://apps.apple.com/id/app/lab-zip/id6738157564")

    found = run(go())
    assert found["title"] == "Lab.zip"
    assert "Lab" in found["text"]


def test_a_direct_image_has_no_page_to_read():
    async def go():
        async with client_for(lambda r: httpx.Response(200)) as c:
            return await sites.probe(c, "https://i.pinimg.com/564x/4b/a1/c0/x.jpg")

    found = run(go())
    assert found["text"] == ""
    assert found["image"].endswith(".jpg")


def test_an_unknown_site_is_left_to_the_generic_ladder():
    async def go():
        async with client_for(lambda r: httpx.Response(200, text="<html></html>")) as c:
            return await sites.probe(c, "https://arcteryx.com/beta-lt")

    assert run(go()) is None
