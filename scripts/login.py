#!/usr/bin/env python3
"""Two-step telegram login, so the code can be typed in a separate call.

    python scripts/login.py --phone +71234567890
    python scripts/login.py --code 12345 [--password ...]

Telethon's default flow blocks on input(), which needs a real terminal. Here
the code request and the sign-in are separate runs with the state on disk.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telethon import TelegramClient  # noqa: E402
from telethon.errors import (  # noqa: E402
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from tglinks.config import TG_API_HASH, TG_API_ID  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SESSION = str(ROOT / "data" / "backfill")
STATE = ROOT / "data" / "login.json"


async def request_code(phone: str) -> int:
    client = TelegramClient(SESSION, TG_API_ID, TG_API_HASH)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Уже авторизован как {me.first_name} (@{me.username}). Ничего не нужно.")
        await client.disconnect()
        return 0
    sent = await client.send_code_request(phone)
    STATE.write_text(json.dumps({"phone": phone, "hash": sent.phone_code_hash}))
    await client.disconnect()
    print(f"Код отправлен на {phone}. Он придёт в Telegram, не по SMS.")
    print("Дальше: python scripts/login.py --code <код>")
    return 0


async def sign_in(code: str, password: str | None) -> int:
    if not STATE.exists():
        print("Нет сохранённого запроса. Сначала --phone", file=sys.stderr)
        return 1
    state = json.loads(STATE.read_text())

    client = TelegramClient(SESSION, TG_API_ID, TG_API_HASH)
    await client.connect()
    try:
        await client.sign_in(state["phone"], code, phone_code_hash=state["hash"])
    except SessionPasswordNeededError:
        if not password:
            print("Включена двухфакторка. Повтори с --password <пароль>", file=sys.stderr)
            await client.disconnect()
            return 2
        await client.sign_in(password=password)
    except PhoneCodeInvalidError:
        print("Код неверный.", file=sys.stderr)
        await client.disconnect()
        return 1
    except PhoneCodeExpiredError:
        print("Код протух, запроси заново через --phone", file=sys.stderr)
        await client.disconnect()
        return 1

    me = await client.get_me()
    await client.disconnect()
    STATE.unlink(missing_ok=True)
    print(f"Готово, вошли как {me.first_name} (@{me.username}).")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone")
    ap.add_argument("--code")
    ap.add_argument("--password")
    args = ap.parse_args()

    if not TG_API_ID or not TG_API_HASH:
        print("TG_API_ID / TG_API_HASH не заданы", file=sys.stderr)
        return 1
    Path(SESSION).parent.mkdir(parents=True, exist_ok=True)

    if args.phone:
        return await request_code(args.phone)
    if args.code:
        return await sign_in(args.code, args.password)
    ap.error("нужен --phone или --code")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
