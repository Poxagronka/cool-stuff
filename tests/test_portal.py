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


def test_the_thing_itself_outranks_a_passing_mention(tmp_path):
    """Someone saying "hoka" about another shoe must not outrank Hoka's own note."""
    vault.write(tmp_path, {
        "url": "https://nike.com/pegasus", "domain": "nike.com", "title": "Nike Pegasus",
        "description": "A road running shoe.", "category": "clothing", "tags": ["running"],
        "shared_at": "2025-01-02T10:00:00",
    }, [{"author": "Sasha", "sent_at": "2025-01-02T10:00:00", "text": "лучше чем hoka"}])
    vault.write(tmp_path, {
        "url": "https://hoka.com/bondi", "domain": "hoka.com", "title": "Hoka Bondi",
        "description": "A cushioned trainer.", "category": "clothing", "tags": ["hoka"],
        "shared_at": "2024-01-02T10:00:00",
    }, [])
    index = portal.Index(tmp_path)
    index.load()
    hits, total = index.search("hoka")
    assert total == 2
    # the nike note is a year newer, and still loses: the word is only an aside there
    assert hits[0].title == "Hoka Bondi"


def test_a_name_is_found_in_either_alphabet(tmp_path):
    """The vault is written in english, and people type brands in Cyrillic."""
    vault.write(tmp_path, {
        "url": "https://hoka.com/bondi", "domain": "hoka.com", "title": "Hoka Bondi",
        "description": "A cushioned trainer.", "category": "clothing", "tags": ["shoes"],
        "shared_at": "2024-01-02T10:00:00",
    }, [])
    index = portal.Index(tmp_path)
    index.load()
    assert index.search("хока")[1] == 1
    assert index.search("hoka")[1] == 1


def test_a_typo_still_finds_the_thing(tmp_path):
    vault.write(tmp_path, {
        "url": "https://arcteryx.com/beta", "domain": "arcteryx.com",
        "title": "Arcteryx Beta", "description": "A hardshell.",
        "category": "clothing", "tags": ["shell"], "shared_at": "2024-05-11T10:00:00",
    }, [])
    index = portal.Index(tmp_path)
    index.load()
    assert index.search("arcteryks")[1] == 1
    # a word that is not a misspelling of anything here is still a miss
    assert index.search("kayak")[1] == 0


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
    assert index.search("", tags=["outdoor"])[1] == 1
    assert index.search("", category="software", tags=["outdoor"])[1] == 0


def test_related_tags_come_from_the_current_results(root):
    """The cloud walks: what is left after picking a tag, minus the tag itself."""
    index = portal.Index(root)
    index.load()
    hits = index.find("", tags=["outdoor"])
    assert dict(index.related(hits, ["outdoor"])) == {"куртка": 1}
    # nothing picked yet: the whole vault's tags are on offer
    assert dict(index.related(index.items, [])) == {"cli": 1, "outdoor": 1, "куртка": 1}


def test_keywords_make_the_language_not_matter(tmp_path):
    """A note written in english, looked up with a russian word, and back."""
    vault.write(tmp_path, {
        "url": "https://arcteryx.com/beta", "domain": "arcteryx.com",
        "title": "Beta Jacket", "description": "A light shell for the shoulder season.",
        "category": "clothing", "tags": ["shell"],
        "keywords": ["jacket", "куртка", "ветровка", "мембрана"],
        "shared_at": "2024-05-11T10:00:00",
    }, [])
    index = portal.Index(tmp_path)
    index.load()
    assert index.search("куртка")[1] == 1
    assert index.search("jacket")[1] == 1


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


def test_a_saved_note_says_so_and_a_chat_note_does_not(tmp_path):
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "a.md").write_text(
        "---\nurl: https://shop.com/a\ndomain: shop.com\ntitle: A\n"
        "shared_at: '2025-02-01'\nsource: saved\n---\n", encoding="utf-8")
    (tmp_path / "links" / "b.md").write_text(
        "---\nurl: https://shop.com/b\ndomain: shop.com\ntitle: B\n"
        "shared_at: '2025-02-01'\n---\n", encoding="utf-8")
    index = portal.Index(tmp_path)
    index.load()
    marked = {i.title: i.public()["saved"] for i in index.items}
    assert marked == {"A": True, "B": False}


def test_a_note_without_url_is_skipped(tmp_path):
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "readme.md").write_text("# просто заметка\n", encoding="utf-8")
    assert portal.Index(tmp_path).load() == 0


def test_the_graph_has_the_lines_as_well_as_the_dots(root):
    """The cloud only needed the tags; a web needs to know which sit together."""
    index = portal.Index(root)
    index.load()
    web = index.graph(index.items, [])
    assert {n["tag"] for n in web["nodes"]} == {"cli", "outdoor", "куртка"}
    # the jacket note carries both of its tags, so they are joined once
    assert web["edges"] == [["outdoor", "куртка", 1]]
    assert web["picked"] == []


def test_a_picked_tag_stays_on_the_web(root):
    """You have to be able to see the path you walked in on, and step back off it."""
    index = portal.Index(root)
    index.load()
    hits = index.find("", tags=["outdoor"])
    web = index.graph(hits, ["outdoor"])
    assert web["picked"] == ["outdoor"]
    assert {n["tag"] for n in web["nodes"]} == {"outdoor", "куртка"}
