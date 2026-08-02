import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill  # noqa: E402

from tglinks import app as app_module  # noqa: E402
from tglinks import canon, categorize, db, enrich, pipeline, triage, urls, vault  # noqa: E402


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
    # the same thing again is the same note, rewritten with what was said now
    assert pipeline.store_link(conn, second, "https://shop.com/item?id=5") == cluster

    assert conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM link").fetchone()[0] == 2
    assert conn.execute("SELECT status FROM entry").fetchone()[0] == "new"
    # the very same message twice over changes nothing at all
    assert pipeline.store_link(conn, second, "https://shop.com/item?id=5") is None


def test_a_second_mention_brings_its_own_context(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    first = {"chat_id": -1001, "msg_id": 1, "sent_at": "2024-11-03T21:14:00",
             "author": "Дима", "text": "вот куртка", "reply_to": None}
    second = {"chat_id": -1001, "msg_id": 9, "sent_at": "2025-02-01T10:00:00",
              "author": "Саша", "text": "взял её, размер мал", "reply_to": None}
    for msg in (first, second):
        pipeline.store_message(conn, msg)
        cluster = pipeline.store_link(conn, msg, "https://shop.com/jacket")

    said = [m["text"] for m in pipeline.context_for_cluster(conn, cluster)]
    assert said == ["вот куртка", "взял её, размер мал"]


def test_a_link_only_ever_saved_privately_is_marked_as_such(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    saved = {"chat_id": 777, "msg_id": 1, "sent_at": "2025-02-01T10:00:00",
             "author": "Sasha", "text": "", "reply_to": None, "private": True}
    pipeline.store_message(conn, saved)
    cluster = pipeline.store_link(conn, saved, "https://shop.com/jacket")
    assert pipeline.private_only(conn, cluster)

    # the group saw it too, so there is nothing left to hide
    public = {"chat_id": -1001, "msg_id": 2, "sent_at": "2025-02-02T10:00:00",
              "author": "Дима", "text": "видели?", "reply_to": None}
    pipeline.store_message(conn, public)
    pipeline.store_link(conn, public, "https://shop.com/jacket")
    assert not pipeline.private_only(conn, cluster)


def saved_cluster(conn, text="надо купить"):
    saved = {"chat_id": 777, "msg_id": 1, "sent_at": "2025-02-01T10:00:00",
             "author": "Sasha", "text": text, "reply_to": None, "private": True}
    pipeline.store_message(conn, saved)
    return pipeline.store_link(conn, saved, "https://shop.com/jacket")


def stub_enrichment(monkeypatch, title="Jacket", resolved="", seen=None):
    async def enriched(url, preview=None):
        return enrich.Meta(url=url, title="Jacket", description="A warm jacket for winter.",
                           tier="html", http_status=200)

    async def sorted_out(url, meta, context, chain=""):
        if seen is not None:
            seen.extend(m.get("text") or "" for m in context)
        return {"title": title, "description": "A warm jacket.", "category": "clothing",
                "tags": ["jacket"], "keywords": ["jacket", "warm"], "confidence": "high"}

    async def no_body(url):
        return ""

    monkeypatch.setattr(enrich, "enrich", enriched)
    monkeypatch.setattr(enrich, "body_text", no_body)
    monkeypatch.setattr(categorize, "classify", sorted_out)
    if resolved:
        monkeypatch.setattr(enrich, "final_url", lambda url, meta: resolved)


def test_a_private_link_the_gate_refuses_never_becomes_a_note(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    cluster = saved_cluster(conn)
    stub_enrichment(monkeypatch)

    async def refuse(url, meta, note, chain):
        return False, "an errand"

    monkeypatch.setattr(triage, "keep", refuse)
    path = asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))

    assert path is None
    assert conn.execute("SELECT status FROM entry").fetchone()[0] == "skipped"
    assert not list((tmp_path / "vault").rglob("*.md"))


def test_a_saved_link_that_passes_is_published_and_marked_as_saved(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    cluster = saved_cluster(conn, text="давно хотел такую")
    stub_enrichment(monkeypatch)

    async def allow(url, meta, note, chain):
        # the gate reads the note too, because the note gets published as well
        assert "давно хотел такую" in note
        return True, "a jacket"

    monkeypatch.setattr(triage, "keep", allow)
    path = asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))

    assert path is not None
    written = path.read_text(encoding="utf-8")
    assert "source: saved" in written
    assert "## Saved to myself" in written
    assert "давно хотел такую" in written


