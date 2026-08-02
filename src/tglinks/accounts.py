"""Invite-only accounts: who may look at the vault.

Getting in the first time needs an invite: a url with a code in it, single use,
and it knows who minted it, so an account that hands its links out carelessly is
visible rather than anonymous. Signing up on that link is where you pick the
name and password you come back with afterwards.

Coming back is an ordinary sign-in. It used to be a second permanent link, which
meant a bearer token sitting in a browser history and a chat log forever — one
forward and the sender's account was somebody else's too.
"""

import base64
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from hashlib import scrypt

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  key        TEXT NOT NULL UNIQUE,
  invited_by INTEGER REFERENCES account(id),
  created_at TEXT NOT NULL
);
-- the name is the login, so two people cannot hold the same one, and "Sasha"
-- must not be a different account from "sasha"
CREATE UNIQUE INDEX IF NOT EXISTS ix_account_name ON account(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS invite (
  code       TEXT PRIMARY KEY,
  created_by INTEGER REFERENCES account(id),
  created_at TEXT NOT NULL,
  used_by    INTEGER REFERENCES account(id),
  used_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_invite_by ON invite(created_by);

CREATE TABLE IF NOT EXISTS session (
  token      TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES account(id),
  created_at TEXT NOT NULL,
  seen_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_session_acc ON session(account_id);
"""

COOKIE = "sid"
SESSION_DAYS = 365
# enough to invite the people you actually know, few enough that a leaked
# account cannot quietly open the door for a crowd
UNUSED_LIMIT = 5
NAME_LIMIT = 40
PASSWORD_MIN = 8
PASSWORD_MAX = 200

# scrypt at the parameters python's own docs use for interactive logins. one
# check is a few tens of milliseconds, which is nothing for a person and a wall
# for anybody working through a word list
SCRYPT = {"n": 2**14, "r": 8, "p": 1}

# added after the first accounts existed, so it cannot be NOT NULL
LATER = [("account", "pass_hash", "TEXT")]

NAME_OK = re.compile(r"^[\w][\w .\-]*$", re.U)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def setup(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, column, decl in LATER:
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()


def clean_name(raw: str) -> str:
    """The name as it will be stored, or empty when it cannot be a login.

    Slashes, angle brackets and the like are out: this string ends up in a url
    on the sign-in form and in html on every page that greets you.
    """
    name = " ".join(str(raw or "").split())[:NAME_LIMIT]
    return name if NAME_OK.match(name) else ""


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    raw = scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return "scrypt${}${}".format(
        base64.b64encode(salt).decode(), base64.b64encode(raw).decode()
    )


def check_password(password: str, stored: str) -> bool:
    """Whether the password matches, in constant time and without raising."""
    try:
        kind, salt_b64, hash_b64 = str(stored or "").split("$")
        if kind != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        want = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    got = scrypt(password.encode(), salt=salt, dklen=len(want), **SCRYPT)
    return hmac.compare_digest(got, want)


def bad_password(password: str) -> str:
    """Why this password will not do, empty when it will."""
    if len(password or "") < PASSWORD_MIN:
        return f"The password needs at least {PASSWORD_MIN} characters."
    if len(password) > PASSWORD_MAX:
        return "That password is too long."
    return ""


# ---------------------------------------------------------------- invites


def mint(conn: sqlite3.Connection, account_id: int | None) -> str | None:
    """A fresh single-use code, or None when too many are already waiting."""
    if account_id is not None and unused_count(conn, account_id) >= UNUSED_LIMIT:
        return None
    code = secrets.token_urlsafe(9)
    conn.execute(
        "INSERT INTO invite(code, created_by, created_at) VALUES(?,?,?)",
        (code, account_id, now()),
    )
    conn.commit()
    return code


def unused_count(conn: sqlite3.Connection, account_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM invite WHERE created_by = ? AND used_by IS NULL",
        (account_id,),
    ).fetchone()
    return row["n"]


def open_invite(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    """The invite behind a code, only while nobody has spent it."""
    if not code:
        return None
    return conn.execute(
        "SELECT * FROM invite WHERE code = ? AND used_by IS NULL", (code,)
    ).fetchone()


def invites_of(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT i.*, a.name AS taken_by FROM invite i"
        " LEFT JOIN account a ON a.id = i.used_by"
        " WHERE i.created_by = ? ORDER BY i.created_at DESC",
        (account_id,),
    ).fetchall()


# ---------------------------------------------------------------- accounts


def join(conn: sqlite3.Connection, code: str, name: str,
         password: str) -> tuple[sqlite3.Row, str] | str:
    """Spend the code and create the account, or say what went wrong.

    Returns the new account with a live session, or a message to put on the
    form. Spending the invite and creating the account are one transaction: two
    people submitting the same link at the same moment must not both get in.
    """
    clean = clean_name(name)
    if not clean:
        return "Pick a name: letters, digits, spaces, dots and dashes."
    trouble = bad_password(password)
    if trouble:
        return trouble

    stored = hash_password(password)
    try:
        with conn:
            spent = conn.execute(
                "UPDATE invite SET used_at = ? WHERE code = ? AND used_by IS NULL",
                (now(), code),
            )
            if spent.rowcount == 0:
                return "dead"
            invite = conn.execute(
                "SELECT created_by FROM invite WHERE code = ?", (code,)
            ).fetchone()
            cur = conn.execute(
                "INSERT INTO account(name, key, pass_hash, invited_by, created_at)"
                " VALUES(?,?,?,?,?)",
                (clean, secrets.token_urlsafe(18), stored, invite["created_by"], now()),
            )
            account_id = int(cur.lastrowid)
            conn.execute("UPDATE invite SET used_by = ? WHERE code = ?", (account_id, code))
    except sqlite3.IntegrityError:
        return "Somebody already goes by that name here. Pick another."

    return by_id(conn, account_id), start_session(conn, account_id)


def sign_in(conn: sqlite3.Connection, name: str, password: str) -> str:
    """A session token for the right name and password, empty for anything else.

    An unknown name still costs a hash, so the response time does not quietly
    say which of the two was wrong.
    """
    row = by_name(conn, name)
    stored = row["pass_hash"] if row and row["pass_hash"] else hash_password("no such account")
    if not check_password(password or "", stored) or not row:
        return ""
    return start_session(conn, row["id"])


def by_id(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()


def by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    clean = clean_name(name)
    if not clean:
        return None
    return conn.execute(
        "SELECT * FROM account WHERE name = ? COLLATE NOCASE", (clean,)
    ).fetchone()


def set_password(conn: sqlite3.Connection, account_id: int, password: str,
                 keep: str = "") -> str:
    """Replace the password, signing every other device out along with it.

    A password gets changed because the old one is somewhere it should not be,
    and leaving the sessions it opened alive would make the change pointless.
    """
    trouble = bad_password(password)
    if trouble:
        return trouble
    with conn:
        conn.execute(
            "UPDATE account SET pass_hash = ? WHERE id = ?",
            (hash_password(password), account_id),
        )
        conn.execute(
            "DELETE FROM session WHERE account_id = ? AND token <> ?", (account_id, keep)
        )
    return ""


def rename(conn: sqlite3.Connection, account_id: int, name: str) -> None:
    clean = clean_name(name)
    if clean:
        conn.execute("UPDATE account SET name = ? WHERE id = ?", (clean, account_id))
        conn.commit()


# ---------------------------------------------------------------- sessions


def start_session(conn: sqlite3.Connection, account_id: int) -> str:
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO session(token, account_id, created_at, seen_at) VALUES(?,?,?,?)",
        (token, account_id, now(), now()),
    )
    conn.commit()
    return token


def whoami(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    """The account behind a session cookie, refreshing its last-seen stamp."""
    if not token:
        return None
    row = conn.execute(
        "SELECT a.* FROM session s JOIN account a ON a.id = s.account_id"
        " WHERE s.token = ? AND s.created_at > ?",
        (token, (datetime.now() - timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")),
    ).fetchone()
    if row:
        conn.execute("UPDATE session SET seen_at = ? WHERE token = ?", (now(), token))
        conn.commit()
    return row


def end_session(conn: sqlite3.Connection, token: str) -> None:
    if token:
        conn.execute("DELETE FROM session WHERE token = ?", (token,))
        conn.commit()


def head_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) AS n FROM account").fetchone()["n"]
