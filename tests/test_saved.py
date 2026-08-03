"""The scheduled pull of Saved Messages: the gate, the watermark, the session.

No telegram anywhere near this file. The client is a list of messages behind
an async iterator, which is all `collect` ever asks of it, and the pipeline is
replaced by a recorder — what happens to a cluster after it is stored is the
pipeline's own tests' business.
"""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tglinks import db, saved

WHEN = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


class Msg:
    """Enough of a telethon message for the walk: id, date, text, chat."""

    def __init__(self, mid: int, text: str = "", minute: int = 0):
        self.id = mid
        self.message = text
        self.entities = []
        self.reply_to = None
        self.chat_id = 424242
        self.date = WHEN + timedelta(minutes=minute)
        self.web_preview = None


class Me:
    first_name = "Owner"
    username = "owner"


class Fake:
    """A telethon client made of a list. Remembers what it was asked for."""

    def __init__(self, messages: list[Msg], hold: asyncio.Event | None = None):
        self.messages = messages
        self.hold = hold
        self.asked: list[int] = []

    async def get_me(self):
        return Me()

    def iter_messages(self, peer, min_id=0, reverse=False):
        self.asked.append(min_id)
        picked = sorted(
            (m for m in self.messages if m.id > min_id),
            key=lambda m: m.id, reverse=not reverse,
        )

        async def walk():
            for msg in picked:
                if self.hold is not None:
                    await self.hold.wait()
                yield msg

        return walk()


def opener(client: Fake):
    @contextlib.asynccontextmanager
    async def opening():
        yield client

    return opening


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


@pytest.fixture(autouse=True)
def no_pipeline(monkeypatch):
    """Record which clusters were handed on, write no notes."""
    seen: list[int] = []

    async def process_entry(conn, cluster_id, vault_root):
        seen.append(cluster_id)
        conn.execute(
            "UPDATE entry SET status = 'ok' WHERE cluster_id = ?", (cluster_id,)
        )
        conn.commit()
        return Path(vault_root) / f"{cluster_id}.md"

    monkeypatch.setattr(saved.pipeline, "process_entry", process_entry)
    return seen


def pull(conn, client, tmp_path, **kw):
    return asyncio.run(saved.pull(conn, tmp_path, opening=opener(client), **kw))


# the watermark -------------------------------------------------------------


def test_a_run_starts_where_the_last_one_finished(conn, tmp_path, no_pipeline):
    client = Fake([Msg(10, "https://one.example/a"), Msg(11, "https://two.example/b", 1)])
    out = pull(conn, client, tmp_path)
    assert out["seen"] == 2
    assert client.asked == [0]
    assert db.get_state(conn, saved.MARK) == "11"
    assert len(no_pipeline) == 2

    client.messages.append(Msg(12, "https://three.example/c", 2))
    out = pull(conn, client, tmp_path)
    # the second run asks telegram for 11 and up, and only the new one is read
    assert client.asked == [0, 11]
    assert out["seen"] == 1
    assert db.get_state(conn, saved.MARK) == "12"
    assert len(no_pipeline) == 3


def test_the_first_run_does_not_reread_what_the_laptop_already_imported(conn, tmp_path):
    """A fresh state key with rows in the database means a backfill, not zero."""
    conn.execute(
        "INSERT INTO message(chat_id, msg_id, sent_at, text, private)"
        " VALUES(424242, 500, '2026-01-01T00:00:00', 'saved before', 1)"
    )
    conn.commit()
    assert saved.watermark(conn) == 500

    client = Fake([Msg(501, "https://later.example/x")])
    pull(conn, client, tmp_path)
    assert client.asked == [500]


def test_an_interrupted_run_resumes_instead_of_starting_over(conn, tmp_path, no_pipeline):
    """The mark is committed with the rows it stands for, message by message."""

    class Broken(Fake):
        def iter_messages(self, peer, min_id=0, reverse=False):
            self.asked.append(min_id)
            picked = sorted((m for m in self.messages if m.id > min_id), key=lambda m: m.id)

            async def walk():
                for msg in picked:
                    if msg.id == 22:
                        raise RuntimeError("the machine was suspended")
                    yield msg

            return walk()

    client = Broken([Msg(20, "https://a.example/1"), Msg(21, "https://b.example/2", 1),
                     Msg(22, "https://c.example/3", 2)])
    with pytest.raises(RuntimeError):
        pull(conn, client, tmp_path)
    assert db.get_state(conn, saved.MARK) == "21"

    # what the broken run stored is still waiting, and the walk carries on
    good = Fake(client.messages)
    out = pull(conn, good, tmp_path)
    assert good.asked == [21]
    assert out["seen"] == 1
    assert sorted(no_pipeline) == no_pipeline and len(no_pipeline) == 3


