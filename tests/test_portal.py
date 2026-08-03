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


def test_the_top_tags_count_what_is_there(root):
    index = portal.Index(root)
    index.load()
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


def test_the_web_only_draws_the_biggest_tags(tmp_path):
    """Every tag at once was unreadable: the bubbles sat on top of each other."""
    (tmp_path / "links").mkdir()
    for i in range(30):
        (tmp_path / "links" / f"{i}.md").write_text(
            f"---\nurl: https://shop.com/{i}\ndomain: shop.com\ntitle: N{i}\n"
            # every note carries a tag of its own, and the first ten share one
            f"shared_at: '2025-02-01'\ntags: [t{i}{', common' if i < 10 else ''}]\n---\n",
            encoding="utf-8")
    index = portal.Index(tmp_path)
    index.load()
    web = index.graph(index.items, [])
    assert len(web["nodes"]) == 14
    # the one tag ten notes share is the biggest, so it leads
    assert web["nodes"][0] == {"tag": "common", "count": 10}


def test_where_a_link_lives_is_not_a_bubble(tmp_path):
    """"instagram" was the biggest tag in the vault and says nothing at all.

    Neither does "brand", which named a shape and not a subject: sixteen notes
    carried it and every one of them was a shop.
    """
    (tmp_path / "links").mkdir()
    for i in range(6):
        (tmp_path / "links" / f"{i}.md").write_text(
            f"---\nurl: https://x.com/{i}\ndomain: x.com\ntitle: N{i}\n"
            f"shared_at: '2025-02-01'\ntags: [instagram, video, brand, running]\n---\n",
            encoding="utf-8")
    index = portal.Index(tmp_path)
    index.load()
    assert dict(index.top_tags()) == {"running": 6}
    web = index.graph(index.items, [])
    assert [n["tag"] for n in web["nodes"]] == ["running"]
    # picking one from a card does not put it back either
    assert index.graph(index.items, ["instagram"])["nodes"] == [
        {"tag": "running", "count": 6}]
    # the note still carries them: they are context, just not a way in
    assert index.items[0].tags == ["instagram", "video", "brand", "running"]


def test_a_note_carries_its_whole_front_matter_to_the_panel(tmp_path):
    """The panel is the note, so what it shows has to come out of the index."""
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "a.md").write_text(
        "---\nurl: https://shop.com/a\ndomain: shop.com\ntitle: A\n"
        "shared_at: '2025-02-01T10:00:00'\nconfidence: high\n"
        "keywords: [sampler, groovebox]\n---\n", encoding="utf-8")
    index = portal.Index(tmp_path)
    index.load()
    out = index.items[0].public()
    assert out["keywords"] == ["sampler", "groovebox"]
    assert out["confidence"] == "high"
    assert out["at"] == "2025-02-01T10:00:00"
    assert out["source"] == "chat"
    # a keyword still says what the thing is, the way a tag does
    assert index.search("groovebox")[1] == 1


def test_a_vault_that_moved_under_the_process_is_read_again(tmp_path):
    """A `git pull` on the machine left an afternoon of notes served stale."""
    (tmp_path / "links").mkdir()
    note = tmp_path / "links" / "a.md"
    note.write_text(
        "---\nurl: https://a.com/1\ndomain: a.com\ntitle: Первый\n"
        "shared_at: '2025-02-01'\n---\n", encoding="utf-8")
    index = portal.Index(tmp_path)
    index.load()
    assert index.items[0].title == "Первый"
    # nothing changed, and the walk is not repeated within the half minute
    assert index.stale() is False

    note.write_text(
        "---\nurl: https://a.com/1\ndomain: a.com\ntitle: The first one\n"
        "shared_at: '2025-02-01'\n---\n", encoding="utf-8")
    index._checked = 0.0
    assert index.stale() is True
    index.load()
    assert index.items[0].title == "The first one"
    assert index.stale() is False


def test_both_alphabets_come_back_as_one_list(tmp_path):
    """A russian caption and an english note both answer a russian word."""
    vault.write(tmp_path, {
        "url": "https://norda.run/001", "domain": "norda.run", "title": "Norda 001",
        "description": "A trail running shoe.", "category": "clothing",
        "tags": ["running"], "shared_at": "2024-01-02T10:00:00",
    }, [])
    vault.write(tmp_path, {
        "url": "https://example.com/kurtka", "domain": "example.com",
        "title": "Shell Jacket", "description": "A shell.", "category": "clothing",
        "tags": ["jacket"], "shared_at": "2024-01-03T10:00:00",
    }, [{"author": "kolya", "at": "2024-01-03", "text": "бег в дождь"}])

    index = portal.Index(tmp_path)
    index.load()
    # as typed, it reaches only the russian caption
    typed = index.find("бег")
    assert [i.title for i in typed] == ["Shell Jacket"]
    # translated, it reaches only the english note
    english = index.find("running")
    assert [i.title for i in english] == ["Norda 001"]
    # merged, it reaches both, and neither is listed twice
    both = portal.merge_hits(typed, english)
    assert sorted(i.title for i in both) == ["Norda 001", "Shell Jacket"]
    assert len({i.url for i in both}) == 2


def test_merging_keeps_a_note_at_its_best_place(tmp_path):
    a = portal.Item(url="a", title="A")
    b = portal.Item(url="b", title="B")
    c = portal.Item(url="c", title="C")
    # c is last of three as typed and first once translated, so it climbs over
    # b. a and c both lead a run, and the tie goes to the query as it was typed
    assert [i.url for i in portal.merge_hits([a, b, c], [c])] == ["a", "c", "b"]
