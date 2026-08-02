"""Telegram webhook service. Runs on fly.io, sleeps between messages."""

import asyncio
import contextlib
import logging
import os
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from . import db, gitvault, pipeline, urls, vault
from .config import DB_PATH, GITHUB_TOKEN, SSH_KEY, TG_BOT_TOKEN, VAULT_PATH, VAULT_REPO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tglinks")

# telegram signs webhook calls with this header when setWebhook set a secret
SECRET = os.getenv("WEBHOOK_SECRET", "")

app = FastAPI(title="tg-links-collector")
_lock = asyncio.Lock()

# telegram's reaction api takes a literal emoji string, so these are escaped
# codepoints rather than characters: eyes = seen, writing hand = note created
REACT_SEEN = "\U0001f440"
REACT_SAVED = "\u270d"


@app.on_event("startup")
async def startup() -> None:
    app.state.conn = db.connect(DB_PATH)
    root = Path(VAULT_PATH)
    ssh_cmd = gitvault.install_ssh_key(SSH_KEY)
    if ssh_cmd:
        os.environ["GIT_SSH_COMMAND"] = ssh_cmd
    if VAULT_REPO:
        ok = await gitvault.ensure_clone(root, VAULT_REPO, GITHUB_TOKEN)
        log.info("vault clone: %s", "ok" if ok else "failed")
    vault.scaffold(root)
    app.state.vault = root


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
    if not found:
        return

    conn = app.state.conn
    record = to_record(msg)

    async with _lock:
        pipeline.store_message(conn, record)
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

        if written and VAULT_REPO:
            names = ", ".join(p.stem for p in written[:3])
            await gitvault.commit_push(app.state.vault, f"link: {names}")

        await react(record["chat_id"], record["msg_id"], REACT_SAVED if written else REACT_SEEN)


@app.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    if SECRET and x_telegram_bot_api_secret_token != SECRET:
        raise HTTPException(status_code=403, detail="bad secret")

    update = await request.json()
    msg = update.get("message") or update.get("channel_post")
    if msg:
        # answer immediately: telegram retries on timeout and that means dupes
        background.add_task(handle, msg)
    return {"ok": True}
