"""The portal reads the same notes the vault writes, so it is tested against them."""

import pytest

from tglinks import portal, vault


@pytest.fixture
def root(tmp_path):
    entries = [
        ({"url": "https://arcteryx.com/beta-jacket", "domain": "arcteryx.com",
          "title": "Beta Jacket", "description": "Лёгкая мембранная куртка",
          "category": "clothing", "tags": ["куртка", "outdoor"],
          "shared_by": "Darina", "shared_at": "2024-05-11T10:00:00"},
         [{"author": "Darina", "sent_at": "2024-05-11T10:00:00", "text": "вот эта топ"}]),
        ({"url": "https://ffmpeg.org", "domain": "ffmpeg.org", "title": "FFmpeg",
          "description": "Конвертер видео", "category": "software", "tags": ["cli"],
          "shared_by": "Sasha", "shared_at": "2024-06-01T09:00:00", "status": "dead"}, []),
    ]
    for entry, context in entries:
        vault.write(tmp_path, entry, context)
    return tmp_path


def test_index_reads_every_note(root):
    index = portal.Index(root)
    assert index.load() == 2
    # newest first
    assert index.items[0].domain == "ffmpeg.org"


def test_search_matches_words_in_any_order(root):
    index = portal.Index(root)
    index.load()
    hits, total = index.search("куртка мембранная")
    assert total == 1
    assert hits[0].title == "Beta Jacket"
    # words match as substrings, but every one of them has to be there
    assert index.search("куртка ffmpeg")[1] == 0


def test_any_mode_ranks_instead_of_filtering(root):
    """The model guesses synonyms, so one hit is enough — best match on top."""
    index = portal.Index(root)
    index.load()
    hits, total = index.search("куртк мембран видео", mode="any")
    assert total == 2
    # the jacket matched two words, ffmpeg only "видео" — and it is the newer note
    assert hits[0].title == "Beta Jacket"
    assert index.search("куртк мембран видео")[1] == 0   # strict mode finds nothing


def test_search_covers_the_chat_quotes(root):
    index = portal.Index(root)
    index.load()
    hits, total = index.search("топ")
    assert total == 1
    assert hits[0].quotes == [{"author": "Darina", "at": "10:00", "text": "вот эта топ"}]


def test_filters_narrow_the_result(root):
    index = portal.Index(root)
    index.load()
    assert index.search("", category="software")[1] == 1
    assert index.search("", tag="outdoor")[1] == 1
    assert index.search("", category="software", tag="outdoor")[1] == 0


def test_facets_count_what_is_there(root):
    index = portal.Index(root)
    index.load()
    assert dict(index.categories()) == {"clothing": 1, "software": 1}
    assert dict(index.top_tags()) == {"cli": 1, "outdoor": 1, "куртка": 1}


def test_dead_links_are_flagged_not_hidden(root):
    index = portal.Index(root)
    index.load()
    dead = [i.public() for i in index.items if i.public()["dead"]]
    assert [d["domain"] for d in dead] == ["ffmpeg.org"]


def test_a_note_without_url_is_skipped(tmp_path):
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "readme.md").write_text("# просто заметка\n", encoding="utf-8")
    assert portal.Index(tmp_path).load() == 0
