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


def test_a_bubble_is_sized_by_where_its_count_falls_in_the_range():
    """Fourteen tags between 21 and 57 links came out fourteen circles alike.

    `sqrt(count / biggest)` of a narrow range on top of a large floor is one
    size, and fourteen bubbles of one size have no reason to prefer any
    arrangement — which is what "the tags are going mad" looked like.
    """
    assert "(n.count - low) / span" in graph.JS
    assert "const top = Math.max(...counts), low = Math.min(...counts)" in graph.JS


def test_the_bubbles_look_for_their_places_on_screen():
    """The search is the animation, so the whole budget of it is watchable.

    Solving off screen and showing only the settled result was quicker and
    dead. What made the web look broken was never the search — it was circles
    of one size with nothing to choose between arrangements, and a scale
    snapped on at the end. Only someone who asked for no motion gets the
    layout solved before it is drawn.
    """
    assert "if (calm.matches) { settle(BUDGET); steps = BUDGET;" in graph.JS
    assert "const head = calm.matches" not in graph.JS


def test_the_room_and_the_overlaps_are_taken_out_over_frames():
    """A jump on the last frame reads as the picture glitching, not settling."""
    # the box is filled by an eased tug the threads pull against, and the
    # leftover overlaps come out across the closing frames rather than at once
    assert "function spread(all, ease)" in graph.JS
    assert "grew = spread(all, 0.05 * k)" in graph.JS
    assert "function unpack(" in graph.JS
    assert "if (tidy) unpack(4, 0.5); else unpack(60, 1);" in graph.JS
    # and the web is not called settled while it is still being pulled outwards
    assert "still = fastest < 0.12 && grew < 0.25 ? still + 1 : 0;" in graph.JS
    # a hub on ten threads used to be dragged straight through its neighbours
    assert "Math.sqrt(a.deg)" in graph.JS


def test_a_crowded_web_is_given_more_room():
    """Fourteen bubbles in a phone-width box is not the same picture as four."""
    assert "function stretch(" in graph.JS
    assert "box.style.height" in graph.JS


def test_a_box_that_changed_size_is_laid_out_again():
    """Turning a phone sideways is a different web, not the same one stretched."""
    assert "if (latest) apply(latest); else kick();" in graph.JS


def test_the_web_is_centred_as_one_thing():
    """Per-bubble springs left a wide box empty down one side."""
    assert "function recentre(" in graph.JS
