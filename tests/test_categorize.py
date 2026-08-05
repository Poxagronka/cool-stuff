"""What the model sends back is not always what the schema asked for."""

from tglinks import categorize


def test_keywords_sent_as_one_string_are_not_thrown_away():
    """Sonnet answers "a,b,c" for an array field, and the note needs those words."""
    out = categorize.coerce({
        "category": "place", "title": "MACRO", "description": "A museum in Rome.",
        "tags": ["museum", "rome"],
        "keywords": "MACRO museum, Rome, contemporary art, gallery",
        "confidence": "high",
    })
    assert out["keywords"] == ["macro museum", "rome", "contemporary art", "gallery"]


def test_a_tag_is_asked_for_as_a_shelf_and_not_as_a_description():
    """A radio station came back `athens-radio`, `online-radio`, `experimental-music`.

    Two of those three are the only link that will ever hold them: the place is
    glued to the kind, and `online-radio` is `radio` said again. The note is
    filed under nothing and the tag web never sees it. `experimental-music` is
    the one worth keeping — narrow is fine, alone is not.
    """
    assert "The FIRST is the plain" in categorize.SYSTEM
    assert "`athens-radio` is one link for" in categorize.SYSTEM
    assert "`online-radio` adds nothing" in categorize.SYSTEM
    assert "`experimental-music`" in categorize.SYSTEM


def test_ten_tags_is_the_same_number_in_the_prompt_and_in_the_schema():
    """Six of them left most tags on a single note, so the web had nothing to draw."""
    assert categorize.TAGS == 10
    assert "tags: ten of them" in categorize.SYSTEM
    assert categorize.SCHEMA["properties"]["tags"]["maxItems"] == 10
    out = categorize.coerce({"category": "misc", "tags": [f"t{i}" for i in range(14)]})
    assert len(out["tags"]) == 10


def test_tags_sent_as_one_string_survive_too():
    out = categorize.coerce({"category": "place", "tags": "museum, #rome"})
    assert out["tags"] == ["museum", "rome"]


def test_a_field_of_the_wrong_shape_is_dropped_quietly():
    out = categorize.coerce({"category": "place", "tags": 7, "keywords": None})
    assert out["tags"] == []
    assert out["keywords"] == []


def test_repeats_are_collapsed_and_the_count_is_capped():
    out = categorize.coerce({"category": "misc", "keywords": ["Jacket", "jacket", *"abcdefghijkl"]})
    assert out["keywords"][0] == "jacket"
    assert len(out["keywords"]) <= 12
    assert len(out["keywords"]) == len(set(out["keywords"]))


def test_an_invented_category_falls_back_to_misc():
    out = categorize.coerce({"category": "spaceship", "confidence": "high"})
    assert out["category"] == "misc"
    assert out["confidence"] == "low"
