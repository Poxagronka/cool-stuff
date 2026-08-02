import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tglinks import canon, db, pipeline, urls, vault  # noqa: E402


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://WWW.Example.com:443/a/b/?utm_source=tg&b=2&a=1",
         "https://example.com/a/b?a=1&b=2"),
        ("https://example.com/path/", "https://example.com/path"),
        ("http://example.com", "http://example.com/"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=abc123&list=PL9&index=2",
         "https://youtube.com/watch?v=abc123"),
        ("https://twitter.com/jack/status/20", "https://x.com/jack/status/20"),
        ("https://www.amazon.de/Some-Long-Product-Name/dp/B08N5WRWNW/ref=sr_1_1?keywords=x",
         "https://amazon.de/dp/B08N5WRWNW"),
        ("https://example.com//double///slash", "https://example.com/double/slash"),
        # telegram marks bare hosts as links, with no scheme at all
        ("butkus.org", "https://butkus.org/"),
        ("www.hydrasite.com/", "https://hydrasite.com/"),
        ("awdee.ru/7-a-m-coffee", "https://awdee.ru/7-a-m-coffee"),
        ("//example.com/x", "https://example.com/x"),
    ],
)
def test_normalise(raw, expected):
    assert canon.normalise(raw) == expected


def test_schemeless_link_keeps_its_domain():
    assert canon.domain("behance.net/gallery/158985815") == "behance.net"
    assert canon.key("suno.ai") == "suno.ai/"


def test_tracking_params_do_not_split_clusters():
    a = "https://shop.com/item?utm_source=tg&fbclid=xyz&id=5"
    b = "https://shop.com/item?id=5"
    assert canon.key(a) == canon.key(b)


def test_unwrap_redirect_wrapper():
    wrapped = "https://l.facebook.com/l.php?u=https%3A%2F%2Fexample.com%2Freal&h=AT0"
    assert canon.normalise(wrapped) == "https://example.com/real"


def test_bare_root_detects_dead_shortener():
    assert canon.is_bare_root("https://www.amazon.com/")
    assert not canon.is_bare_root("https://www.amazon.com/dp/B08N5WRWNW")


def test_entities_utf16_offsets():
    """Cyrillic before the url shifts byte offsets; utf-16 units must be used."""
    text = "смотри https://example.com/x вот"
    entities = [{"type": "url", "offset": 7, "length": 21}]
    assert urls.from_entities(text, entities) == ["https://example.com/x"]


def test_text_link_entity():
    text = "вот тут"
    entities = [{"type": "text_link", "offset": 0, "length": 3, "url": "https://example.com/hidden"}]
    assert urls.from_entities(text, entities) == ["https://example.com/hidden"]


def test_bare_url_fallback_strips_punctuation():
    assert urls.from_entities("см. https://example.com/x.", None) == ["https://example.com/x"]


def test_message_collects_caption_and_preview():
    msg = {
        "text": "https://a.com/1",
        "entities": [{"type": "url", "offset": 0, "length": 15}],
        "link_preview_options": {"url": "https://b.com/2"},
    }
    assert urls.from_message(msg) == ["https://a.com/1", "https://b.com/2"]


