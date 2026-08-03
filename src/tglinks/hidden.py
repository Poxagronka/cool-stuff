"""Links the portal does not show, though the vault still keeps them.

Hiding is a decision about the site, not about the collection. The note stays
on disk exactly as it was written, so the collector goes on deduplicating
against the link and goes on appending whatever the chat says about it next —
a hidden thing mentioned again is still the same thing, and a second note for
it would be worse than the card nobody wanted to see.

That is why the hidden set lives here, in the database, keyed by the url a note
carries, rather than in the note's front matter: writing it into the vault would
put a portal decision into the collection and hand it to git.
"""

import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS hidden_url (
  url       TEXT PRIMARY KEY,
  hidden_at TEXT NOT NULL,
  hidden_by INTEGER
);
"""

# a url out of a note is a couple of hundred characters at worst, and the value
# arrives in a request body: whatever is longer than this is not one
URL_MAX = 2000


def setup(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def clean_url(raw: str) -> str:
    """The url as it will be stored, or empty when it cannot be one."""
    url = " ".join(str(raw or "").split())
    return url if 0 < len(url) <= URL_MAX else ""


def hide(conn: sqlite3.Connection, url: str, account_id: int | None = None) -> bool:
    """Take this url off the site. False when there was nothing to take off.

    Hiding the same url twice is not an error — two tabs open on the same grid
    is the ordinary way it happens — so the second one keeps the first stamp.
    """
    clean = clean_url(url)
    if not clean:
        return False
    conn.execute(
        "INSERT OR IGNORE INTO hidden_url(url, hidden_at, hidden_by) VALUES(?,?,?)",
        (clean, datetime.now().isoformat(timespec="seconds"), account_id),
    )
    conn.commit()
    return True


def unhide(conn: sqlite3.Connection, url: str) -> bool:
    clean = clean_url(url)
    if not clean:
        return False
    conn.execute("DELETE FROM hidden_url WHERE url = ?", (clean,))
    conn.commit()
    return True


def all_urls(conn: sqlite3.Connection) -> set[str]:
    """Every hidden url at once: the index is handed this and holds on to it."""
    return {r["url"] for r in conn.execute("SELECT url FROM hidden_url")}


def rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Newest first, which is the order the profile page lists them in."""
    return conn.execute(
        "SELECT * FROM hidden_url ORDER BY hidden_at DESC, url"
    ).fetchall()
