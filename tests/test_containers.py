"""Container pages, driven by answers recorded off the live sites once."""

import asyncio
import json
from pathlib import Path

import httpx

from tglinks import containers, pipeline

FIXTURES = Path(__file__).parent / "fixtures"
NOTION_CHUNK = json.loads((FIXTURES / "notion_loadpagechunk.json").read_text())
WISHLIST = (FIXTURES / "mywishlist_wishlist.html").read_text()
CLICKOUTS = {
    p.stem.rsplit("_", 1)[-1]: p.read_text()
    for p in FIXTURES.glob("mywishlist_clickout_*.html")
}

NOTION_URL = "https://ddf35.notion.site/wishlist-ffb5e75433ed40f99ee549a7def3b1a7"
WISHLIST_URL = "https://mywishlist.online/w/cruuoi/hannas-wishlist"


def run(coro):
    return asyncio.run(coro)


def read(handler, url):
    """Every reader in turn, with the web replaced by canned answers."""

    async def go():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ) as client:
            host = url.split("/")[2].removeprefix("www.")
            for reader in containers.READERS:
                found = await reader(client, url, host)
                if found:
                    return found
        return []

    return run(go())


def wishlist_handler(request):
    if request.url.path.startswith("/w/"):
        return httpx.Response(200, text=WISHLIST)
    return httpx.Response(200, text=CLICKOUTS[request.url.path.rsplit("/", 1)[-1]])


def test_the_page_id_is_the_uuid_the_api_will_accept():
    assert containers._page_id(NOTION_URL) == "ffb5e754-33ed-40f9-9ee5-49a7def3b1a7"
    # the same page linked with the uuid already spelled out
    dashed = "https://ddf35.notion.site/ffb5e754-33ed-40f9-9ee5-49a7def3b1a7"
    assert containers._page_id(dashed) == "ffb5e754-33ed-40f9-9ee5-49a7def3b1a7"
    assert containers._page_id("https://ddf35.notion.site/") is None


def test_notion_links_come_out_of_the_record_map():
    def handler(request):
        assert request.url.path == "/api/v3/loadPageChunk"
        assert json.loads(request.content)["pageId"] == "ffb5e754-33ed-40f9-9ee5-49a7def3b1a7"
        return httpx.Response(200, json=NOTION_CHUNK)

    found = read(handler, NOTION_URL)
    # one link written into a heading, one written into a bullet
    assert "https://softrock.pt/en/rocks/goodpiece-atomos-smooth-eng" in found
    assert "https://www.gagebeasleyshop.com/en-de/products/orchid-mantis" in found
    # the same google sheet is linked from two blocks and is one link here
    assert sum(1 for u in found if "docs.google.com" in u) == 1
    # `attachment:...` is how a block points at a file, and it is not a link
    assert all(u.startswith("https://") for u in found)


def test_notion_keeps_its_own_addresses_to_itself():
    chunk = {"recordMap": {"block": {
        "a": {"value": {"value": {
            "type": "bookmark",
            "format": {"bookmark_url": "https://arcteryx.com/beta-lt"},
        }}},
        "b": {"value": {"value": {
            "type": "text",
            "properties": {"title": [
                ["another page", [["a", "https://ddf35.notion.site/sub-page"]]],
                ["notion help", [["a", "https://www.notion.so/help"]]],
            ]},
        }}},
        "c": {"value": {"value": {
            "type": "video",
            "format": {"display_source": "https://www.youtube.com/watch?v=s1eWe2vy184"},
        }}},
        # an image pasted into the page: notion links it by its storage
        # address, and it is not one of the things on the wishlist
        "d": {"value": {"value": {
            "type": "image",
            "format": {"display_source":
                       "https://prod-files-secure.s3.us-west-2.amazonaws.com/e0a1/b0dc.jpg"},
        }}},
    }}}
    assert containers.links_in_chunk(chunk) == [
        "https://arcteryx.com/beta-lt",
        "https://www.youtube.com/watch?v=s1eWe2vy184",
    ]


def test_a_block_stored_one_level_shallower_is_still_a_block():
    chunk = {"recordMap": {"block": {"a": {"value": {
        "type": "bookmark", "format": {"bookmark_url": "https://standartmag.com/products/x"},
    }}}}}
    assert containers.links_in_chunk(chunk) == ["https://standartmag.com/products/x"]


def test_a_wishlist_is_its_items_and_not_its_page():
    found = read(wishlist_handler, WISHLIST_URL)
    assert found == [
        "https://satisfyrunning.com/products/auralite-uv-long-tee-moon-rock",
        "https://satisfyrunning.com/products/mothtech-muscle-tee-faded-black-women",
        "https://www.gnuhr.com/products/warp-short-short?variant=6",
    ]
    # nothing that leaves here still belongs to the wishlist site
    assert not any("mywishlist.online" in u for u in found)


def test_a_wishlist_item_whose_stub_will_not_open_is_dropped():
    def handler(request):
        if request.url.path.startswith("/w/"):
            return httpx.Response(200, text=WISHLIST)
        if request.url.path.endswith("29711264"):
            return httpx.Response(502)
        return httpx.Response(200, text=CLICKOUTS[request.url.path.rsplit("/", 1)[-1]])

    assert len(read(handler, WISHLIST_URL)) == 2


def test_a_wishlist_page_with_no_items_is_not_a_container():
    def handler(request):
        return httpx.Response(200, text="<html><body>nothing here</body></html>")

    assert read(handler, WISHLIST_URL) == []


def test_an_ordinary_link_is_nobody_s_container():
    async def go():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html></html>"))
        ) as client:
            return [
                await reader(client, "https://arcteryx.com/beta-lt", "arcteryx.com")
                for reader in containers.READERS
            ]

    assert run(go()) == [None, None]


def test_widen_puts_the_inside_of_a_container_in_place_of_it(monkeypatch):
    async def fake(url):
        return ["https://gnuhr.com/a", "https://miista.com/b"] if url == WISHLIST_URL else []

    monkeypatch.setattr(containers, "expand", fake)
    found = run(pipeline.widen(["https://shop.com/jacket", WISHLIST_URL, "https://gnuhr.com/a"]))
    # the container is gone, and the item the chat also posted is one link
    assert found == ["https://shop.com/jacket", "https://gnuhr.com/a", "https://miista.com/b"]