def test_a_link_the_group_also_posted_skips_the_gate(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    cluster = saved_cluster(conn)
    public = {"chat_id": -1001, "msg_id": 2, "sent_at": "2025-02-02T10:00:00",
              "author": "Дима", "text": "отличная куртка", "reply_to": None}
    pipeline.store_message(conn, public)
    pipeline.store_link(conn, public, "https://shop.com/jacket")
    stub_enrichment(monkeypatch)

    async def never(url, meta, note, chain):
        raise AssertionError("the gate is only for what nobody else has seen")

    monkeypatch.setattr(triage, "keep", never)
    path = asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))

    assert path is not None
    written = path.read_text(encoding="utf-8")
    assert "отличная куртка" in written
    assert "source: chat" in written


def test_what_was_said_privately_stays_out_of_a_note_the_group_reopened(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    cluster = saved_cluster(conn, text="купить после приёма у онколога")
    public = {"chat_id": -1001, "msg_id": 2, "sent_at": "2025-02-02T10:00:00",
              "author": "Дима", "text": "отличная куртка", "reply_to": None}
    pipeline.store_message(conn, public)
    pipeline.store_link(conn, public, "https://shop.com/jacket")
    shown = []
    stub_enrichment(monkeypatch, seen=shown)

    async def never(url, meta, note, chain):
        raise AssertionError("the gate is only for what nobody else has seen")

    monkeypatch.setattr(triage, "keep", never)
    path = asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))

    written = path.read_text(encoding="utf-8")
    assert "отличная куртка" in written
    # the group made the link public, not the sentence the owner wrote beside it
    assert "онколога" not in written
    assert shown == ["отличная куртка"]


def test_a_saved_link_on_a_private_host_is_never_even_fetched(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    saved = {"chat_id": 777, "msg_id": 1, "sent_at": "2025-02-01T10:00:00",
             "author": "Sasha", "text": "перевести", "reply_to": None, "private": True}
    pipeline.store_message(conn, saved)
    cluster = pipeline.store_link(conn, saved, "https://revolut.com/app/transfer")
    stub_enrichment(monkeypatch)

    async def never(url, preview=None):
        raise AssertionError("a link the string check already refuses is not worth a request")

    monkeypatch.setattr(enrich, "enrich", never)
    path = asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))

    assert path is None
    assert conn.execute("SELECT status FROM entry").fetchone()[0] == "skipped"


def test_the_group_posting_a_link_reopens_what_the_gate_refused(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    cluster = saved_cluster(conn)
    stub_enrichment(monkeypatch)

    async def refuse(url, meta, note, chain):
        return False, "an errand"

    monkeypatch.setattr(triage, "keep", refuse)
    asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))
    assert conn.execute("SELECT status FROM entry").fetchone()[0] == "skipped"

    public = {"chat_id": -1001, "msg_id": 2, "sent_at": "2025-02-02T10:00:00",
              "author": "Дима", "text": "отличная куртка", "reply_to": None}
    pipeline.store_message(conn, public)
    assert pipeline.store_link(conn, public, "https://shop.com/jacket") == cluster
    # backfill only picks up 'new', so a refusal that is no longer justified
    # has to put the entry back in the queue
    assert conn.execute("SELECT status FROM entry").fetchone()[0] == "new"

    async def never(url, meta, note, chain):
        raise AssertionError("nothing private is left to guard")

    monkeypatch.setattr(triage, "keep", never)
    path = asyncio.run(pipeline.process_entry(conn, cluster, tmp_path / "vault"))
    assert path is not None


