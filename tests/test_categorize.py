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
