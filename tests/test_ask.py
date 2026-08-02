"""The chat box is a query builder, so the tests are about what it refuses to pass on."""

import asyncio

from tglinks import ask


def test_only_known_categories_and_tags_survive():
    plan = ask.coerce(
        {"query": "куртк", "category": "оружие", "tag": "неизвестный", "reply": "ищу"},
        {"outdoor"},
    )
    assert plan["category"] == ""
    assert plan["tag"] == ""


def test_markup_and_punctuation_are_stripped_from_the_model_output():
    plan = ask.coerce(
        {"query": "<script>alert(1)</script> куртк", "reply": "<b>вот</b> результат"},
        set(),
    )
    assert "<" not in plan["query"] and ">" not in plan["query"]
    assert "<" not in plan["reply"]
    assert "куртк" in plan["query"]


def test_reply_is_never_empty():
    assert ask.coerce({"query": "", "reply": ""}, set())["reply"] == "Ищу"


def test_fields_are_capped():
    plan = ask.coerce({"query": "а" * 500, "reply": "б" * 500}, set())
    assert len(plan["query"]) == 80
    assert len(plan["reply"]) == 120


def test_a_question_without_an_api_key_falls_back_to_plain_search(monkeypatch):
    monkeypatch.setattr(ask, "ANTHROPIC_API_KEY", "")
    plan = asyncio.run(ask.Asker().plan("тёплая куртка", []))
    assert plan == {"query": "тёплая куртка", "category": "", "tag": "", "reply": "Ищу"}


def test_the_limiter_lets_ten_through_then_stops():
    async def run():
        limiter = ask.Limiter(per_minute=10)
        for i in range(10):
            assert await limiter.allow("ip", 100.0 + i)
        assert not await limiter.allow("ip", 110.0)
        # a minute later the window has rolled over
        assert await limiter.allow("ip", 200.0)

    asyncio.run(run())


def test_limits_are_per_address():
    async def run():
        limiter = ask.Limiter(per_minute=1)
        assert await limiter.allow("a", 1.0)
        assert await limiter.allow("b", 1.0)
        assert not await limiter.allow("a", 1.0)

    asyncio.run(run())