def test_dedup_across_messages(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    base = {"chat_id": -1001, "sent_at": "2024-11-03T21:14:00", "author": "Дима", "reply_to": None}

    first = {**base, "msg_id": 1, "text": "вот"}
    pipeline.store_message(conn, first)
    cluster = pipeline.store_link(conn, first, "https://shop.com/item?utm_source=tg&id=5")
    assert cluster is not None

    second = {**base, "msg_id": 2, "text": "уже кидали"}
    pipeline.store_message(conn, second)
    assert pipeline.store_link(conn, second, "https://shop.com/item?id=5") is None

    assert conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM link").fetchone()[0] == 2


def test_context_includes_reply_chain_and_neighbours(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rows = [
        {"chat_id": -1, "msg_id": 1, "sent_at": "2024-11-03T21:10:00", "author": "A",
         "text": "какая куртка?", "reply_to": None},
        {"chat_id": -1, "msg_id": 2, "sent_at": "2024-11-03T21:14:00", "author": "B",
         "text": "вот", "reply_to": 1},
        {"chat_id": -1, "msg_id": 3, "sent_at": "2024-11-03T21:16:00", "author": "A",
         "text": "дорого", "reply_to": None},
        {"chat_id": -1, "msg_id": 4, "sent_at": "2024-11-03T23:00:00", "author": "C",
         "text": "не в тему", "reply_to": None},
    ]
    for row in rows:
        pipeline.store_message(conn, row)
    conn.commit()

    got = {m["msg_id"] for m in pipeline.context_for(conn, -1, 2)}
    assert got == {1, 2, 3}


def test_render_note_has_frontmatter_and_chat_quotes(tmp_path):
    entry = {
        "url": "https://arcteryx.com/beta-lt",
        "domain": "arcteryx.com",
        "title": "Arc'teryx Beta LT",
        "description": "Мембранная куртка на межсезонье.",
        "category": "clothing",
        "tags": ["gore-tex", "куртка"],
        "confidence": "high",
        "shared_by": "Дима",
        "shared_at": "2024-11-03T21:14:00",
        "status": "ok",
        "tg_link": "https://t.me/c/1234567890/2",
        "image": "https://img/x.jpg",
        "price": "€500",
    }
    context = [{"author": "Дима", "sent_at": "2024-11-03T21:14:00", "text": "у меня такая третий год"}]
    text = vault.render(entry, context)

    assert text.startswith("---\n")
    assert "category: clothing" in text
    assert "у меня такая третий год" in text
    assert "Открыть в Telegram" in text
    assert 'price: €500' in text or "price: '€500'" in text


def test_note_path_layout(tmp_path):
    entry = {"domain": "arcteryx.com", "title": "Beta LT", "shared_at": "2024-11-03T21:14:00"}
    path = vault.note_path(tmp_path, entry)
    assert path.parent == tmp_path / "links" / "2024"
    assert path.name.startswith("2024-11-03 arcteryx.com")


def test_note_filename_strips_illegal_chars(tmp_path):
    entry = {"domain": "shop.com", "title": 'A/B: "test" <x>', "shared_at": "2025-01-02T10:00:00"}
    path = vault.note_path(tmp_path, entry)
    assert not set(path.name) & set('<>:"/\\|?*')


def test_tg_link_strips_supergroup_prefix():
    assert vault.tg_link(-1001234567890, 42) == "https://t.me/c/1234567890/42"


def test_tg_link_empty_for_basic_group():
    # a basic group has no t.me/c/ link, so anything built would be dead
    assert vault.tg_link(-4092567497, 1267604) == ""


def test_challenge_page_is_not_valid_metadata():
    from tglinks.enrich import Meta

    assert not Meta(url="u", title="Reddit - Please wait for verification").ok()
    assert not Meta(url="u", title="Just a moment...").ok()
    assert Meta(url="u", title="r/malefashionadvice").ok()


def test_two_links_same_day_do_not_overwrite_each_other(tmp_path):
    # tiktok links carry no metadata, so several in one day share a title
    base = {"domain": "vm.tiktok.com", "title": "TikTok видео", "shared_at": "2024-05-11T10:00:00",
            "category": "video", "tags": [], "shared_by": "sasha"}
    first = vault.write(tmp_path, {**base, "url": "https://vm.tiktok.com/ZMM72U7Dp"}, [])
    second = vault.write(tmp_path, {**base, "url": "https://vm.tiktok.com/ZMM7YVpVh"}, [])
    assert first != second
    assert first.exists() and second.exists()
    assert vault.url_of(first) == "https://vm.tiktok.com/ZMM72U7Dp"
    assert vault.url_of(second) == "https://vm.tiktok.com/ZMM7YVpVh"


def test_rewriting_the_same_link_keeps_its_path(tmp_path):
    entry = {"domain": "vm.tiktok.com", "title": "TikTok видео", "shared_at": "2024-05-11T10:00:00",
             "url": "https://vm.tiktok.com/ZMM72U7Dp", "category": "video", "tags": []}
    assert vault.write(tmp_path, entry, []) == vault.write(tmp_path, entry, [])
