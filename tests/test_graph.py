"""The tag web is drawn on a canvas, so nothing about it is checkable as markup.

What is checkable is that no length in it is a pixel constant: the box is
whatever the screen gives, and a layout tuned to one width put words on top of
words at every other one.
"""

from tglinks import graph


def test_every_length_comes_off_the_size_of_the_box():
    """A laptop strip and a phone are not the same picture at the same scale."""
    for name in ("function tune(", "const holds =", "unit * unit", "unit * (0.18"):
        assert name in graph.JS
    # the numbers those replaced. a radius, a font size or a thread length in
    # bare pixels only ever fits the one screen it was tried on
    assert "3400 / d2" not in graph.JS
    assert "14 + 22 * Math.sqrt" not in graph.JS
    assert "10 + n.r * 0.22" not in graph.JS


def test_the_word_under_a_bubble_is_part_of_the_bubble():
    """Circles that clear each other still had their labels running together.

    `running` sat next to `hiking` and the two words were one. So the pair is
    kept apart as boxes the width of the text, and the sides of the box hold in
    the text rather than the centre of the circle.
    """
    assert "ctx.measureText(n.text)" in graph.JS
    assert "a.hw + b.hw" in graph.JS
    assert "Math.max(n.r, n.lw / 2)" in graph.JS


def test_a_box_that_changed_size_is_laid_out_again():
    """Turning a phone sideways is a different web, not the same one stretched."""
    assert "if (latest) apply(latest); else kick();" in graph.JS


def test_the_web_is_centred_as_one_thing():
    """Per-bubble springs left a wide box empty down one side."""
    assert "function recentre(" in graph.JS
