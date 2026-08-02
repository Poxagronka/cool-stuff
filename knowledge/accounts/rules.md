# Accounts — rules

**R1.** Getting in the first time is an invite, coming back is a name and a
password. There is no permanent personal link any more. `/enter/{key}` was a
bearer token with no expiry: it sat in browser history, in whatever chat it was
forwarded through, and in the referrer of every outbound click. One forward and
the sender's account belonged to someone else.

**R2.** Passwords are hashed with stdlib `scrypt` at n=2^14, r=8, p=1 — the
parameters python's own docs give for an interactive login. One check costs a
few tens of milliseconds, which nobody notices and a word list cannot afford.
The stored string is `scrypt$<salt>$<hash>`; `check_password` compares with
`hmac.compare_digest` and returns False instead of raising on anything it
cannot parse.

**R3.** An unknown name still costs a hash. `sign_in` hashes against a dummy
when there is no such account, so the response time does not answer "does this
person exist here" for free. The error on the form says "wrong name or
password" for both cases, on purpose.

**R4.** The name is the login, so it is unique case-insensitively:
`CREATE UNIQUE INDEX ... ON account(name COLLATE NOCASE)`. Without NOCASE
"Sasha" and "sasha" are two accounts, and which one a sign-in reaches is
whatever the index feels like.

**R5.** Spending the invite and creating the account are one transaction, and
the invite is spent with a conditional `UPDATE ... WHERE used_by IS NULL` whose
`rowcount` is the check. Reading the invite first and inserting afterwards lets
two people who were sent the same link both get in.

**R6.** Changing a password deletes every session except the one that changed
it. A password is changed because the old one is somewhere it should not be,
and the sessions it already opened live for a year.

**R7.** The door is closed by default: the middleware lets through only
`/webhook`, `/health`, `/join`, `/signin` and `/favicon.svg`, and everything
else — including every `/api/` route the page itself calls — needs a session.
An api route answers 401 json, a page answers the sign-in form. New routes are
protected by not being on the list, which is the right way round.

**R8.** Sign-in is rate limited harder than the search box: 8 attempts a minute
per address against 10 questions. A password is worth guessing at and a
question is not.

**R9.** Both open form routes read the body with a ceiling (`fields()`, 8 KB)
rather than `await request.body()`. They are reachable without a session, and a
chunked upload with no ceiling takes as much memory as the sender feels like
giving it.

**R10.** The first account on a fresh machine has no invite to arrive on, so it
comes from `scripts/invite.py` run on the box that holds the database. That is
why `scripts/` is in the docker image and not just in the repo.

**R11.** An account created before passwords existed has an empty `pass_hash`
and can never sign in — `sign_in` hashes what was typed and compares, and
nothing hashes to the empty string, so it fails closed rather than open. The
name is still taken, though: the unique index on `account(name)` is `NOCASE`,
so the dead row blocks its own owner from re-joining under the same name. Check
with `scripts/invite.py --who` before minting an invite for somebody who
already appears there.
