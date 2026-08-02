# Непрерывный сбор: маленькая апка на Fly.io

Вместо n8n. Один Python-сервис, один контейнер, один том.

## Что уже есть у вас

В `/Users/poxagronka/abooks_bot` лежит **рабочий телеграм-бот на Fly.io в
webhook-режиме** — готовый шаблон, который можно копировать целиком.

### Креды Telegram — уже есть, регистрировать ничего не надо

`abooks_bot/.env` (файл в `.gitignore`, значения ниже замаскированы):

```
TG_API_ID=322694••••••      <- MTProto, ЭТО НУЖНО для Telethon-бэкфилла
TG_API_HASH=07ef4d••••••    <- MTProto, ЭТО НУЖНО для Telethon-бэкфилла
TG_BOT_TOKEN=866944••••••   <- бот @shoggoth-book-bot
TG_BOT_USERNAME=shoggo••••••
```

`api_id` / `api_hash` выданы на **аккаунт**, а не на приложение — их можно
переиспользовать для второго проекта без ограничений. Шаг «зарегистрироваться
на my.telegram.org» из плана вычёркивается.

`TG_BOT_TOKEN` переиспользовать **не стоит**: один бот = один webhook URL.
Если тот же токен привязать к новому серверу, книжный бот отвалится. Завести
отдельного бота у BotFather (30 секунд) и положить его токен в секреты Fly.

### fly.toml как шаблон

Из `abooks_bot/fly.toml`, релевантная часть:

```toml
app = "shoggoth-book-bot"
primary_region = "fra"

[env]
  BOT_MODE = "webhook"
  BOT_PORT = "8443"
  WEBHOOK_URL = "https://shoggoth-book-bot.fly.dev"

[http_service]
  internal_port = 8443
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 0

[mounts]
  source = "abooks_data"
  destination = "/data"

[[vm]]
  size = "performance-8x"
  memory = "16384"
```

`performance-8x` / 16 ГБ — под перекодирование аудиокниг. Сборщику ссылок
столько не нужно на два порядка.

## fly.toml для сборщика ссылок

```toml
app = "tg-links-collector"
primary_region = "fra"

[build]
  dockerfile = "Dockerfile"

[env]
  BOT_MODE = "webhook"
  BOT_PORT = "8443"
  WEBHOOK_URL = "https://tg-links-collector.fly.dev"
  DB_PATH = "/data/links.db"

[http_service]
  internal_port = 8443
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

[mounts]
  source = "links_data"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512"
```

Секреты (в репозиторий не кладутся):

```bash
fly secrets set TG_BOT_TOKEN=... ANTHROPIC_API_KEY=... GITHUB_TOKEN=...
```

### Про масштаб и деньги

`shared-cpu-1x` / 256 МБ входит в бесплатные ресурсы Fly. 512 МБ взято с
запасом: `curl_cffi` и `trafilatura` на тяжёлой странице съедают заметно
больше, чем эхо-бот, а OOM-kill на 256 МБ ловить неприятно.

`auto_stop_machines = "suspend"` + `min_machines_running = 0` — машина
засыпает между сообщениями и просыпается на входящий webhook. Для чата, где
ссылку кидают несколько раз в день, реальное потребление около нуля.

Важное отличие от `abooks_bot`: там стоит `auto_stop_machines = false`, потому
что бот сам себя останавливает через Machines API после долгой задачи. Здесь
задачи короткие — пусть Fly управляет сам.

Холодный старт из suspend — доли секунды, Telegram успевает в свой таймаут.
Из полностью остановленного состояния — несколько секунд, тоже нормально:
Telegram ретраит webhook.

**Том обязателен.** Файловая система машины Fly эфемерна; без `[mounts]`
SQLite с историей ссылок пропадёт при первом же деплое. Тома привязаны к
одному региону и одной машине — для однопользовательского бота это ровно то,
что нужно, но масштабироваться горизонтально с ним нельзя.

