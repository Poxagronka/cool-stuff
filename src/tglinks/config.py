"""Configuration loaded from environment / .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# telegram mtproto (backfill only) — reused from the abooks_bot account.
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")

# telegram bot api (live collection). separate bot from the abooks one:
# a token can only carry a single webhook url.
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# chat to harvest. numeric id (-100...) or @username.
TG_CHAT = os.getenv("TG_CHAT", "")

DB_PATH = Path(os.getenv("DB_PATH", "data/links.db"))
VAULT_PATH = Path(os.getenv("VAULT_PATH", "data/vault"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# vault git remote, used by the fly app to push generated notes.
VAULT_REPO = os.getenv("VAULT_REPO", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# deploy key for the vault repo, scoped to that one repo
SSH_KEY = os.getenv("SSH_KEY", "")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))

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
