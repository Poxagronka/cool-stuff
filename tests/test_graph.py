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
    # the box is filled by a force, and the leftover overlaps come out across
    # the closing frames rather than all at once
    assert "const needX = short(W, span.x1 - span.x0)" in graph.JS
    assert "function unpack(" in graph.JS
    assert "if (tidy) unpack(4, 0.5); else unpack(60, 1);" in graph.JS
    # a hub on ten threads used to be dragged straight through its neighbours
    assert "Math.sqrt(a.deg)" in graph.JS


def test_the_search_ends_by_itself():
    """Every layout used to run the whole budget out however fast it had settled.

    The tug that fills the box scaled the positions, which skips the damping and
    so has no resting point: it pushed, the threads pulled back, and the web
    crept on for ever. Asking the velocities could not see that, because nobody's
    speed ever reached zero. What ends it is net movement over a window.
    """
    assert "n.vx += (n.x - mx) * needX" in graph.JS
    assert "if (steps % MARK === 0)" in graph.JS
    assert "far < MARK * 0.5" in graph.JS
    # and the damping tightens as it goes, or the tail of it creeps on for ever
    assert "const damp = 0.8 - 0.3 * Math.min(1, steps / 90);" in graph.JS
    # a bubble held against a wall used to keep the speed that put it there
    assert "if (wx !== n.x) n.vx = 0;" in graph.JS


def test_the_web_goes_on_moving_once_it_has_found_its_shape():
    """It must never come to a full stop — it should crawl, as if through jam.

    The old sine-wave wobble was wrong about the speed, not about the idea. The
    crawl goes in as a force, so the separation and the threads answer it and no
    gap it opens can close on a word, and it is capped at about a pixel a frame.
    """
    assert "crawl = true;" in graph.JS
    assert "const top = unit * (crawl ? 0.0055 : 0.075);" in graph.JS
    # restarting the solver has to clear it, or the re-layout crawls too
    assert "tidy = 12; crawl = false;" in graph.JS
    # but someone who asked for no motion gets none
    assert "if (calm.matches && done && !tidy) { asleep = true; return; }" in graph.JS


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
