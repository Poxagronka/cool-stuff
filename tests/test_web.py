"""The page is assembled by string replacement, which fails quietly."""

import re

from tglinks import web

# a placeholder that never got replaced, e.g. {sheet_js}. the template is full
# of javascript, so a `${name}` of its own is skipped by the lookbehind
LEFTOVER = re.compile(r"(?<!\$)\{[a-z_]+\}")


def test_every_placeholder_was_filled_in():
    assert LEFTOVER.search(web.PAGE) is None


def test_the_page_carries_the_note_panel():
    assert 'id="veil"' in web.PAGE
    assert "const Sheet" in web.PAGE
    # the card opens the note, and only the small link leaves for the site
    assert 'data-open="${esc(it.url)}"' in web.PAGE


def test_the_category_strip_is_gone():
    """It duplicated the tag web and ate a row of the page above the fold."""
    assert 'id="cats"' not in web.PAGE
    assert "data-category" not in web.PAGE


def test_every_tag_chip_is_a_real_button():
    """As a span it was unreachable: the keyboard could not pick a tag at all.

    Every place that writes one is checked, not the first: the panel's chips
    were the ones that went back to being spans, and the card's came first.
    """
    spots = [m.start() for m in re.finditer(r"data-tag=", web.PAGE)]
    assert len(spots) >= 3   # the card, the crumb, and the panel
    for at in spots:
        assert "<button" in web.PAGE[max(0, at - 80):at]


def test_a_card_is_not_a_button_holding_buttons():
    """The title opens the note; a card with the role swallowed the chips."""
    assert 'role="button"' not in web.PAGE
    assert 'class="t" data-open=' in web.PAGE


def test_a_lookup_table_is_never_indexed_blind():
    """`category: __proto__` fetched something inherited and broke the panel."""
    assert "Object.hasOwn" in web.PAGE
    assert "NAMES[" not in web.PAGE
    assert "NOTE_SOURCE[" not in web.PAGE
