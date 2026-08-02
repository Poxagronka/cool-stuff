# Telegram — facts

Verified 2026-08-02 on the live "cool stuff" chat.

## Chat and bot

- The "cool stuff" chat is a plain basic group, id `-4092567497`. Not a
  supergroup, which is why there are no deep links (see R4)
- Bot `@coolstuff_links_bot`, created through BotFather from the user account
- MTProto credentials reused from the `abooks_bot` project: one account can have
  several apps, and api_id/api_hash are tied to the account, not to the bot

## History size

350 messages with links, 391 links, 388 unique after canonicalization, 213
domains. Top: instagram 58, youtube 39, tiktok 16, x 16, apps.apple 9.

Dedup cut only 3 links out of 391. In a chat between friends, where the same
thing is rarely posted twice, heavy clustering machinery barely pays for itself —
its main value turned out to be mapping different forms of one url to a single
key, not catching repeats.

## Telethon login without a terminal

Claude Code gives no TTY, and Telethon calls `input()` directly. The workaround is
a two-step script: `login.py --phone` stores `phone_code_hash` in
`data/login.json`, `login.py --code` finishes the login. The code arrives in
Telegram, not by SMS.

With two-factor auth on, `sign_in(code)` raises `SessionPasswordNeededError`
instead of asking for the password. Enter the password only through getpass so it
does not end up in shell history.

## Creating the bot automatically

BotFather is driven by plain messages from the user session, no keyboard button
presses: `/newbot` → name → username, then `/setprivacy` → `@username` →
`Disable`. Adding the bot to a basic group is
`messages.AddChatUserRequest(chat_id=<positive id>, user_id=<bot>)`.
