"""The gate on privately saved links. Every test here is about what it drops."""

import asyncio

import pytest

from tglinks import llm, triage


@pytest.mark.parametrize("url", [
    "https://mail.google.com/mail/u/0/#inbox",
    "https://drive.google.com/file/d/abc/view",
    "https://www.dropbox.com/s/xyz/scan.pdf",
    "https://notion.so/my-plans-1234",
    "https://revolut.com/app",
    "https://t.me/c/1234567/89",
    "https://shop.com/order?token=abcdef",
    "http://192.168.1.10:8080/admin",
    "https://www.pornhub.com/view_video.php?viewkey=1",
    "https://onlyfans.com/someone",
    "https://checkin.lufthansa.com/?token=zz",
])
def test_a_private_host_never_reaches_the_model(url):
    assert triage.obviously_private(url)


@pytest.mark.parametrize("url", [
    "https://www.arcteryx.com/jacket",
    "https://apps.apple.com/app/id123",
    "https://fonts.google.com/specimen/Inter",
    "https://www.google.com/search?q=shoes",
])
def test_an_ordinary_link_gets_as_far_as_the_model(url):
    assert not triage.obviously_private(url)


def test_a_private_host_is_dropped_without_a_provider():
    kept, why = asyncio.run(
        triage.keep("https://mail.google.com/x", {}, "", llm.chain("groq/whatever"))
    )
    assert not kept
    assert why == "private by host"


def test_no_verdict_means_no_note():
    # an empty chain stands in for every provider being down at once
    kept, why = asyncio.run(triage.keep("https://shop.com/jacket", {}, "", []))
    assert not kept
    assert why == "no verdict"


def test_the_verdict_comes_from_the_tool_call(monkeypatch):
    async def answer(steps, system, user, tool, **kwargs):
        assert tool.name == "verdict"
        assert "jacket" in user
        return {"keep": True, "reason": "a jacket"}, steps[0]

    monkeypatch.setattr(llm, "call", answer)
    kept, why = asyncio.run(
        triage.keep("https://shop.com/jacket", {"domain": "shop.com"}, "брать?",
                    llm.chain("groq/llama-3.3-70b-versatile"))
    )
    assert kept
    assert why == "a jacket"


def test_the_note_is_passed_to_the_model_but_a_missing_one_does_not_break_it():
    text = triage.prompt("https://shop.com/x", {"domain": "shop.com"}, "  ")
    assert "(nothing)" in text
    assert "https://shop.com/x" in text
