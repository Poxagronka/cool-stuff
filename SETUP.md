# Что настроено

Всё работает автоматически. Ручных шагов не осталось.

## Инфраструктура

| Что | Где |
|---|---|
| Репозиторий пайплайна | `github.com/Poxagronka/tg-links-secondbrain` (приватный) |
| Репозиторий vault | `github.com/Poxagronka/links-vault` (приватный) |
| Локальный vault | `~/links-vault` |
| Приложение на Fly | `tg-links-collector.fly.dev`, регион fra |
| Том | `links_data`, 1 ГБ, fra |
| Бот | `@coolstuff_links_bot`, privacy mode отключён, в группе |
| Чат | «cool stuff», id `-4092567497` (обычная группа, не супергруппа) |
| Deploy key | на `links-vault` с правом записи; приватная часть в `~/.ssh/tg-links-vault-deploy` и в секретах Fly |
| Секреты Fly | `ANTHROPIC_API_KEY`, `SSH_KEY`, `VAULT_REPO`, `WEBHOOK_SECRET`, `TG_BOT_TOKEN`, `TG_CHAT` |
| Сессия Telethon | `data/backfill.session`, вход выполнен |

## Что проверено вживую

Ссылка отправлена в группу, и она прошла весь путь: webhook принял апдейт,
метаданные забрались со страницы, Anthropic вернул категорию и теги, заметка
закоммитилась в `links-vault`, бот поставил реакцию. Логи и заметка на месте.

## Как пользоваться

Кинуть ссылку в чат — дальше само. Бот ставит реакцию: «глаза» — ссылка уже
была, «рука с ручкой» — завёл заметку.

Локально: `cd ~/links-vault && git pull`. В Obsidian поставить плагин Obsidian
Git, чтобы тянул сам. Открыть vault: «Open folder as vault» → `~/links-vault`,
включить ядровой плагин Bases — заработают представления из `bases/`.

Облако тегов — встроенная панель тегов Obsidian: свойство `tags` во
фронтматтере распознаётся как настоящие теги.

## Обслуживание

```
flyctl logs -a tg-links-collector          # что происходит
flyctl status -a tg-links-collector        # спит машина или нет
curl https://tg-links-collector.fly.dev/health
```

Машина на `auto_stop_machines = "suspend"`: между сообщениями спит,
просыпается на webhook за доли секунды.

Если бот замолчал — первым делом сюда:

```
source .env
curl "https://api.telegram.org/bot$TG_BOT_TOKEN/getWebhookInfo"
```

Смотреть `last_error_message`.

## Повторная выгрузка истории

Разово уже сделана. Если понадобится ещё раз:

```
.venv/bin/python scripts/backfill.py --recon     # посчитать
.venv/bin/python scripts/backfill.py --dump      # в sqlite
.venv/bin/python scripts/backfill.py --process   # обогатить и написать заметки
```

Гонять с ноутбука, а не с сервера: домашний IP резидентный, магазины отдают
ему метаданные там, где датацентру не отдают.

## Про стоимость

Не бесплатно, вопреки исходному замыслу — Anthropic вместо локальной модели
выбран сознательно.

- Fly: `shared-cpu-1x`/512 МБ со сном плюс том 1 ГБ. Копейки в месяц, добавится
  к существующему счёту за `abooks_bot`
- Anthropic: примерно $0.002 за ссылку. Разбор истории из 388 ссылок обошёлся
  меньше чем в доллар, дальше центы в месяц
- GitHub, Obsidian: бесплатно

Если захочется вернуться к нулю: работа с Anthropic изолирована в
`categorize.py`, подмена на локальную модель — правка в одном файле.