def test_a_saved_message_dumped_through_the_plain_chat_flag_is_still_private(tmp_path):
    class Peer:
        def __init__(self, ident):
            self.id = ident

    class Client:
        async def get_me(self):
            return Peer(4242)

        async def get_entity(self, chat):
            # every spelling of yourself resolves to the same user
            return Peer(4242) if chat in ("me", "@sasha", 4242) else Peer(-1001)

    client = Client()
    assert asyncio.run(backfill.is_self(client, "me"))
    assert asyncio.run(backfill.is_self(client, "@sasha"))
    assert asyncio.run(backfill.is_self(client, 4242))
    assert not asyncio.run(backfill.is_self(client, -1001))


def test_two_links_that_resolve_to_one_page_become_one_note(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    vault_root = tmp_path / "vault"
    base = {"chat_id": -1001, "sent_at": "2025-02-01T10:00:00", "author": "Дима",
            "reply_to": None}
    long = {**base, "msg_id": 1, "text": "вот куртка"}
    short = {**base, "msg_id": 2, "text": "и она же"}
    for msg in (long, short):
        pipeline.store_message(conn, msg)
    first = pipeline.store_link(conn, long, "https://shop.com/item")
    second = pipeline.store_link(conn, short, "https://bit.ly/x")
    assert first != second

    stub_enrichment(monkeypatch, resolved="https://shop.com/item")
    one = asyncio.run(pipeline.process_entry(conn, first, vault_root))
    two = asyncio.run(pipeline.process_entry(conn, second, vault_root))

    assert one == two
    assert len(list(vault_root.rglob("*.md"))) == 1
    rows = conn.execute("SELECT cluster_id, domain FROM entry").fetchall()
    assert [(r["cluster_id"], r["domain"]) for r in rows] == [(first, "shop.com")]
    # both sightings hang off the surviving cluster, none is orphaned
    assert conn.execute(
        "SELECT COUNT(*) FROM link WHERE cluster_id = ?", (first,)
    ).fetchone()[0] == 2


def test_renaming_a_note_takes_the_old_file_with_it(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    vault_root = tmp_path / "vault"
    msg = {"chat_id": -1001, "msg_id": 1, "sent_at": "2025-02-01T10:00:00",
           "author": "Дима", "text": "вот куртка", "reply_to": None}
    pipeline.store_message(conn, msg)
    cluster = pipeline.store_link(conn, msg, "https://shop.com/jacket")

    stub_enrichment(monkeypatch, title="Old Name")
    old = asyncio.run(pipeline.process_entry(conn, cluster, vault_root))
    assert old.name == "Old Name.md"

    later = {"chat_id": -1001, "msg_id": 2, "sent_at": "2025-03-01T10:00:00",
             "author": "Саша", "text": "взял", "reply_to": None}
    pipeline.store_message(conn, later)
    pipeline.store_link(conn, later, "https://shop.com/jacket")
    stub_enrichment(monkeypatch, title="New Name")
    new = asyncio.run(pipeline.process_entry(conn, cluster, vault_root))

    assert new.name == "New Name.md"
    # the old file would keep answering searches with what it used to say
    assert not old.exists()
    assert [p.name for p in vault_root.rglob("*.md")] == ["New Name.md"]


def test_a_note_that_is_not_ours_is_left_where_it_is(tmp_path):
    entry = {"domain": "shop.com", "title": "Jacket", "shared_at": "2025-02-01T10:00:00",
             "url": "https://shop.com/a", "category": "clothing", "tags": []}
    path = vault.write(tmp_path, entry, [])
    rel = str(path.relative_to(tmp_path))

    # two links can share a stem, so the name is no proof of who owns the file
    assert not vault.retire(tmp_path, rel, "https://shop.com/b")
    assert path.exists()
    assert vault.retire(tmp_path, rel, "https://shop.com/a")
    assert not path.exists()


def test_the_note_just_written_is_never_the_one_retired(tmp_path):
    entry = {"domain": "gnuhr.com", "title": "GNUHR", "shared_at": "2025-02-01T10:00:00",
             "url": "https://gnuhr.com/", "category": "clothing", "tags": []}
    path = vault.write(tmp_path, entry, [])

    # where the filesystem folds case, the two spellings are one file:
    # the url inside matches, so the old name would delete the new note
    assert not vault.retire(tmp_path, str(path.relative_to(tmp_path)),
                            entry["url"], keeping=path)
    assert path.exists()


def test_a_title_that_only_changed_case_moves_the_file(tmp_path):
    entry = {"domain": "gnuhr.com", "title": "Gnuhr", "shared_at": "2025-02-01T10:00:00",
             "url": "https://gnuhr.com/", "category": "clothing", "tags": []}
    first = vault.write(tmp_path, entry, [])

    entry["title"] = "GNUHR"
    second = vault.write(tmp_path, entry, [])

    # the database records the new spelling, so that is what has to be on disk
    assert second.name == "GNUHR.md"
    assert [p.name for p in second.parent.iterdir()] == ["GNUHR.md"]
    assert first.name == "Gnuhr.md"


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


def test_context_stops_at_the_next_link(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rows = [
        {"chat_id": -1, "msg_id": 1, "sent_at": "2024-11-03T21:10:00", "author": "A",
         "text": "https://valentinmarco.com крутится", "reply_to": None},
        {"chat_id": -1, "msg_id": 2, "sent_at": "2024-11-03T21:11:00", "author": "A",
         "text": "он у меня пару лет", "reply_to": None},
        {"chat_id": -1, "msg_id": 3, "sent_at": "2024-11-03T21:12:00", "author": "A",
         "text": "https://hoka.com/jacket", "reply_to": None},
        {"chat_id": -1, "msg_id": 4, "sent_at": "2024-11-03T21:13:00", "author": "B",
         "text": "красивая", "reply_to": None},
        {"chat_id": -1, "msg_id": 5, "sent_at": "2024-11-03T21:14:00", "author": "B",
         "text": "https://arcteryx.com ну или эта", "reply_to": None},
        {"chat_id": -1, "msg_id": 6, "sent_at": "2024-11-03T21:15:00", "author": "A",
         "text": "тоже вариант", "reply_to": None},
    ]
    for row in rows:
        pipeline.store_message(conn, row)
    conn.commit()

    # the talk about valentinmarco and about arcteryx belongs to those links
    got = {m["msg_id"] for m in pipeline.context_for(conn, -1, 3)}
    assert got == {2, 3, 4}


def test_context_stops_at_a_link_hiding_behind_its_own_words(tmp_path):
    """Telegram lets a url sit behind display text, and "вот эта" is a link."""
    conn = db.connect(tmp_path / "t.db")
    rows = [
        {"chat_id": -1, "msg_id": 1, "sent_at": "2024-11-03T21:10:00", "author": "A",
         "text": "а что за куртка", "reply_to": None},
        {"chat_id": -1, "msg_id": 2, "sent_at": "2024-11-03T21:11:00", "author": "B",
         "text": "вот эта", "reply_to": None},
        {"chat_id": -1, "msg_id": 3, "sent_at": "2024-11-03T21:12:00", "author": "A",
         "text": "https://hoka.com/jacket", "reply_to": None},
    ]
    for row in rows:
        pipeline.store_message(conn, row)
    pipeline.store_link(conn, rows[1], "https://valentinmarco.com/coat")
    pipeline.store_link(conn, rows[2], "https://hoka.com/jacket")
    conn.commit()

    # nothing in the text of message 2 says so, but the walk has to stop there
    assert {m["msg_id"] for m in pipeline.context_for(conn, -1, 3)} == {3}
    # and the question it answers is still context for the link it does carry
    assert {m["msg_id"] for m in pipeline.context_for(conn, -1, 2)} == {1, 2}


def test_a_message_with_no_link_is_kept_for_the_link_that_comes_after_it(tmp_path):
    """"Runs two sizes small" is the whole note, and it carries no url."""
    conn = db.connect(tmp_path / "t.db")
    app_module.app.state.conn = conn
    when = datetime(2024, 11, 3, 21, 10, tzinfo=timezone.utc)
    asyncio.run(app_module.handle({
        "message_id": 1,
        "chat": {"id": -1},
        "date": int(when.timestamp()),
        "from": {"first_name": "A"},
        "text": "runs two sizes small",
    }))

    later = {"chat_id": -1, "msg_id": 2, "author": "B", "reply_to": None,
             "sent_at": (when + timedelta(minutes=1)).isoformat(timespec="seconds"),
             "text": "https://hoka.com/jacket"}
    pipeline.store_message(conn, later)
    pipeline.store_link(conn, later, "https://hoka.com/jacket")
    conn.commit()

    assert {m["msg_id"] for m in pipeline.context_for(conn, -1, 2)} == {1, 2}


def test_the_dump_keeps_the_talk_around_a_link_and_leaves_the_rest(tmp_path):
    """The history comes back newest first, both sides have to survive that."""

    start = datetime(2024, 11, 3, 21, 0, tzinfo=timezone.utc)

    class MessageEntityTextUrl:
        """Telethon names the class, and the dump reads links off the name."""

        def __init__(self, url):
            self.url = url

    class Msg:
        def __init__(self, mid, minute, text, reply_to=None):
            self.id = mid
            self.date = start + timedelta(minutes=minute)
            self.message = text
            self.entities = None
            self.web_preview = None
            self.reply_to = SimpleNamespace(reply_to_msg_id=reply_to) if reply_to else None

    history = [
        Msg(1, 0, "не в тему"),
        Msg(2, 20, "какая куртка?"),
        Msg(3, 57, "давно ищу"),
        Msg(4, 58, "вот эта", reply_to=2),
        Msg(5, 59, "runs two sizes small"),
        Msg(6, 90, "погода"),
    ]
    history[3].entities = [MessageEntityTextUrl("https://hoka.com/jacket")]

    class Client:
        def iter_messages(self, chat, limit=None):
            async def newest_first():
                for msg in sorted(history, key=lambda m: m.id, reverse=True):
                    yield msg
            return newest_first()

    async def collect():
        return [(msg.id, found) async for msg, found in
                backfill.iter_in_scope(Client(), "chat", None)]

    got = dict(asyncio.run(collect()))
    # 3 and 5 are the two sides of the window, 2 is what the link replies to,
    # and the two far ends are talk about something else entirely
    assert set(got) == {2, 3, 4, 5}
    assert got[4] == ["https://hoka.com/jacket"]
    assert all(not found for mid, found in got.items() if mid != 4)


def test_quotes_lose_their_urls():
    """A message that is a list of links must not become a wall of urls."""
    said = vault.speech("clo\nhttps://instagram.com/uvu\nhttps://instagram.com/nordarun")
    assert said == "clo"
    assert vault.speech("вот эта топ https://shop.com/x") == "вот эта топ"
    # a message that was nothing but links has nothing left to quote
    assert vault.speech("https://instagram.com/uvu") == ""


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
    assert "Open in Telegram" in text
    assert 'price: €500' in text or "price: '€500'" in text


def test_note_path_layout(tmp_path):
    entry = {"domain": "arcteryx.com", "title": "Beta LT", "shared_at": "2024-11-03T21:14:00"}
    path = vault.note_path(tmp_path, entry)
    assert path.parent == tmp_path / "links" / "2024"
    assert path.name == "Beta LT.md"


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


def test_page_text_drops_the_furniture():
    from tglinks import pagetext
    html = """<html><body>
      <nav>Главная Каталог Корзина</nav>
      <header><button>Купить</button></header>
      <main><h1>Куртка Beta LT</h1>
        <p>Лёгкая мембранная куртка из Gore-Tex, рассчитана на дождь и ветер в горах.</p>
        <p>Вес 340 грамм, три слоя, капюшон под каску, полностью проклеенные швы.</p>
      </main>
      <footer>Доставка Оплата Контакты</footer>
      <script>var tracking = 1;</script></body></html>"""
    text = pagetext.readable(html)
    assert "мембранная куртка" in text
    assert "tracking" not in text
    assert "Корзина" not in text and "Доставка" not in text


def test_page_text_is_capped():
    from tglinks import pagetext
    html = "<html><body><main>" + "<p>довольно длинное предложение про куртку</p>" * 500
    assert len(pagetext.readable(html, limit=500)) <= 500
