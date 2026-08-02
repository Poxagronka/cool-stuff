# Что уже настроено и что осталось

## Готово

| Что | Где |
|---|---|
| Репозиторий пайплайна | `github.com/Poxagronka/tg-links-secondbrain` (приватный) |
| Репозиторий vault | `github.com/Poxagronka/links-vault` (приватный) |
| Локальный vault | `~/links-vault` |
| Приложение на Fly | `tg-links-collector.fly.dev`, регион fra |
| Том | `links_data`, 1 ГБ, fra |
| Deploy key | зарегистрирован на `links-vault` с правом записи; приватная часть в `~/.ssh/tg-links-vault-deploy` и в секретах Fly |
| Секреты Fly | `ANTHROPIC_API_KEY`, `SSH_KEY`, `VAULT_REPO`, `WEBHOOK_SECRET` |
| Креды в `.env` | `TG_API_ID`, `TG_API_HASH` (из abooks_bot), `ANTHROPIC_API_KEY` (из appodeal-life) |

Проверено: `GET /health` отвечает 200, при старте приложение успешно клонирует
vault по deploy key.

## Осталось три шага

### 1. Узнать id чата

Разовый вход в Telegram, спросит номер телефона и код:

```
cd ~/tg-links-secondbrain
.venv/bin/python scripts/backfill.py --list-chats
```

Найти в списке «cool stuff», вписать id в `.env`:

```
TG_CHAT=-100...
```

Сессия сохранится в `data/backfill.session`, второй раз код не понадобится.

### 2. Разведка перед выгрузкой

```
.venv/bin/python scripts/backfill.py --recon
```

Покажет, сколько уникальных ссылок и топ доменов. **От этой цифры зависит,
имеет ли смысл всё остальное** — если ссылок окажется полторы сотни, проще
разобрать руками.

Дальше, если объём оправдывает:

```
.venv/bin/python scripts/backfill.py --dump          # в sqlite
.venv/bin/python scripts/backfill.py --process --limit 20   # проба на 20 штуках
```

Посмотреть, что получилось в `data/vault/links/`, и если нравится — снять
`--limit`. Гонять с ноутбука, а не с сервера: домашний IP резидентный, магазины
отдают ему метаданные там, где датацентру не отдают.

### 3. Бот для новых ссылок

Создать отдельного бота (не переиспользовать книжного):

1. `@BotFather` → `/newbot`
2. `/setprivacy` → выбрать бота → **Disable** — иначе он не увидит ссылки
3. Добавить бота в «cool stuff» **после** смены privacy: настройка
   применяется в момент добавления
4. Токен положить в оба места:

```
cd ~/tg-links-secondbrain
echo 'TG_BOT_TOKEN=<токен>' >> .env
flyctl secrets set TG_BOT_TOKEN=<токен> TG_CHAT=<id чата>
```

Второй командой машина передеплоится сама. Затем повесить webhook:

```
source .env
curl "https://api.telegram.org/bot$TG_BOT_TOKEN/setWebhook?url=https://tg-links-collector.fly.dev/webhook&secret_token=$WEBHOOK_SECRET"
curl "https://api.telegram.org/bot$TG_BOT_TOKEN/getWebhookInfo"
```

В `getWebhookInfo` смотреть на `last_error_message` — это первое место, куда
идти, если бот молчит.

## Как пользоваться

Кинуть ссылку в чат. Бот ставит реакцию: «глаза» — видел, но ссылка уже есть;
«рука с ручкой» — завёл заметку. Заметка уезжает коммитом в `links-vault`.

Локально подтянуть: `cd ~/links-vault && git pull`. В Obsidian поставить плагин
Obsidian Git, чтобы делал это сам.

Открыть vault в Obsidian: «Open folder as vault» → `~/links-vault`. Включить
ядровой плагин Bases, тогда заработают представления из `bases/`.

## Обслуживание

```
flyctl logs -a tg-links-collector          # что происходит
flyctl status -a tg-links-collector        # спит машина или нет
curl https://tg-links-collector.fly.dev/health
```

Машина настроена на `auto_stop_machines = "suspend"`: между сообщениями спит,
просыпается на webhook за доли секунды.

## Про стоимость

Не бесплатно, вопреки исходному замыслу — вы сами выбрали Anthropic API вместо
локальной модели.

- Fly: `shared-cpu-1x`/512 МБ со сном + том 1 ГБ. Копейки в месяц, добавится
  к существующему счёту за `abooks_bot`
- Anthropic: примерно $0.002 за ссылку. Разбор истории — единоразово порядка
  $2–4 на пару тысяч ссылок, дальше центы в месяц
- GitHub, Obsidian: бесплатно

Если захотите вернуться к нулю: в `categorize.py` вся работа с Anthropic
изолирована в одном модуле, подменить на локальную модель — правка в одном
файле.
