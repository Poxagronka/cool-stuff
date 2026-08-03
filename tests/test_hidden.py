"""Hiding a card: who may do it, what disappears, and what carries on regardless."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from tglinks import accounts, db, hidden, pipeline, portal, vault, web
from tglinks import app as app_module

PASS = "correct horse battery"
JACKET = "https://arcteryx.com/beta-jacket"


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    accounts.setup(conn)
    hidden.setup(conn)
    return conn


def account(conn, name, admin=False):
    row, _ = accounts.join(conn, accounts.mint(conn, None), name, PASS)
    if admin:
        accounts.set_admin(conn, name)
    return accounts.by_id(conn, row["id"])


@pytest.fixture
def root(tmp_path):
    """Two notes, the same pair the portal tests read."""
    vault.write(tmp_path / "vault", {
        "url": JACKET, "domain": "arcteryx.com", "title": "Beta Jacket",
        "description": "A light shell.", "category": "clothing",
        "tags": ["outdoor", "shell"], "shared_at": "2024-05-11T10:00:00",
    }, [])
    vault.write(tmp_path / "vault", {
        "url": "https://ffmpeg.org", "domain": "ffmpeg.org", "title": "FFmpeg",
        "description": "A video converter.", "category": "software",
        "tags": ["cli"], "shared_at": "2024-06-01T09:00:00",
    }, [])
    return tmp_path / "vault"


# ------------------------------------------------------------------ the flag


def test_admin_is_a_column_and_nobody_starts_with_it(conn):
    ordinary = account(conn, "Darina")
    assert not accounts.is_admin(ordinary)
    boss = account(conn, "poxagronka", admin=True)
    assert accounts.is_admin(boss)
    # granted by name from the machine, and taken back the same way
    assert accounts.set_admin(conn, "poxagronka", False)
    assert not accounts.is_admin(accounts.by_name(conn, "poxagronka"))
    assert accounts.set_admin(conn, "nobody at all") is False


def test_an_older_database_gains_the_column(tmp_path):
    """The flag arrived after the accounts did, so it is added on startup."""
    import sqlite3

    conn = sqlite3.connect(tmp_path / "old.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE account (id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        " key TEXT NOT NULL UNIQUE, invited_by INTEGER, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO account(name, key, created_at) VALUES('Sasha','k','2024-01-01')"
    )
    accounts.setup(conn)
    # the rows that predate the column are ordinary accounts, which is the
    # only answer that fails safe
    assert not accounts.is_admin(accounts.by_name(conn, "Sasha"))


# ------------------------------------------------------------------ the guard


class Ask:
    """Enough of a Request for these handlers: an account and a json body."""

    def __init__(self, who, body=None):
        self.state = SimpleNamespace(account=who)
        self._body = body or {}

    async def json(self) -> dict:
        return self._body


def test_a_normal_account_cannot_hide_anything(conn, root):
    """The button is not the check: the endpoint is asked directly here."""
    app_module.app.state.conn = conn
    app_module.app.state.index = portal.Index(root, hidden.all_urls(conn))
    app_module.app.state.index.load()

    ordinary = account(conn, "Darina")
    with pytest.raises(HTTPException) as refused:
        asyncio.run(app_module.hide_card(Ask(ordinary, {"url": JACKET})))
    assert refused.value.status_code == 403
    assert hidden.all_urls(conn) == set()

    # nobody at all is refused the same way, and so is the unhide beside it
    with pytest.raises(HTTPException):
        asyncio.run(app_module.hide_card(Ask(None, {"url": JACKET})))
    with pytest.raises(HTTPException):
        asyncio.run(app_module.unhide_card(Ask(ordinary)))

    boss = account(conn, "poxagronka", admin=True)
    assert asyncio.run(app_module.hide_card(Ask(boss, {"url": JACKET}))) == {"ok": True}
    assert hidden.all_urls(conn) == {JACKET}
    # and the index the endpoint refreshed no longer carries it
    assert [i.url for i in app_module.app.state.index.items] == ["https://ffmpeg.org"]


def test_a_url_that_is_not_one_is_refused(conn, root):
    app_module.app.state.conn = conn
    app_module.app.state.index = portal.Index(root, hidden.all_urls(conn))
    app_module.app.state.index.load()
    boss = account(conn, "poxagronka", admin=True)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(app_module.hide_card(Ask(boss, {"url": "   "})))
    assert refused.value.status_code == 400


# ------------------------------------------------------------------ the index


def test_a_hidden_url_is_gone_from_everything(root):
    index = portal.Index(root)
    index.load()
    assert index.search("jacket")[1] == 1
    assert len(index.items) == 2

    index.set_hidden({JACKET})
    # out of the results, out of the count, out of the tags and off the web
    assert index.search("jacket")[1] == 0
    assert index.search("")[1] == 1
    assert dict(index.top_tags()) == {"cli": 1}
    assert [n["tag"] for n in index.graph(index.items, [])["nodes"]] == ["cli"]
    # the note is still on disk and the profile page needs its title
    assert [i.title for i in index.buried] == ["Beta Jacket"]

    # unhiding puts it straight back
    index.set_hidden(set())
    assert index.search("jacket")[1] == 1
    assert index.buried == []


def test_the_hidden_set_survives_a_reload(root):
    """The collector reloads the index whenever it writes a note."""
    index = portal.Index(root, {JACKET})
    index.load()
    assert len(index.items) == 1
    index.load()
    assert len(index.items) == 1


def test_hiding_the_same_url_twice_is_not_an_error(conn):
    assert hidden.hide(conn, JACKET, None)
    assert hidden.hide(conn, JACKET, None)
    assert hidden.all_urls(conn) == {JACKET}
    assert len(hidden.rows(conn)) == 1
    assert hidden.unhide(conn, JACKET)
    assert hidden.all_urls(conn) == set()
    # nothing to store, nothing stored
    assert hidden.hide(conn, "") is False
    assert hidden.hide(conn, "x" * (hidden.URL_MAX + 1)) is False


# ------------------------------------------------------------------ the pipeline


def test_a_hidden_link_still_deduplicates_and_still_collects(tmp_path):
    """Hiding is about the site. The collector must not learn about it at all."""
    conn = db.connect(tmp_path / "t.db")
    hidden.setup(conn)
    hidden.hide(conn, "https://shop.com/jacket")

    base = {"chat_id": -1001, "reply_to": None}
    first = {**base, "msg_id": 1, "sent_at": "2024-11-03T21:14:00",
             "author": "Дима", "text": "вот куртка"}
    second = {**base, "msg_id": 9, "sent_at": "2025-02-01T10:00:00",
              "author": "Саша", "text": "взял её, размер мал"}
    for msg in (first, second):
        pipeline.store_message(conn, msg)
        cluster = pipeline.store_link(conn, msg, "https://shop.com/jacket")

    # one note, not two, and the second remark landed on it
    assert conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 1
    assert [m["text"] for m in pipeline.context_for_cluster(conn, cluster)] == [
        "вот куртка", "взял её, размер мал"]


# ------------------------------------------------------------------ the page


def test_the_page_says_whether_to_draw_the_hide_button():
    assert "const ADMIN = true" in web.page(True)
    assert "const ADMIN = false" in web.page()
    # the control is one button on the card, and its mark is drawn rather than
    # typed: an emoji in a source file wears the reader's own font
    assert 'class="hide" data-hide=' in web.page(True)
    assert "<svg" in web.page(True).split("HIDE_SVG = ")[1][:400]