## Что делает сервис

```
POST /webhook от Telegram
  -> достать URL из text_entities (type: url и text_link)
     плюс message.link_preview_options.url
  -> канонизация (см. 02)
  -> дедуп по трём ключам в SQLite на томе
  -> если новый: лестница обогащения (см. 03, 04)
  -> Claude, structured output (см. 05)
  -> запись .md в vault (см. ниже)
  -> реакция на сообщение в чате как подтверждение
```

Ответ на webhook отдавать **сразу 200**, работу делать в фоне
(`asyncio.create_task` / `BackgroundTasks`). Telegram ждёт ответа считанные
секунды и при таймауте ретраит — иначе получите дубли при медленном
обогащении.

Реакция-эмодзи на исходное сообщение вместо ответного сообщения: подтверждение
видно, чат не засоряется.

## Как заметки попадают в Obsidian

Три варианта, по возрастанию геморроя:

**1. Git (рекомендуется).** Vault — приватный репозиторий на GitHub. Сервис
клонирует его на том при старте, коммитит новую заметку, пушит. Локально
Obsidian Git подтягивает.

Плюсы: история версий, работает на любом устройстве, никаких дыр наружу.
Минусы: конфликты, если правите vault с двух сторон одновременно (для
однопользовательского сценария практически не случается).

Токен — fine-grained PAT только на один репозиторий, в `fly secrets`.

**2. Obsidian Local REST API.** Плагин поднимает HTTP-сервер прямо в Obsidian.
Сервис на Fly дёргает его и создаёт заметку.

Проблема очевидна: ваш ноутбук должен быть доступен из интернета и включён.
Решается через Tailscale или Cloudflare Tunnel, но это лишний движущийся
кусок, который будет отваливаться.

**3. Промежуточная очередь.** Сервис пишет только в SQLite на томе, отдаёт
`GET /pending`; локальный скрипт по расписанию забирает и раскладывает в vault.

Надёжнее всех и не требует доступа снаружи, но появляется ручной шаг.

Для одного человека **вариант 1** — правильный компромисс. Вариант 3 разумен,
если vault лежит в iCloud/Obsidian Sync и git туда не заводится.

## Настройка бота в группе

- Бот должен быть **администратором** группы, либо с **выключенным privacy
  mode** (BotFather → `/setprivacy` → Disable). Иначе он видит только команды,
  адресованные лично ему, и ни одной ссылки
- **После смены privacy mode бота надо удалить из группы и добавить заново** —
  настройка применяется в момент добавления. Это ловушка, на которой теряют час
- Один бот = один webhook URL. `setWebhook` перезаписывает предыдущий молча
- Ссылки приходят в `message.entities` (`type: "url"` — голый текст) и
  `type: "text_link"` (гиперссылка, URL в поле `url`). Забыть про второй —
  значит потерять все ссылки, вставленные под текстом
- Превью, которое Telegram сам подтянул, лежит в `link_preview_options` —
  бесплатные метаданные, можно использовать как нулевой тир обогащения

## Деплой

```bash
fly launch --no-deploy          # сгенерирует fly.toml, поправить руками
fly volumes create links_data --region fra --size 1
fly secrets set TG_BOT_TOKEN=... ANTHROPIC_API_KEY=... GITHUB_TOKEN=...
fly deploy
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://tg-links-collector.fly.dev/webhook"
```

Проверить, что webhook встал:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Поле `last_error_message` — первое место, куда смотреть, когда бот молчит.

## Чего этот сервис НЕ делает

Бэкфилл истории. Bot API не имеет метода для чтения прошлых сообщений — ни
сейчас, ни в перспективе (24 часа хранения обновлений, дальше данные для бота
не существуют).

История выгружается один раз локально через Telethon с вашего пользовательского
аккаунта (шаг 1 плана), результат заливается в тот же SQLite. Гонять Telethon-
юзербот на сервере постоянно не нужно и рискованно для аккаунта.
