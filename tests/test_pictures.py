"""Picking a picture off a page that never declared one."""

from tglinks import pictures

BASE = "https://shop.example.com/products/fanghorn-ii-extrait"


def test_the_logo_and_the_payment_badges_are_not_the_picture():
    html = """
    <header><img src="/assets/logo.svg" alt="Example"></header>
    <main><img src="/cdn/fanghorn-1200x1200.jpg" alt="Fanghorn II Extrait bottle"></main>
    <footer>
      <img src="https://www.paypalobjects.com/mark.png" width="800" height="800" alt="pay">
      <img src="/img/visa-icon.png" width="900" height="900" alt="visa card">
    </footer>
    """
    assert pictures.pick(html, BASE) == "https://shop.example.com/cdn/fanghorn-1200x1200.jpg"


def test_what_the_shop_says_about_its_own_product_wins():
    html = """
    <script type="application/ld+json">
      {"@type": "Product", "name": "Fanghorn II",
       "image": ["https://cdn.example.com/hero.jpg"]}
    </script>
    <main><img src="/cdn/other-1200x1200.jpg" alt="a second angle"></main>
    """
    assert pictures.pick(html, BASE) == "https://cdn.example.com/hero.jpg"


def test_the_organizations_own_image_is_its_logo_and_stays_out():
    html = """
    <script type="application/ld+json">
      {"@type": "Organization", "image": "https://cdn.example.com/brandmark.png"}
    </script>
    """
    assert pictures.pick(html, BASE) == ""


def test_a_tracking_pixel_is_not_a_picture():
    html = '<body><img src="https://mc.yandex.ru/watch/123" width="1" height="1"></body>'
    assert pictures.pick(html, BASE) == ""


def test_a_lazy_image_is_read_from_the_attribute_it_will_load_from():
    html = ("<main><img data-src='/cdn/late-900x900.jpg' src='data:image/gif;base64,R0lGOD'"
            " alt='the thing itself'></main>")
    assert pictures.pick(html, BASE) == "https://shop.example.com/cdn/late-900x900.jpg"


def test_the_widest_candidate_of_a_srcset_is_the_one_taken():
    html = ("<main><img srcset='/s/small-200x200.jpg 200w, /s/big-1400x1400.jpg 1400w'"
            " alt='the thing itself'></main>")
    assert pictures.pick(html, BASE) == "https://shop.example.com/s/big-1400x1400.jpg"


def test_a_thumbnail_is_not_offered_as_the_card():
    html = '<main><img src="/cdn/thumb.jpg" width="80" height="80" alt="a small one"></main>'
    assert pictures.pick(html, BASE) == ""


def test_nothing_at_all_is_an_answer():
    assert pictures.pick("<html><body><p>words</p></body></html>", BASE) == ""
    assert pictures.pick("", BASE) == ""


def test_the_address_is_read_for_words_when_nothing_else_says_anything():
    assert pictures.words_in(BASE) == "shop.example.com fanghorn ii extrait"
    # the shop's filing system is not what the page is about
    assert pictures.words_in("https://www.gnuhr.com/en-de/collections/shorts/warp-short") == (
        "gnuhr.com shorts warp short"
    )
    # a bare root says only where it is
    assert pictures.words_in("https://lulua.pl/") == "lulua.pl"


def test_no_key_means_the_tail_is_simply_not_there(monkeypatch):
    import asyncio

    monkeypatch.setattr(pictures, "GOOGLE_CSE_KEY", "")
    assert asyncio.run(pictures.from_search(BASE, "Fanghorn II")) == ""
