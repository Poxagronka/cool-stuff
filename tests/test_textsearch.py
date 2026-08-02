"""What a typed word is allowed to mean, and what it is worth once it means it."""

from tglinks.textsearch import MAX_CACHE, MAX_TEXT, MAX_TOKENS, Terms, tokens


def test_words_are_folded_to_latin():
    # the same brand, typed two ways, has to become one term
    assert tokens("Хока Бонди") == ["hoka", "bondi"]
    assert tokens("Hoka Bondi") == ["hoka", "bondi"]


def test_url_scaffolding_is_not_a_word():
    assert tokens("https://www.arcteryx.com/beta.html") == ["arcteryx", "beta"]


def build(*docs: str) -> Terms:
    terms = Terms()
    for doc in docs:
        terms.add(set(tokens(doc)))
    terms.finish()
    return terms


def test_a_rare_word_counts_for_more_than_a_common_one():
    terms = build(*["jacket"] * 9, "jacket arcteryx")
    assert terms.idf("arcteryx") > terms.idf("jacket")


def test_an_exact_word_beats_the_longer_word_it_starts():
    terms = build("shoe", "shoes", "shoelace")
    found = dict(terms.expand("shoe"))
    assert found["shoe"] == 1.0
    # "shoes" is still offered, just for less: someone typing shoe may want it
    assert 0 < found["shoes"] < 1.0


def test_a_misspelling_still_lands():
    terms = build("arcteryx jacket")
    assert [t for t, _ in terms.expand("arcteryks")] == ["arcteryx"]


def test_guessing_only_happens_when_nothing_matched_outright():
    """A word that exists must not drag its near-spellings in behind it."""
    terms = build("hoka", "hoja")
    assert [t for t, _ in terms.expand("hoka")] == ["hoka"]


def test_a_word_the_vault_has_never_seen_finds_nothing():
    assert build("jacket").expand("quantum") == []


def test_a_wall_of_text_is_read_only_so_far():
    # a novel pasted into the box costs the same as a sentence
    assert len(tokens("word " * 50_000)) == MAX_TOKENS
    assert len(tokens("x" * (MAX_TEXT * 10))) == 1


def test_an_absurd_query_does_not_grow_the_cache_without_end():
    terms = build("jacket arcteryx hoka")
    for n in range(MAX_CACHE + 500):
        terms.expand(f"nonsense{n}")
    assert len(terms.cache) <= MAX_CACHE
    # evicting must not have cost anything a real search relies on
    assert dict(terms.expand("arcteryks")) == {"arcteryx": 0.65}
