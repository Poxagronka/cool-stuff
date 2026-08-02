#!/usr/bin/env python3
"""Step 0 and step 1: read the chat history once, via a user account.

    python scripts/backfill.py --recon          just count, change nothing
    python scripts/backfill.py --dump           store messages and links
    python scripts/backfill.py --process        enrich, categorise, write notes

Bot api cannot read history at all, so this runs on your own account through
mtproto. Run it from a laptop on a residential ip: the same fetch that returns
nothing from a datacentre often returns full metadata from home.
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telethon import TelegramClient  # noqa: E402
from telethon.tl.types import InputMessagesFilterUrl  # noqa: E402

from tglinks import canon, db, pipeline, urls, vault  # noqa: E402
from tglinks.config import (  # noqa: E402
    DB_PATH,
    TG_API_HASH,
    TG_API_ID,
    TG_CHAT,
    VAULT_PATH,
)

SESSION = str(Path(__file__).resolve().parents[1] / "data" / "backfill")


def _entities(msg) -> list[dict]:
    out = []
    for ent in msg.entities or []:
        name = type(ent).__name__
        if name == "MessageEntityTextUrl":
            out.append({"type": "text_link", "url": ent.url})
        elif name == "MessageEntityUrl":
            out.append({"type": "url", "offset": ent.offset, "length": ent.length})
    return out


async def iter_links(client, chat, limit: int | None):
    """Yield (message, [urls]) for every message that carries a link."""
    async for msg in client.iter_messages(chat, filter=InputMessagesFilterUrl, limit=limit):
        text = msg.message or ""
        found = urls.from_entities(text, _entities(msg))
        if not found and getattr(msg, "web_preview", None):
            preview_url = getattr(msg.web_preview, "url", None)
            if preview_url:
                found = [preview_url]
        if found:
            yield msg, found


async def author_of(client, msg, cache: dict) -> str:
    uid = getattr(msg.from_id, "user_id", None) if msg.from_id else None
    if uid is None:
        return ""
    if uid not in cache:
        try:
            user = await client.get_entity(uid)
            cache[uid] = (user.first_name or user.username or str(uid)).strip()
        except Exception:
            cache[uid] = str(uid)
    return cache[uid]


async def list_chats(client, limit: int = 60) -> None:
    """Print group dialogs with their ids, so the chat can be picked by name."""
    print(f"{'id':>16}  {'тип':<8}  название")
    print("-" * 70)
    async for dialog in client.iter_dialogs(limit=limit):
        if not (dialog.is_group or dialog.is_channel):
            continue
        kind = "группа" if dialog.is_group else "канал"
        print(f"{dialog.id:>16}  {kind:<8}  {dialog.name}")
    print("\nСкопируй нужный id в .env как TG_CHAT=...")


async def recon(client, chat, limit):
    total, keys, domains, raw = 0, set(), Counter(), 0
    async for msg, found in iter_links(client, chat, limit):
        total += 1
        for url in found:
            raw += 1
            keys.add(canon.key(url))
            domains[canon.domain(url)] += 1
        if total % 200 == 0:
            print(f"  ...{total} сообщений, {len(keys)} уникальных", file=sys.stderr)

    print(f"\nСообщений со ссылками : {total}")
    print(f"Ссылок всего          : {raw}")
    print(f"Уникальных после канона: {len(keys)}")
    print(f"Доменов               : {len(domains)}\n")
    print("Топ-25 доменов:")
    for host, count in domains.most_common(25):
        print(f"  {count:5d}  {host}")

    unique = len(keys)
    print("\nВывод:")
    if unique < 500:
        print("  <500 — пайплайн не нужен, хватит одного прогона --dump --process.")
    elif unique < 3000:
        print("  500-3000 — свой пайплайн окупается, продолжай по плану.")
    else:
        print("  >3000 — стоит посмотреть на Karakeep, см. research/07.")


async def dump(client, chat, limit, conn):
    cache: dict[int, str] = {}
    stored = new = 0
    async for msg, found in iter_links(client, chat, limit):
        record = {
            "chat_id": msg.chat_id,
            "msg_id": msg.id,
            "sent_at": msg.date.isoformat(timespec="seconds"),
            "author": await author_of(client, msg, cache),
            "text": msg.message or "",
            "reply_to": getattr(msg.reply_to, "reply_to_msg_id", None),
            "preview": None,
        }
        pipeline.store_message(conn, record)
        stored += 1
        for url in found:
            if pipeline.store_link(conn, record, url):
                new += 1
        if stored % 100 == 0:
            conn.commit()
            print(f"  ...{stored} сообщений, {new} новых ссылок", file=sys.stderr)
        await asyncio.sleep(0.05)
    conn.commit()
    print(f"Сохранено сообщений: {stored}, новых уникальных ссылок: {new}")


async def process(conn, vault_root, limit):
    vault.scaffold(vault_root)
    rows = conn.execute(
        "SELECT cluster_id FROM entry WHERE status = 'new' ORDER BY cluster_id LIMIT ?",
        (limit or 1_000_000,),
    ).fetchall()
    print(f"К обработке: {len(rows)}")
    for i, row in enumerate(rows, 1):
        try:
            path = await pipeline.process_entry(conn, row["cluster_id"], vault_root)
        except Exception as exc:
            print(f"  [{i}] ошибка на cluster {row['cluster_id']}: {exc}", file=sys.stderr)
            continue
        if path:
            print(f"  [{i}/{len(rows)}] {path.name}")
    print("Готово.")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-chats", action="store_true", help="показать список чатов с id")
    ap.add_argument("--recon", action="store_true", help="только посчитать")
    ap.add_argument("--dump", action="store_true", help="выгрузить в sqlite")
    ap.add_argument("--process", action="store_true", help="обогатить и записать заметки")
    ap.add_argument("--chat", default=TG_CHAT)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not (args.list_chats or args.recon or args.dump or args.process):
        ap.error("нужен хотя бы один из --list-chats / --recon / --dump / --process")

    conn = db.connect(DB_PATH)
    vault_root = Path(VAULT_PATH)

    if args.list_chats or args.recon or args.dump:
        if not TG_API_ID or not TG_API_HASH:
            print("TG_API_ID / TG_API_HASH не заданы, см. .env.example", file=sys.stderr)
            return 1
        if not args.list_chats and not args.chat:
            print("не указан чат: --chat или TG_CHAT в .env", file=sys.stderr)
            return 1
        Path(SESSION).parent.mkdir(parents=True, exist_ok=True)
        if not sys.stdin.isatty() and not Path(SESSION + ".session").exists():
            print(
                "Первый вход требует ввода номера и кода, а сейчас нет терминала.\n"
                "Запусти эту же команду в обычном Терминале — сессия сохранится\n"
                "в data/, и дальше ввод больше не понадобится.",
                file=sys.stderr,
            )
            return 1
        async with TelegramClient(SESSION, TG_API_ID, TG_API_HASH) as client:
            if args.list_chats:
                await list_chats(client)
            if args.recon or args.dump:
                chat = int(args.chat) if args.chat.lstrip("-").isdigit() else args.chat
                if args.recon:
                    await recon(client, chat, args.limit)
                if args.dump:
                    await dump(client, chat, args.limit, conn)

    if args.process:
        await process(conn, vault_root, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
