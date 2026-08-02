"""The free translation step. The network is never touched here."""

import asyncio
from datetime import date

import httpx
import pytest

from tglinks import translate


@pytest.fixture
def serve(monkeypatch):
    """Point httpx at a canned answer instead of the internet."""
    def install(handler):
        original = httpx.AsyncClient

        class Client(original):
            def __init__(self, **kw):
                kw.pop("timeout", None)
                super().__init__(transport=httpx.MockTransport(handler), **kw)

        monkeypatch.setattr(httpx, "AsyncClient", Client)
    return install


def answer(text: str, status: int = 200, quota: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "responseData": {"translatedText": text},
            "responseStatus": status,
            "quotaFinished": quota,
        })
    return handler


def english_of(text: str, when: date | None = None, **kw) -> str:
    return asyncio.run(translate.Translator(**kw).to_english(text, when))


@pytest.mark.parametrize("text", ["jacket", "  ", "cafe latte"])
def test_english_costs_nothing(text):
    """Latin already matches the index, so the budget is not touched."""
    t = translate.Translator()
    assert asyncio.run(t.to_english(text)) == ""
    assert t.spent == 0


def test_a_russian_question_comes_back_in_english(serve):
    serve(answer("something warm for the winter"))
    assert english_of("что-нибудь тёплое на зиму") == "something warm for the winter"


def test_the_budget_runs_out_and_returns_the_next_day(serve):
    serve(answer("shoes"))
    t = translate.Translator(daily_chars=12)
    day = date(2026, 8, 2)
    assert asyncio.run(t.to_english("обувь", day)) == "shoes"
    assert asyncio.run(t.to_english("обувь", day)) == "shoes"
    # a third would go over twelve characters
    assert asyncio.run(t.to_english("обувь", day)) == ""
    assert asyncio.run(t.to_english("обувь", date(2026, 8, 3))) == "shoes"


@pytest.mark.parametrize("reply", [
    answer("shoes", quota=True),      # the day's free translations are gone
    answer("обувь"),                  # came back in the alphabet it went in
    answer("", status=403),           # the service said no
])
def test_anything_short_of_english_is_a_miss(serve, reply):
    """A miss hands the question on to the model, which is the point."""
    serve(reply)
    assert english_of("обувь") == ""


def test_a_dead_service_is_not_an_error(serve):
    def blow_up(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")
    serve(blow_up)
    assert english_of("обувь") == ""
