# Telegram — rules

**R1.** The Bot API does not return history. Updates live for 24 hours, and there
is no way at all to read messages sent before the bot existed. History comes only
through MTProto (Telethon) from a user account.

**R2.** Turn the bot's privacy mode off BEFORE adding it to the group. The setting
is applied at the moment it is added, so the wrong order means a silent bot:
`/setprivacy` → Disable → only then add it.

**R3.** One token, one webhook. Reusing another bot's token (`abooks_bot`, for
example) does not work: `setWebhook` overwrites the other URL.

**R4.** Links of the form `t.me/c/<id>/<msg>` exist only for supergroups and
channels, whose id starts with `-100`. A plain group has no such link at all —
building one from the id without the prefix means putting a broken url into every
note.

**R5.** Telegram also marks a bare host with no scheme (`butkus.org`) as a link.
The scheme has to be added before parsing the url, otherwise `urlsplit` reads the
host as a path and the domain comes out empty.

**R6.** Offsets in `entities` are counted in UTF-16 units, not in Python
characters. With emoji and non-BMP characters, naive slicing by index breaks.

**R7.** The `.session` file is created on the very first login attempt, even a
failed one. Its presence does not mean the login succeeded — ask
`client.is_user_authorized()`.

**R8.** Context around a link stops at the nearest neighbouring message that
carries a link, on both sides. A window of "the whole ±5 minutes" pulls in the
conversation about the neighbouring link, and the model then describes the wrong
thing — it produced the Russian description «куртка, которую Весна носит уже пару
лет» ("the jacket Vesna has been wearing for a couple of years"), which was about
a different link in the same window.

Whether a message carries a link is answered by the `link` table, not by looking
for a url in its text. A `text_link` entity hides the address behind display
text, so a message reading «вот эта» is a link that no regex over the text can
see, and the walk used to stroll straight through it into somebody else's
conversation. The visible-url check is still there behind the table lookup, for
a message stored before its link was recorded.

The other half of the same rule: everything within the window is stored, not
only the messages with a url in them. The sentence that explains a link almost
never contains one ("runs two sizes small"), and a message that was never
stored cannot be read back as anybody's context. In scope, and therefore
stored: a message with a link, any message within ±5 minutes of one, and
anything up the reply chain of a message already kept. The live webhook stores
every message with text in the watched chat, because it cannot know that a link
is coming two minutes later.

**R9.** A valid secret header says telegram sent the update, not where it
started. A stranger's dm to the bot and any group somebody adds it to are
signed exactly the same way, so the chat is checked as well: anything that is
not `TG_CHAT` is dropped and logged by chat id only, never by text — whatever
was sent is not ours to keep. `TG_CHAT` is a string out of the environment and
the update carries an int, so the numeric form is compared as text; an
`@username` lives on the chat rather than on its id. Both `WEBHOOK_SECRET` and
`TG_CHAT` are checked at startup and the app refuses to run without either.
Missing config used to mean an open door, which is the wrong way to fail for
something that writes into a repo.

**R10.** Privacy is a property of a message, not of a link and not of a
cluster. The same page can be posted in the group and saved privately months
apart, and that is one note. So the note is written from the public sightings
only, unless every sighting is private — what the owner wrote beside the link
in his own saved messages never faced the triage gate and is dropped from the
note and from every prompt. The other direction matters too: a cluster the gate
refused reopens the moment a genuinely public sighting turns up, because there
was never anything to guard once the group has the link.

**R11.** Saved Messages answers to three names: `me`, your own `@username` and
your numeric user id. The backfill derives the private flag from the resolved
peer rather than from the string that was typed, otherwise `--chat me` and
`--chat @yourself` import the same messages under different rules and half of
them walk past the gate as public.
