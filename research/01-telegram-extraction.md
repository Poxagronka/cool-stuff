# Извлечение сообщений и ссылок из Telegram

Проверено 2026-08-02.

## Ключевой факт

Достать историю и собирать новое — **две разные технологии**. Бот через Bot API
физически не может прочитать ничего, что было до его добавления в группу.
Userbot через MTProto может всё, но держать его 24/7 — риск бана.

Отсюда гибрид: userbot один раз для бэкфилла, бот навсегда для нового.

## Сводная таблица

| Способ | Бэкфилл | Live | Превью ссылок | Риск |
|---|---|---|---|---|
| Telegram Desktop export JSON | да | нет | **нет**, только URL | нулевой |
| `tdl` (Go CLI, MTProto) | да | по крону | частично | userbot |
| **Telethon 1.44 / Kurigram** | **да** | да | **да, полные** | бан аккаунта |
| Bot API / n8n Telegram Trigger | **невозможно** | да | да | нулевой |
| TDLib (Pytdbot) | да | да | да | тот же + сложность |
| Zapier / Make / Readwise / Raindrop | нет | да | — | — |

## 1. Официальный экспорт Telegram Desktop

Settings → Advanced → Export Telegram data, либо правый клик по чату →
Export chat history. Схема: [core.telegram.org/import-export](https://core.telegram.org/import-export).

Поля сообщения: `id`, `type` (`message`/`service`), `date`, `date_unixtime`,
`edited`, `from`, `from_id` (формат `user123456`), `reply_to_message_id`,
`forwarded_from`, `saved_from`, `via_bot`, `author`.

**Текст лежит в двух параллельных полях:**
- `text` — строка или массив строк и объектов-сущностей (легаси, неудобно)
- `text_entities` — плоский массив `{type, text}`, покрывает весь текст

**Для ссылок нужен `text_entities`**, типы `link` (голый URL) и `text_link`
(скрытая гиперссылка, href в отдельном поле).

Типы сущностей целиком: `mention`, `hashtag`, `bot_command`, `link`, `email`,
`bold`, `italic`, `code`, `pre`, `plain`, `text_link`, `mention_name`, `phone`,
`cashtag`, `underline`, `strikethrough`, `blockquote`, `bank_card`, `spoiler`,
`custom_emoji`, `unknown`.

### Главный минус

**Link preview не экспортируется вообще.** В схеме нет объекта webpage — ни
title, ни description, ни og-картинки. Только URL в тексте. Метаданные придётся
дофетчивать самому.

### Лимиты

- Порог размера медиа по умолчанию небольшой (~8 МБ), слайдер до ~4 ГБ.
  **Файлы выше порога скипаются молча** — в JSON вместо пути warning-строка.
- Ограничений по количеству сообщений и глубине истории нет.
- Полный экспорт большого аккаунта — от минут до часа+.
- Только Telegram Desktop, в мобильных клиентах фичи нет.
- Первый запрос полного экспорта может быть отложен на срок ожидания.

### Инкрементальность — частичная

- Для **одного чата** диапазон дат выбрать можно (From/To).
- Для **массового** «export all data» диапазона **нет**. Открытый feature
  request: [tdesktop#30463](https://github.com/telegramdesktop/tdesktop/issues/30463)
  (открыт 2026-03-20, PR #30618 висит).
- Автоматизировать нельзя: GUI-only, CLI нет.

### Альтернатива с CLI — `tdl`

[docs.iyear.me/tdl](https://docs.iyear.me/tdl/guide/tools/export-messages/), Go,
MTProto под капотом.

```
tdl chat export -c CHAT -T time -i <unix_from>,<unix_to>
```

Также `-T id` / `-T last`, фильтры на уровне выражений. Пригодно для крона.
Формально это уже userbot — нужны api_id/api_hash.

## 2. Bot API

[core.telegram.org/bots/api](https://core.telegram.org/bots/api). Актуальная
версия на середину 2026 — **9.4**.

### Может ли бот читать всё в группе

Да, при одном из двух условий:

1. **Privacy mode выключен** через @BotFather (`/setprivacy` → Disable).
   По умолчанию включён: с ним бот видит только команды `/cmd`, реплаи на свои
   сообщения и сервисные события.
2. **Бот админ** — админы всегда получают всё независимо от privacy mode.

⚠️ **После смены privacy mode бота надо удалить из группы и добавить заново**,
иначе настройка не применится.

Никогда не получит: **сообщения других ботов** (защита от петель).

### Истории задним числом нет

Жёсткое ограничение. В Bot API нет метода «получить историю чата». Апдейты
хранятся на сервере **не дольше 24 часов** и удаляются, как только подтверждены
(`getUpdates` с `offset` выше их `update_id`).

Всё, что было до добавления бота, для него не существует.

### getUpdates vs webhook

Взаимоисключающие: пока стоит webhook, `getUpdates` возвращает ошибку.

- `getUpdates` — максимум 100 апдейтов за вызов, long polling через `timeout`
- webhook — только HTTPS, порты 443/80/88/8443, max 100 соединений
  (`max_connections`), фильтр типов через `allowed_updates`
- **Один webhook на бота** — ключевая боль для n8n

### Лимиты отправки

Входящие не лимитируются. Исходящие: ~30 msg/sec суммарно, ~1 msg/sec в один
чат, ~20 msg/min в группу.

## 3. Userbot / MTProto

Нужны **api_id + api_hash** с [my.telegram.org](https://my.telegram.org) и
авторизация по номеру. Сессия сохраняется в файл/строку.

### Статус библиотек — в 2026 много сдвигов

**Telethon (Python)**
- Репозиторий LonamiWebs/Telethon **архивирован 2026-02-21**, read-only
- Разработка на **Codeberg: `codeberg.org/Lonami/Telethon`**
- Стабильная **v1.44.0 от 2026-06-15**, в maintenance mode (багфиксы + layer)
- **v2 всё ещё альфа** (`2.0.0a0`, октябрь 2025), обратной совместимости нет
- Брать v1

**Pyrogram — мёртв.** Преемник: [Kurigram](https://github.com/KurimuzonAkuma/kurigram)
2.2.24 (2026-07-11), Python ≥3.8, LGPL-3.0, drop-in замена (`import pyrogram`
работает), поддерживает Gifts/Stories/Topics/Business. Второй форк —
`pyrotgfork`, менее популярен.

**GramJS (Node/TS) — архивирован 2026-07-14.** npm-пакет `telegram` не
поддерживается. Преемник — **`teleproto`**, «largely compatible» форк, миграция
= замена пакета.

**Итог:** Python → Telethon v1.44 или Kurigram 2.2.x. Node → teleproto.

### Чтение истории

```python
client.iter_messages(chat, limit=None, offset_id=..., reverse=True)  # Telethon
client.get_chat_history()                                            # Kurigram
```

Тянут **всю историю**, включая до вашего присоединения (для публичных групп),
пачками по 100. `min_id`/`offset_id` → инкремент тривиален.

**Здесь же полные link previews:** `MessageMediaWebPage` с `title`,
`description`, `site_name`, `url`, `photo`. Это главный аргумент за MTProto,
если задача про ссылки.

Плюс `search` по чату с фильтром `InputMessagesFilterUrl` — вытащить **только
сообщения со ссылками**, не выкачивая весь чат.

### Rate limits и бан

- `FloodWaitError` — троттлинг, не бан. От секунд до 24+ часов. Telethon сам
  спит, если ожидание <60 сек (`flood_sleep_threshold`).
- Точных лимитов Telegram не публикует. Практика: **1–2 сек между запросами
  держат стабильно бесконечно**.
- Реальный риск — **бан аккаунта**. Триггеры: свежий аккаунт, массовое
  вступление в чаты, резкий старт на высокой скорости, много `ResolveUsername`.
- Митигация: аккаунт с историей, не основной SIM, переменные задержки,
  постепенный разгон, одна сессия на аккаунт.
- Формально массовый сбор нарушает дух ToS.

## 4. TDLib

[core.telegram.org/tdlib](https://core.telegram.org/tdlib). Официальная C++
библиотека, на ней построены сами клиенты. Локальная БД, кэш, полный MTProto,
работает и как user, и как bot.

Плюс: официальность, надёжность, корректная обработка апдейтов, локальное
хранилище. Минус: тяжёлая, нужно компилировать, API низкоуровневый.

**Python-обёртки, актуальные в 2026:**
- **Pytdbot** — асинхронная, релиз 2026-02-22, рекомендована в README tdlib
- **tdjson** (AYMENJD) — низкоуровневый биндинг, апрель 2026, пребилты под
  Linux x64/ARM64, Windows x64, macOS M-series. Pytdbot построен поверх
- **aiotdlib** — тоже в рекомендациях, развивается медленнее
- **python-telegram** (alexander-akhmetov) — Python 3.10+, без Windows
- `tdlib-python` (JunaidBabu) — старый, не брать

⚠️ `telegram-bot-api` (self-hosted Bot API server на TDLib) снимает часть
лимитов Bot API (файлы до 2000 МБ), **но доступа к истории не даёт** — это всё
тот же Bot API.

## 5. n8n

### Штатные ноды

**Telegram Trigger** — только через webhook Bot API. 23+ типа апдейтов:
`message`, `channel_post`, `edited_message`, business-события, callback/inline
queries, poll, reactions, `chat_member`, chat boosts. По умолчанию подписан на
всё кроме Chat Member, Message Reaction, Message Reaction Count. Есть опция
Download Images/Files и фильтры по chat ID / user ID.

**Telegram node** — sendMessage, getFile, getChat, admin-операции. Метода
«получить историю» нет (его нет в Bot API).

### Ограничения

1. **Наследует всё от Bot API** → ретроспективный бэкфилл невозможен в принципе
2. **Один webhook на бота** → одна Telegram Trigger нода. Два воркфлоу на один
   чат — либо второй бот, либо Switch внутри
3. **Test URL перебивает Production URL**: пока тестируете, продакшн не
   получает события. Самая частая жалоба в issues
4. **Self-hosted**: обязательно `WEBHOOK_URL` (или `N8N_HOST`/`N8N_PROTOCOL`)
   на публичный адрес. За реверс-прокси нужен проксинг websocket, иначе
   редактор виснет на «listening». HTTPS обязателен
5. `chat_member`, реакции, boosts требуют админских прав бота

### Community-ноды с MTProto

Если нужен бэкфилл прямо в n8n:

- **`n8n-nodes-telegram-grampro`** — MTProto через teleproto. Есть **Get Chat
  History**, Read Messages History, фильтры по времени, шифрование сессии,
  встроенный rate limiting. Самая актуальная
- **`n8n-nodes-telegram-mtproto`** (veezex) — слушает новые сообщения
- **`n8n-nodes-telegram-mtproto-client`** — клиент-нода для user-аккаунта
- **Telepilot** — userbot-нода на TDLib

Все требуют установки community-пакетов на self-hosted и хранения строки сессии
userbot в credentials — по сути полный доступ к аккаунту лежит в n8n.

## 6. SaaS и бриджи

**Все построены на Bot API → истории не умеет ни один.** Модель «форварднул
сообщение боту → сохранилось».

**Zapier.** Триггер New Message. Ограничения: только ЛС и группы где бот
добавлен с выключенным privacy; **один бот = один Zap**; **не срабатывает на
сообщения владельца бота**; дропдаун Chat ID показывает только чаты, активные
за 24 часа.

**Make.com.** То же самое поверх Bot API, гибче по трансформациям, дешевле по
операциям.

**Readwise Reader.** Официального TG-бота нет (есть Discord-бот, extension,
email-inbox). Ходит community `@SaveToReadwiseBot`. Чистый путь — свой бот +
[Reader API](https://readwise.io/reader_api) (`POST /save`).

**Raindrop.io.** Официальный путь — **через IFTTT**: пишете `@IFTTT`-боту с
хештегом `#save`. Своего бота нет. Community
[OlegWock/raindrop-telegram-bot](https://github.com/OlegWock/raindrop-telegram-bot)
умер 2024-08-21. Есть нормальный [REST API](https://developer.raindrop.io/) —
свой мост пишется за вечер.

**Notion.** Официального бота нет. Только самописные на Notion API либо связка
через n8n/Make.

## Вывод под задачу

1. **Бэкфилл** — Telethon 1.44 с `InputMessagesFilterUrl`. Заодно отдаст полные
   link previews. 1–2 сек между итерациями, не с основного аккаунта.
   Быстрая альтернатива без кода — Desktop-экспорт чата в JSON и разбор
   `text_entities` (но previews дофетчивать самому).
2. **Непрерывный сбор** — n8n Telegram Trigger + бот-админ.

Держать userbot 24/7 не нужно — бот безопаснее и стабильнее.
