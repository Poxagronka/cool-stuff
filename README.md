# Telegram → Obsidian: база ссылок из группового чата

Ресерч от 2026-08-02. Задача: в групповом чате годами кидают ссылки (шмотки,
техника, клёвые сайты, статьи), всё тонет и не ищется. Нужна база с
категориями и нормальным поиском.

## Итог в пяти строчках

1. История и новые сообщения — **две разные технологии**. Bot API историю не
   отдаёт в принципе, нужен userbot один раз.
2. Обогащение: **oEmbed → UA соцкраулеров → curl_cffi**. Браузер почти не нужен.
3. Главная мина: дохлые короткие ссылки редиректят на главную, а не в 404.
4. Категоризация LLM стоит ~$3 на пару тысяч ссылок. Не то, на чём экономить.
5. Obsidian: одна заметка на ссылку + Bases + Omnisearch. Dataview не ставить.

## Навигация

| Файл | О чём |
|---|---|
| [PLAN.md](PLAN.md) | План внедрения по шагам, с чего начинать |
| [research/01-telegram-extraction.md](research/01-telegram-extraction.md) | Как достать сообщения: экспорт, Bot API, Telethon, TDLib |
| [research/02-url-canonicalization.md](research/02-url-canonicalization.md) | Нормализация URL, ClearURLs, резолв редиректов, дедуп |
| [research/03-url-metadata.md](research/03-url-metadata.md) | oEmbed, парсинг метатегов, хостед-сервисы и цены |
| [research/04-anti-bot.md](research/04-anti-bot.md) | Заблокированные сайты, TLS-фингерпринт, прокси, RU-маркетплейсы |
| [research/05-llm-categorization.md](research/05-llm-categorization.md) | Таксономия, промптинг, расчёт стоимости, склейка контекста |
| [research/06-obsidian-vault.md](research/06-obsidian-vault.md) | Структура vault, frontmatter, Bases, поиск, плагины, синк |
| [research/07-ready-made-tools.md](research/07-ready-made-tools.md) | Karakeep, Linkwarden, Raindrop, готовые боты и плагины |
| [research/08-archiving.md](research/08-archiving.md) | monolith, SingleFile, ArchiveBox, Wayback SPN |
| [research/09-deployment-flyio.md](research/09-deployment-flyio.md) | Апка на Fly.io для новых ссылок, готовые креды, шаблон из abooks_bot |

## Две стратегии

**Готовое (почти без кода).** Karakeep + karakeepbot + плагин Karakeep Sync.
Все три компонента живые и упомянуты в официальной документации проекта.
Историю чата всё равно придётся тащить Telethon'ом отдельно.
→ [07-ready-made-tools.md](research/07-ready-made-tools.md)

**Своё (полный контроль).** Python-пайплайн: Telethon → канонизация →
обогащение → LLM-категоризация → генерация `.md` в vault. Дальше маленькая
апка на Fly.io ловит новые ссылки — шаблон копируется из `abooks_bot`.
→ [PLAN.md](PLAN.md), [09-deployment-flyio.md](research/09-deployment-flyio.md)

Они не взаимоисключающие: бэкфилл одинаковый в обоих случаях.

## Что проверено эмпирически

Часть выводов получена не из документации, а живыми пробами 2026-08-02:
цены Claude API, поведение сокращателей ссылок (HEAD vs GET), таблица
UA соцкраулеров по сайтам, замеры monolith, статус oEmbed-провайдеров.
Такие места помечены в тексте.

Даты релизов библиотек взяты из PyPI/npm/GitHub API на 2026-08-02, а не
по памяти — в этой нише за 2025–2026 умерло много популярных пакетов
(newspaper3k, Pyrogram, GramJS, undetected-chromedriver, Unalix).

## Заметка про язык

Глобальный CLAUDE.md требует английский для `knowledge/`. Здесь сознательно
русский: это личная папка с ресерчем, который целиком велся на русском, и
перевод исказил бы формулировки. Папка называется `research/`, не `knowledge/`.
