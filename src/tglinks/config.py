"""Configuration loaded from environment / .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# telegram mtproto — reused from the abooks_bot account. the bot api cannot
# read saved messages at all, so both the one-off backfill and the scheduled
# pull on the server go through a user session.
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")

# where that session file lives. the root filesystem of a fly machine is
# ephemeral, so in production this has to name a path under the volume
# (/data), or the session vanishes with the next deploy and there is no
# terminal up there to sign in again. the suffix is forced because telethon
# appends it anyway and the existence check has to look at the real file.
_SESSION = os.getenv("TG_SESSION", "data/backfill.session")
TG_SESSION = Path(_SESSION if _SESSION.endswith(".session") else _SESSION + ".session")

# minutes between scheduled saved-messages pulls. 0 turns the schedule off and
# leaves only the trigger route.
SAVED_EVERY_MINUTES = int(os.getenv("SAVED_EVERY_MINUTES", "180"))

# telegram bot api (live collection). separate bot from the abooks one:
# a token can only carry a single webhook url.
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# chat to harvest. numeric id (-100...) or @username.
TG_CHAT = os.getenv("TG_CHAT", "")

DB_PATH = Path(os.getenv("DB_PATH", "data/links.db"))
VAULT_PATH = Path(os.getenv("VAULT_PATH", "data/vault"))

# the model keys are read by llm.py straight from the environment, one per
# provider, because a chain names its providers by string and nothing here
# would know which of them a given chain is going to reach for

# vault git remote, used by the fly app to push generated notes.
VAULT_REPO = os.getenv("VAULT_REPO", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# deploy key for the vault repo, scoped to that one repo
SSH_KEY = os.getenv("SSH_KEY", "")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))

# google's programmable search, used only for the cards no page would give a
# picture for. the free tier is 100 queries a day, so it is a tail and not a
# tier: no key means that tail is simply not there
GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_KEY", "")
GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX", "")

CATEGORIES = [
    "clothing",
    "tech",
    "software",
    "site",
    "article",
    "video",
    "food",
    "place",
    "misc",
]
