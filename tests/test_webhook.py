"""The webhook door: the right secret, and the one chat we harvest."""

import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException

from tglinks import app as app_module

SECRET = "a-long-random-string"
GROUP = "-1001234567890"


class Update:
    """Enough of a Request for the handler: it only ever reads the body."""

    def __init__(self, payload: dict):
        self.payload = payload

    async def json(self) -> dict:
        return self.payload


def message(chat_id: str = GROUP, **chat) -> dict:
    return {"message": {"message_id": 1, "chat": {"id": int(chat_id), **chat}}}


def post(payload: dict, secret: str = SECRET) -> BackgroundTasks:
    """Call the endpoint and hand back whatever it scheduled."""
    background = BackgroundTasks()
    asyncio.run(app_module.webhook(Update(payload), background, secret))
    return background


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(app_module, "SECRET", SECRET)
    monkeypatch.setattr(app_module, "TG_CHAT", GROUP)


def test_the_group_is_processed():
    assert len(post(message()).tasks) == 1


def test_a_dm_is_not():
    """Telegram signs a stranger's dm exactly like the group's own messages."""
    assert post(message("777000")).tasks == []


def test_another_group_is_not():
    assert post(message("-1009999999999")).tasks == []


def test_a_username_chat_matches_by_name(monkeypatch):
    monkeypatch.setattr(app_module, "TG_CHAT", "@coolstuff")
    assert len(post(message("-1", username="CoolStuff")).tasks) == 1
    assert post(message("-1", username="somewhere_else")).tasks == []


def test_a_wrong_secret_is_refused():
    with pytest.raises(HTTPException) as refused:
        post(message(), "not-the-secret")
    assert refused.value.status_code == 403


def test_a_missing_secret_header_is_refused():
    with pytest.raises(HTTPException) as refused:
        post(message(), "")
    assert refused.value.status_code == 403


def test_startup_refuses_to_run_unconfigured(monkeypatch):
    """A machine that cannot tell telegram apart from anyone else stays down."""
    monkeypatch.setattr(app_module, "SECRET", "")
    with pytest.raises(RuntimeError):
        asyncio.run(app_module.startup())
    monkeypatch.setattr(app_module, "SECRET", SECRET)
    monkeypatch.setattr(app_module, "TG_CHAT", "")
    with pytest.raises(RuntimeError):
        asyncio.run(app_module.startup())
