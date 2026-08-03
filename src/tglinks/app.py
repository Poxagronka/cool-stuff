"""Telegram webhook service. Runs on fly.io, sleeps between messages."""

import asyncio
import contextlib
import hmac
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from . import (
    accounts, ask, authweb, brand, db, gitvault, hidden, pipeline, portal,
    translate, urls, vault, web,
)
from .config import (
    DB_PATH, GITHUB_TOKEN, SSH_KEY, TG_BOT_TOKEN, TG_CHAT, VAULT_PATH, VAULT_REPO,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tglinks")

# telegram signs webhook calls with this header when setWebhook set a secret
SECRET = os.getenv("WEBHOOK_SECRET", "")

app = FastAPI(title="cool-stuff")
_lock = asyncio.Lock()
_asker = ask.Asker()
_limiter = ask.Limiter()
# a password is worth guessing at, a question is not, so the door is stricter
_tries = ask.Limiter(per_minute=8)
_translator = translate.Translator()

# telegram's reaction api takes a literal emoji string, so these are escaped
# codepoints rather than characters: eyes = seen, writing hand = note created
REACT_SEEN = "\U0001f440"
REACT_SAVED = "\u270d"


@app.on_event("startup")
async def startup() -> None:
    if not SECRET:
        # without it there is nothing to tell telegram apart from anyone else
        # who found the url, and /webhook writes notes. refuse to run at all
        raise RuntimeError("WEBHOOK_SECRET is not set")
    if not TG_CHAT:
        # every update would then come from an unknown chat and be dropped
        raise RuntimeError("TG_CHAT is not set")
    app.state.conn = db.connect(DB_PATH)
    accounts.setup(app.state.conn)
    hidden.setup(app.state.conn)
    root = Path(VAULT_PATH)
    ssh_cmd = gitvault.install_ssh_key(SSH_KEY)
    if ssh_cmd:
        os.environ["GIT_SSH_COMMAND"] = ssh_cmd
    if VAULT_REPO:
        ok = await gitvault.ensure_clone(root, VAULT_REPO, GITHUB_TOKEN)
        log.info("vault clone: %s", "ok" if ok else "failed")
    vault.scaffold(root)
    app.state.vault = root
    # the hidden set is read once and lives on the index, which filters at parse
    # time: the results, the counts and the tag web are all built from what the
    # index kept, so none of them can forget to leave a hidden card out
    app.state.index = portal.Index(root, hidden.all_urls(app.state.conn))
    log.info("portal index: %s notes", app.state.index.load())


# telegram posts here and nobody is logged in for it; the rest of the door is
# shut, including every api route the page itself calls
OPEN_PATHS = ("/webhook", "/health", "/join", "/signin", "/favicon.svg")


@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path
    if any(path == p or path.startswith(p + "/") for p in OPEN_PATHS):
        return await call_next(request)
    who = accounts.whoami(app.state.conn, request.cookies.get(accounts.COOKIE, ""))
    if not who:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "invite only"}, status_code=401)
        return HTMLResponse(authweb.locked(), status_code=403)
    request.state.account = who
    return await call_next(request)


def remember(request: Request, response: Response, token: str) -> Response:
    # secure only where it can be honoured: on plain http (a local run) the
    # browser would drop the cookie and nobody could ever log in
    https = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
    response.set_cookie(
        accounts.COOKIE, token, max_age=accounts.SESSION_DAYS * 86400,
        httponly=True, samesite="lax", secure=https, path="/",
    )
    return response