def test_a_message_with_no_link_still_moves_the_mark(conn, tmp_path, no_pipeline):
    client = Fake([Msg(30, "just a note to self"), Msg(31, "")])
    out = pull(conn, client, tmp_path)
    assert out["seen"] == 2
    assert db.get_state(conn, saved.MARK) == "31"
    assert no_pipeline == []
    # the wordless one is not stored, the one with text is: it may turn out to
    # be the sentence explaining a link saved a minute later
    kept = conn.execute("SELECT msg_id FROM message").fetchall()
    assert [r["msg_id"] for r in kept] == [30]


def test_everything_pulled_here_is_marked_private(conn, tmp_path):
    """The triage gate is keyed off that flag, and it is the only gate there is."""
    pull(conn, Fake([Msg(40, "https://shop.example/thing")]), tmp_path)
    row = conn.execute("SELECT private FROM link").fetchone()
    assert row["private"] == 1
    assert conn.execute("SELECT private FROM message").fetchone()["private"] == 1


def test_a_cluster_left_behind_by_an_earlier_run_is_picked_up(conn, tmp_path, no_pipeline):
    """The mark has already walked past it, so only `waiting` can find it."""
    pull(conn, Fake([Msg(50, "https://left.example/over")]), tmp_path)
    conn.execute("UPDATE entry SET status = 'new'")
    conn.commit()
    no_pipeline.clear()
    pull(conn, Fake([Msg(50, "https://left.example/over")]), tmp_path)
    assert len(no_pipeline) == 1


# one run at a time ---------------------------------------------------------


def test_a_second_trigger_while_one_runs_is_a_no_op(conn, tmp_path, no_pipeline):
    """Not a queue: the run in flight walks to the newest message there is."""
    hold = asyncio.Event()
    client = Fake([Msg(60, "https://slow.example/a")], hold=hold)

    async def both():
        first = asyncio.create_task(
            saved.pull(conn, tmp_path, opening=opener(client))
        )
        await asyncio.sleep(0)      # let it take the lock and reach the walk
        second = await saved.pull(conn, tmp_path, opening=opener(Fake([Msg(61, "x")])))
        hold.set()
        return await first, second

    first, second = asyncio.run(both())
    assert second == {"ran": False, "why": "already running", "seen": 0, "notes": []}
    assert first["ran"] and first["seen"] == 1
    # the refused trigger touched nothing: its message never reached the walk
    assert db.get_state(conn, saved.MARK) == "60"


def test_the_lock_is_released_when_a_run_blows_up(conn, tmp_path):
    @contextlib.asynccontextmanager
    async def broken():
        raise saved.SessionRevoked("gone")
        yield

    with pytest.raises(saved.SessionRevoked):
        asyncio.run(saved.pull(conn, tmp_path, opening=broken))
    assert not saved._running.locked()
    out = pull(conn, Fake([Msg(70, "https://after.example/x")]), tmp_path)
    assert out["ran"]


# the session, and when a run is due ----------------------------------------


def test_a_missing_session_file_is_loud(monkeypatch, tmp_path):
    monkeypatch.setattr(saved, "TG_API_ID", 12345)
    monkeypatch.setattr(saved, "TG_API_HASH", "hash")
    monkeypatch.setattr(saved, "TG_SESSION", tmp_path / "nowhere.session")

    async def open_it():
        async with saved.session():
            pass

    with pytest.raises(saved.SessionMissing) as gone:
        asyncio.run(open_it())
    assert "SETUP.md" in str(gone.value)


def test_a_failed_run_still_paces_the_next_attempt(conn, tmp_path):
    @contextlib.asynccontextmanager
    async def broken():
        raise saved.SessionMissing("no file")
        yield

    with pytest.raises(saved.SessionMissing):
        asyncio.run(saved.pull(conn, tmp_path, opening=broken))
    assert db.get_state(conn, saved.RAN)
    assert not saved.due(conn)


def test_due_waits_out_the_interval(conn, monkeypatch):
    monkeypatch.setattr(saved, "SAVED_EVERY_MINUTES", 180)
    assert saved.due(conn)
    db.set_state(conn, saved.RAN, WHEN.isoformat(timespec="seconds"))
    assert not saved.due(conn, WHEN + timedelta(minutes=179))
    assert saved.due(conn, WHEN + timedelta(minutes=181))


def test_a_zero_interval_turns_the_schedule_off(conn, monkeypatch):
    """The trigger route still works; nothing fires on a wake any more."""
    monkeypatch.setattr(saved, "SAVED_EVERY_MINUTES", 0)
    assert not saved.due(conn)
