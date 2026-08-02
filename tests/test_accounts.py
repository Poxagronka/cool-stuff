"""The door: invites are single use, and afterwards it is a name and a password."""

import sqlite3

import pytest

from tglinks import accounts

PASS = "correct horse battery"


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    accounts.setup(conn)
    return conn


def joined(conn, name="Sasha", code=None, password=PASS):
    return accounts.join(conn, code or accounts.mint(conn, None), name, password)


def test_first_invite_needs_no_account(conn):
    """Bootstrap: someone has to get in before anyone can be invited."""
    code = accounts.mint(conn, None)
    assert code
    assert accounts.open_invite(conn, code)


def test_joining_spends_the_code(conn):
    code = accounts.mint(conn, None)
    account, token = joined(conn, "Sasha", code)
    assert account["name"] == "Sasha"
    assert accounts.whoami(conn, token)["id"] == account["id"]
    # the same link handed to a second person does nothing
    assert accounts.open_invite(conn, code) is None
    assert joined(conn, "Someone Else", code) == "dead"
    assert accounts.by_name(conn, "Someone Else") is None


def test_invites_carry_their_author(conn):
    host, _ = joined(conn, "Sasha")
    code = accounts.mint(conn, host["id"])
    guest, _ = joined(conn, "Darina", code)
    assert guest["invited_by"] == host["id"]
    sent = accounts.invites_of(conn, host["id"])
    assert len(sent) == 1
    assert sent[0]["taken_by"] == "Darina"


def test_unused_invites_are_capped(conn):
    host, _ = joined(conn, "Sasha")
    for _ in range(accounts.UNUSED_LIMIT):
        assert accounts.mint(conn, host["id"])
    assert accounts.mint(conn, host["id"]) is None
    # spending one frees a slot
    joined(conn, "Guest", accounts.invites_of(conn, host["id"])[0]["code"])
    assert accounts.mint(conn, host["id"])


def test_a_join_that_fails_leaves_the_code_alone(conn):
    code = accounts.mint(conn, None)
    assert isinstance(joined(conn, "   ", code), str)
    assert isinstance(joined(conn, "Sasha", code, "short"), str)
    assert accounts.open_invite(conn, code)


def test_two_people_cannot_hold_the_same_name(conn):
    joined(conn, "Sasha")
    second = accounts.mint(conn, None)
    # the name is the login, so case is not a difference
    assert isinstance(joined(conn, "sasha", second), str)
    # and the invite is not spent on the collision
    assert accounts.open_invite(conn, second)


def test_signing_in_needs_the_right_password(conn):
    account, _ = joined(conn, "Sasha")
    assert accounts.sign_in(conn, "Sasha", "wrong") == ""
    assert accounts.sign_in(conn, "Nobody", PASS) == ""
    token = accounts.sign_in(conn, "sasha", PASS)
    assert accounts.whoami(conn, token)["id"] == account["id"]


def test_changing_the_password_clears_the_other_devices(conn):
    account, phone = joined(conn, "Sasha")
    laptop = accounts.start_session(conn, account["id"])
    assert accounts.set_password(conn, account["id"], "a whole new one", keep=phone) == ""
    assert accounts.whoami(conn, phone)
    assert accounts.whoami(conn, laptop) is None
    assert accounts.sign_in(conn, "Sasha", PASS) == ""
    assert accounts.sign_in(conn, "Sasha", "a whole new one")


def test_a_password_too_short_is_not_stored(conn):
    account, _ = joined(conn, "Sasha")
    assert accounts.set_password(conn, account["id"], "abc")
    assert accounts.sign_in(conn, "Sasha", PASS)


def test_a_stored_hash_is_not_the_password(conn):
    account, _ = joined(conn, "Sasha")
    stored = accounts.by_name(conn, "Sasha")["pass_hash"]
    assert PASS not in stored
    assert stored.startswith("scrypt$")
    # same password, different salt, so two accounts never look alike
    joined(conn, "Darina", accounts.mint(conn, None))
    assert accounts.by_name(conn, "Darina")["pass_hash"] != stored
    assert accounts.check_password(PASS, stored)
    assert not accounts.check_password(PASS, "nonsense")


def test_signing_out_kills_only_that_session(conn):
    account, phone = joined(conn, "Sasha")
    laptop = accounts.start_session(conn, account["id"])
    accounts.end_session(conn, phone)
    assert accounts.whoami(conn, phone) is None
    assert accounts.whoami(conn, laptop)


def test_unknown_tokens_and_codes_are_nobody(conn):
    assert accounts.whoami(conn, "") is None
    assert accounts.whoami(conn, "made-up") is None
    assert accounts.by_name(conn, "made-up") is None
    assert accounts.open_invite(conn, "made-up") is None
