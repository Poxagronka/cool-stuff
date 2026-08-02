"""The cheap half of multilingual search.

Everything in the collection is written in english, so a question in Russian or
Ukrainian has to become english before it can match anything. Haiku does that
well but costs a call; MyMemory does the easy cases for nothing. So the free
one goes first, under a daily budget, and the model is the fallback rather than
the default.

Quality is not traded away for the saving: a free translation is literal and
carries no synonyms, so it is only accepted when it actually finds something.
An empty result means the question goes on to Haiku, which knows to widen it.

MyMemory is free and keyless: about 5000 characters a day per address, ten
times that if an email address is sent along. Lingva, the obvious open-source
alternative, was tried first — every public instance either returned 500 or sat
behind a challenge page.
"""

import asyncio
import logging
import os
import re
from datetime import date

import httpx

log = logging.getLogger("tglinks")

API_URL = "https://api.mymemory.translated.net/get"
# their ceiling is 5000 characters a day anonymously and 50000 with an email on
# the request; we stay under whichever applies rather than find out by being
# cut off in the middle of someone's search
EMAIL = os.getenv("TRANSLATE_EMAIL", "poxagronka@gmail.com")
DAILY_CHARS = int(os.getenv("TRANSLATE_DAILY_CHARS", "40000" if EMAIL else "4000"))
TIMEOUT = float(os.getenv("TRANSLATE_TIMEOUT", "5"))

# anything past latin extended-b: cyrillic, greek, cjk and the rest. plain
# accented latin is not worth a round trip, the index already holds those words
FOREIGN = re.compile("[^\\u0000-\\u024f]")


def foreign(text: str) -> bool:
    return bool(FOREIGN.search(text or ""))


class Translator:
    """Free translations until the day's characters run out."""

    def __init__(self, daily_chars: int = DAILY_CHARS, email: str = EMAIL) -> None:
        self.daily_chars = daily_chars
        self.email = email
        self.day = date.min
        self.spent = 0
        self.lock = asyncio.Lock()

    async def take(self, cost: int, today: date) -> bool:
        """Characters out of today's budget, or nothing when it is spent."""
        async with self.lock:
            if today != self.day:
                self.day, self.spent = today, 0
            if self.spent + cost > self.daily_chars:
                return False
            self.spent += cost
            return True

    async def to_english(self, text: str, today: date | None = None) -> str:
        """The english of it, or "" when the free path did not deliver."""
        text = (text or "").strip()[:200]
        # already english as far as the alphabet goes: nothing to spend on
        if not foreign(text) or not await self.take(len(text), today or date.today()):
            return ""
        params = {"q": text, "langpair": "Autodetect|en"}
        if self.email:
            params["de"] = self.email
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            if data.get("quotaFinished") or int(data.get("responseStatus", 0)) != 200:
                log.info("free translation quota: %s", data.get("responseDetails"))
                return ""
            out = str(data["responseData"]["translatedText"] or "").strip()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
            log.info("free translation unavailable: %s", err)
            return ""
        # unchanged text means it recognised nothing, and text still in another
        # alphabet means it did not reach english. both are a miss
        if out.lower() == text.lower() or foreign(out):
            return ""
        return out[:200]