def site_root(request: Request) -> str:
    """The public origin, so invite links are shareable rather than localhost."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{host}" if host else str(request.base_url).rstrip("/")


@app.get("/join/{code}", response_class=HTMLResponse)
async def join_page(code: str) -> HTMLResponse:
    if not accounts.open_invite(app.state.conn, code):
        return HTMLResponse(authweb.dead_invite(), status_code=410)
    return HTMLResponse(authweb.join_form(code))


# a name and a password fit in a fraction of this; anything larger is not a form
FORM_LIMIT = 8 * 1024


async def fields(request: Request) -> dict[str, list[str]]:
    """A urlencoded form, without pulling in python-multipart.

    Read with a ceiling rather than buffered whole: these routes are open to
    anyone on the internet, and `await request.body()` on a chunked upload
    happily takes as much memory as the sender feels like sending.
    """
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > FORM_LIMIT:
            raise HTTPException(status_code=413, detail="form too large")
    return parse_qs(raw.decode("utf-8", "replace"))


@app.post("/join/{code}")
async def join_submit(code: str, request: Request) -> Response:
    form = await fields(request)
    name = form.get("name", [""])[0]
    made = accounts.join(app.state.conn, code, name, form.get("password", [""])[0])
    if isinstance(made, str):
        if made == "dead":
            return HTMLResponse(authweb.dead_invite(), status_code=410)
        return HTMLResponse(authweb.join_form(code, made, name), status_code=400)
    _, token = made
    return remember(request, RedirectResponse("/", status_code=303), token)


@app.post("/signin")
async def signin(request: Request) -> Response:
    """Name and password, the ordinary way back in."""
    who = request.headers.get("fly-client-ip") or (request.client.host if request.client else "?")
    if not await _tries.allow(who, asyncio.get_running_loop().time()):
        return HTMLResponse(
            authweb.locked("Too many attempts. Wait a minute."), status_code=429
        )
    form = await fields(request)
    token = accounts.sign_in(
        app.state.conn, form.get("name", [""])[0], form.get("password", [""])[0]
    )
    if not token:
        # which of the two was wrong is not said on purpose
        return HTMLResponse(authweb.locked("Wrong name or password."), status_code=403)
    return remember(request, RedirectResponse("/", status_code=303), token)


@app.get("/signin", response_class=HTMLResponse)
async def signin_page() -> HTMLResponse:
    return HTMLResponse(authweb.locked())


def admin_or_403(request: Request):
    """The account behind this request, if it is allowed to hide anything.

    The flag is read off the row the session loaded, so the answer comes from
    the database and not from anything the browser sent. Every route that can
    change what other people see goes through here — a page that does not draw
    the button is not a check.
    """
    account = getattr(request.state, "account", None)
    if not accounts.is_admin(account):
        raise HTTPException(status_code=403, detail="not yours to hide")
    return account


def buried_cards() -> list[tuple[str, str]]:
    """Every hidden url with the title of its note, newest hide first.

    The database knows the urls and the vault knows what they are called, so
    the two are joined here. A url whose note has since been deleted keeps its
    row and simply has no title.
    """
    named = {item.url: item.title for item in app.state.index.buried}
    return [(row["url"], named.get(row["url"], "")) for row in hidden.rows(app.state.conn)]


def reread_hidden() -> None:
    """The hidden set changed, so the index is built again through the new one."""
    app.state.index.set_hidden(hidden.all_urls(app.state.conn))


@app.get("/me", response_class=HTMLResponse)
async def me(request: Request) -> HTMLResponse:
    account = request.state.account
    return HTMLResponse(authweb.profile(
        account, accounts.invites_of(app.state.conn, account["id"]), site_root(request),
        hidden=buried_cards() if accounts.is_admin(account) else None,
    ))


@app.post("/api/hide")
async def hide_card(request: Request) -> dict:
    """Take one card off the site, for everybody including whoever asked."""
    account = admin_or_403(request)
    payload = await request.json()
    if not hidden.hide(app.state.conn, str(payload.get("url") or ""), account["id"]):
        raise HTTPException(status_code=400, detail="that is not a url")
    reread_hidden()
    return {"ok": True}


@app.post("/me/unhide")
async def unhide_card(request: Request) -> Response:
    admin_or_403(request)
    form = await fields(request)
    hidden.unhide(app.state.conn, form.get("url", [""])[0])
    reread_hidden()
    return RedirectResponse("/me", status_code=303)


@app.post("/me/invite")
async def new_invite(request: Request) -> Response:
    account = request.state.account
    if accounts.mint(app.state.conn, account["id"]) is None:
        return HTMLResponse(authweb.profile(
            account, accounts.invites_of(app.state.conn, account["id"]), site_root(request),
            f"You already have {accounts.UNUSED_LIMIT} invites waiting to be used.",
            hidden=buried_cards() if accounts.is_admin(account) else None,
        ), status_code=429)
    return RedirectResponse("/me", status_code=303)


@app.post("/me/password")
async def change_password(request: Request) -> Response:
    account = request.state.account
    token = request.cookies.get(accounts.COOKIE, "")
    form = await fields(request)
    trouble = accounts.set_password(
        app.state.conn, account["id"], form.get("password", [""])[0], keep=token
    )
    return HTMLResponse(authweb.profile(
        account, accounts.invites_of(app.state.conn, account["id"]), site_root(request),
        error=trouble, said="" if trouble else "Changed. Other devices are signed out.",
        hidden=buried_cards() if accounts.is_admin(account) else None,
    ), status_code=400 if trouble else 200)


@app.post("/logout")
async def logout(request: Request) -> Response:
    accounts.end_session(app.state.conn, request.cookies.get(accounts.COOKIE, ""))
    out = RedirectResponse("/", status_code=303)
    out.delete_cookie(accounts.COOKIE, path="/")
    return out


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> str:
    # the same page for everyone bar one button, and the button is only the
    # half of it that shows: /api/hide asks again on its own
    return web.page(accounts.is_admin(request.state.account))


@app.get("/favicon.svg")
async def favicon() -> Response:
    # open to everyone: the locked page wears the same mark
    return Response(
        brand.FAVICON, media_type="image/svg+xml",
        headers={"cache-control": "public, max-age=86400"},
    )


def live_index() -> portal.Index:
    """The index, re-read first if the vault moved under the process."""
    index = app.state.index
    if index.stale():
        log.info("the vault moved on disk: %s notes", index.load())
    return index


# a query translated once is remembered. the box fires on every keystroke and
# the free endpoint is metered by the character, so "бег" typed letter by letter
# must not cost three translations, and typing it again tomorrow none at all
_english: dict[str, str] = {}
_ENGLISH_MAX = 512


async def english_of(query: str) -> str:
    """The english of a foreign query, or "" when it could not be had."""
    if query in _english:
        return _english[query]
    out = await _translator.to_english(query)
    if len(_english) >= _ENGLISH_MAX:
        del _english[next(iter(_english))]
    _english[query] = out
    return out


async def both_alphabets(
    index: portal.Index, q: str, category: str, picked: list[str],
) -> tuple[list[portal.Item], str]:
    """What the query finds as typed and as translated, in one list.

    The vault is written in english and keeps the chat's russian captions as
    they were said, so a russian word has matches on both sides. Translating
    only when the first half comes back empty hid the english half whenever the
    russian half found anything at all.
    """
    hits = index.find(q, category, picked)
    if not translate.foreign(q):
        return hits, ""
    english = await english_of(q)
    if not english:
        return hits, ""
    return portal.merge_hits(hits, index.find(english, category, picked)), english


@app.get("/api/search")
async def search(
    q: str = "", category: str = "", tag: list[str] = Query(default=[]),
    offset: int = 0, limit: int = 60,
) -> dict:
    """The results and the total, which is all the grid needs."""
    index = live_index()
    picked = [t for t in tag if t][:8]
    hits, english = await both_alphabets(index, q, category, picked)
    start = max(0, offset)
    page = hits[start:start + min(120, max(1, limit))]
    return {"items": [i.public() for i in page], "total": len(hits),
            "translated": english}


@app.get("/api/graph")
async def graph(
    q: str = "", category: str = "", tag: list[str] = Query(default=[]),
) -> dict:
    """The tags of the current results as a web: the dots and the lines."""
    index = live_index()
    picked = [t for t in tag if t][:8]
    hits, _ = await both_alphabets(index, q, category, picked)
    return index.graph(hits, picked)


@app.post("/api/ask")
async def ask_endpoint(request: Request) -> dict:
    """A question in plain words, answered with search results only."""
    payload = await request.json()
    question = str(payload.get("q") or "")[:ask.MAX_QUESTION]
    who = request.headers.get("fly-client-ip") or (request.client.host if request.client else "?")
    if not await _limiter.allow(who, asyncio.get_running_loop().time()):
        raise HTTPException(status_code=429, detail="too many questions, wait a minute")

    index = live_index()
    # the cheap path first: a plain translation costs nothing and answers most
    # of what people type. haiku is only worth it when that finds nothing
    if translate.foreign(question):
        english = await _translator.to_english(question)
        if english:
            hits = index.find(english, mode="any")
            if hits:
                plan = {"query": english, "category": "", "tag": "", "reply": "Looking for"}
                return {
                    "plan": plan,
                    "items": [i.public() for i in hits[:60]],
                    "total": len(hits),
                }

    plan = await _asker.plan(question, index.top_tags(60))
    if not any((plan["query"], plan["category"], plan["tag"])):
        # the model refused the question. an empty query would list the whole
        # vault, and that reads as if the refusal had been ignored
        return {"plan": plan, "items": [], "total": 0}
    picked = [plan["tag"]] if plan["tag"] else []
    hits = index.find(plan["query"], plan["category"], picked, mode="any")
    if not hits and (plan["category"] or picked):
        # the category was the model's guess, not the person's. when the guess
        # is wrong it turns a good answer into an empty page, so it is dropped
        # rather than defended
        plan = {**plan, "category": "", "tag": ""}
        picked = []
        hits = index.find(plan["query"], mode="any")
    return {"plan": plan, "items": [i.public() for i in hits[:60]], "total": len(hits)}


@app.get("/health")
async def health() -> dict:
    conn = app.state.conn
    total = conn.execute("SELECT COUNT(*) AS n FROM entry").fetchone()["n"]
    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM entry WHERE status = 'new'"
    ).fetchone()["n"]
    return {"ok": True, "entries": total, "pending": pending}


async def react(chat_id: int, msg_id: int, emoji: str) -> None:
    """Acknowledge in-chat without posting a message."""
    if not TG_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/setMessageReaction"
    payload = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "reaction": [{"type": "emoji", "emoji": emoji}],
    }
    with contextlib.suppress(httpx.HTTPError):
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)


def to_record(msg: dict) -> dict:
    from datetime import datetime, timezone

    sender = msg.get("from") or {}
    author = (sender.get("first_name") or sender.get("username") or "").strip()
    sent = datetime.fromtimestamp(msg["date"], tz=timezone.utc)
    preview = msg.get("link_preview_options") or {}
    return {
        "chat_id": msg["chat"]["id"],
        "msg_id": msg["message_id"],
        "sent_at": sent.isoformat(timespec="seconds"),
        "author": author,
        "text": msg.get("text") or msg.get("caption") or "",
        "reply_to": (msg.get("reply_to_message") or {}).get("message_id"),
        "preview": preview or None,
    }


async def handle(msg: dict) -> None:
    """Store, enrich, categorise, write the note, push. One message at a time."""
    found = urls.from_message(msg)
    conn = app.state.conn
    record = to_record(msg)

    async with _lock:
        # plain talk is kept as well. it carries no link of its own, but five
        # minutes later somebody posts one and this is the sentence that says
        # what it is; a message never stored can never be read back as context
        if not found and not record["text"]:
            return
        pipeline.store_message(conn, record)
        if not found:
            conn.commit()
            return
        fresh = [cid for url in found if (cid := pipeline.store_link(conn, record, url))]
        conn.commit()

        if not fresh:
            await react(record["chat_id"], record["msg_id"], REACT_SEEN)
            return

        written = []
        for cluster_id in fresh:
            try:
                path = await pipeline.process_entry(conn, cluster_id, app.state.vault)
            except Exception:
                log.exception("failed on cluster %s", cluster_id)
                continue
            if path:
                written.append(path)

        if written:
            app.state.index.load()
        if written and VAULT_REPO:
            names = ", ".join(p.stem for p in written[:3])
            await gitvault.commit_push(app.state.vault, f"link: {names}")

        await react(record["chat_id"], record["msg_id"], REACT_SAVED if written else REACT_SEEN)


def ours(msg: dict) -> bool:
    """Did this come from the one chat we harvest?

    A valid signature only says telegram sent the update, not where it started:
    a stranger's dm to the bot, or any group it was added to, is signed exactly
    the same way. TG_CHAT is a string out of the environment and the update
    carries an int, so the numeric form is compared as text; it may also be an
    @username, which lives on the chat rather than its id.
    """
    chat = msg.get("chat") or {}
    if TG_CHAT.startswith("@"):
        return (chat.get("username") or "").casefold() == TG_CHAT[1:].casefold()
    return str(chat.get("id")) == TG_CHAT


@app.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    # bytes rather than str: compare_digest rejects a header with non-ascii in it
    if not hmac.compare_digest(x_telegram_bot_api_secret_token.encode(), SECRET.encode()):
        raise HTTPException(status_code=403, detail="bad secret")

    update = await request.json()
    msg = update.get("message") or update.get("channel_post")
    if msg:
        if not ours(msg):
            # the id only, never the text: whatever was sent is not ours to keep
            log.warning("update from chat %s dropped", (msg.get("chat") or {}).get("id"))
            return {"ok": True}
        # answer immediately: telegram retries on timeout and that means dupes
        background.add_task(handle, msg)
    return {"ok": True}
