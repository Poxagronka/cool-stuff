# tg-links-secondbrain

Сборщик ссылок из телеграм-чата «cool stuff» в Obsidian-vault. История
разобрана разово через Telethon, новые ссылки ловит бот на Fly.io.

## Устройство

`src/tglinks/` — пайплайн: `canon` (канонизация url и дедуп) → `enrich`
(лестница обогащения, `sites` — точечные резолверы, `pagetext` — чистый текст
страницы) → `categorize` (Anthropic) → `vault` (заметки) → `gitvault` (push).
`app.py` — webhook и публичный портал (`portal` — индекс, `web` — страница,
`ask` — поиск словами через Haiku). `scripts/backfill.py` — разовая выгрузка.
Подробности в `research/` и `PLAN.md`, состояние среды — в `SETUP.md`.

## Тропинки, на которые уже наступили

- Bot API не видит историю, и это не обходится. Только MTProto →
  [knowledge/telegram/rules.md](knowledge/telegram/rules.md) R1
- Privacy mode бота отключать ДО добавления в группу, иначе он молчит →
  там же R2
- «cool stuff» — обычная группа, а не супергруппа: ссылок `t.me/c/` для неё
  не существует → там же R4
- HTTP 200 не значит настоящую страницу: challenge-заглушки приходят с кодом
  200 и правдоподобным title →
  [knowledge/scraping/rules.md](knowledge/scraping/rules.md) R1
- Выгрузку гонять с ноутбука, не с сервера: датацентровому IP магазины отдают
  меньше → там же R4
- `accept-encoding: br` без распаковщика ломает всё: сервер отдаёт сжатое,
  httpx не распакует, метаданные пустые → там же R7
- Instagram/TikTok/Spotify/App Store читаются только через свои эндпоинты,
  Pinterest не читается вообще → там же R8
- Контекст обрывается на соседней ссылке, иначе описание уедет не к той вещи →
  [knowledge/telegram/rules.md](knowledge/telegram/rules.md) R8
- Корневая ФС машины Fly эфемерна, состояние только на томе →
  [knowledge/deployment/rules.md](knowledge/deployment/rules.md) R1
- Health-check у Fly не даёт машине заснуть, поэтому их нет → там же R5
- Модель в поиске портала не пишет ответ, только вызывает `search` →
  [knowledge/portal/rules.md](knowledge/portal/rules.md) R1

## Локально

```
.venv/bin/python -m pytest tests/ -q
ruff check src scripts tests
```

Комментарии в коде — по-английски и с маленькой буквы (хук проверяет).
Эмодзи в исходниках только escape-последовательностями.
