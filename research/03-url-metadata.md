# Метаданные из URL: oEmbed, парсинг, хостед-сервисы

Проверено 2026-08-02 живыми пробами и PyPI JSON API.

## Главный вывод: oEmbed первым, скрейпинг потом

Распространённая ошибка — сразу лезть парсить метатеги. Для топовых соцсетей
есть oEmbed: бесплатно, официально, стопроцентно надёжно.

## oEmbed — жив, и лучше чем в 2023

Все результаты — живые пробы, без токенов и кук.

| Провайдер | Endpoint | Auth | Анонимно |
|---|---|---|---|
| **YouTube** | `youtube.com/oembed?url=...&format=json` | нет | да |
| **Vimeo** | `vimeo.com/api/oembed.json?url=...` | нет | да |
| **Twitter/X** | `publish.twitter.com/oembed` → 301 → `publish.x.com/oembed` | **нет** | да, **НЕ мёртв** |
| **TikTok** | `www.tiktok.com/oembed?url=...` | нет | да |
| **Instagram** | `graph.facebook.com/v25.0/instagram_oembed?url=...` | **нет с 2026-06-15** | да, 1000 req/hour |
| **Facebook** | `graph.facebook.com/v25.0/oembed_page` / `oembed_video` | нет | да (`oembed_post` капризен) |
| **Reddit** | `www.reddit.com/oembed?url=...` | нет | да (битый URL → **403 HTML**) |
| **SoundCloud** | `soundcloud.com/oembed?format=json&url=...` | нет | да |
| **Spotify** | `open.spotify.com/oembed?url=...` | нет | да |
| **Flickr** | `flickr.com/services/oembed?format=json&url=...` | нет | да |
| **Giphy** | `giphy.com/services/oembed?url=...` | нет | да |
| **Bluesky** | `embed.bsky.app/oembed?url=...` | нет | да |
| **Mastodon** | `{instance}/api/oembed?url=...` | нет | да (в ядре, но НЕ в providers.json) |
| **Figma** | `www.figma.com/api/oembed?url=...` (не `api.figma.com`!) | нет | да |
| **Loom** | `www.loom.com/v1/oembed?url=...` | нет | да |
| Twitch | ~~`api.twitch.tv/v5/oembed`~~ | — | МЁРТВ с v5 (2022) |
| Threads | — | — | token-gated / нет |
| Substack / Notion / GitHub gists | — | — | никогда не было |
| Medium | `medium.com/services/oembed?url=...` | нет | Cloudflare 403 с сервера |

### Две новости, ломающие расхожие представления

**1. X/Twitter oEmbed работает анонимно.** Проверено на `x.com/jack/status/20` —
возвращает текст твита, автора, готовый blockquote. Миф о смерти оттого, что
`publish.twitter.com` отдаёт **301 с пустым телом**; без `follow_redirects`
выглядит как поломка. Реальный хост теперь `publish.x.com/oembed`.

**2. Meta сняла токен-гейт 2026-06-15.** Шесть лет `instagram_oembed` требовал
`oembed_read` + App Review. Теперь работает без `access_token`. Проверено: без
токена приходит либо embed HTML, либо честный `code: 24 / Media Not Found` —
не ошибка авторизации.

### providers.json

`oembed.com/providers.json`, `last-modified: 2026-08-02`, **366 провайдеров /
372 endpoint'а**, репо `iamcal/oembed` активно (PR #929–932 за конец июля).

Но список **аккретивный** — мёртвые endpoint'ы никто не чистит, Meta там до сих
пор прибита к `v16.0` (давно за пределами двухлетнего окна депрекации Meta).
Переписывать на `v25.0`+ руками.

### Библиотека — одна живая

```bash
pip install micawber   # 0.7.0, 2026-07-05, 680 звёзд, 0 открытых issue
```

```python
from micawber import Cache, bootstrap_oembed
registry = bootstrap_oembed(cache=Cache())      # качает 162 КБ providers.json
meta = registry.request('https://youtu.be/dQw4w9WgXcQ')
html = registry.parse_text('смотри https://youtu.be/dQw4w9WgXcQ')
```

Обязательно подключать `Cache` — иначе 162 КБ на каждый холодный старт. Есть
`bootstrap_basic()`, `bootstrap_noembed()`, `bootstrap_iframely()`, интеграции
с Django и Flask.

Альтернатива `oembedpy` 0.9.0 (2025-12-27), но 8 звёзд. Всё остальное
(`pyembed`, `python-oembed`, `pyoembed`, `django-oembed`) мертво с 2014–2017.

**Честно: для 15 реально важных сайтов словарь из 15 шаблонов + `httpx` лучше
любой библиотеки.** Реестр устарел ровно там, где больнее всего — версии Meta,
дубль Twitter/X, отсутствие Mastodon.

### Три разные формы «не найдено»

YouTube 404 plaintext, X 404 HTML, Bluesky 404 plaintext, Reddit **403 HTML**,
Meta 400 JSON. **Никогда не парсить тело как JSON при не-200.**

### Агрегаторы

- **noembed.com** — отвечает 200 без ключа, но код заморожен с января 2021,
  55 открытых issue, **42 провайдера** образца 2016: нет TikTok, Bluesky,
  Instagram, Reddit, Spotify. `x.com/...` → `no matching providers found`.
  Фолбэк, не фундамент
- **Iframely** — `iframe.ly/api/oembed?url=...&api_key=...`, без ключа 403.
  Серьёзный коммерческий вариант, есть self-hosted ядро
- **Embedly** — жив, `api.embed.ly/1/oembed`, ~$119/мес за 10k Embed + 10k
  Extract. Python-клиент `embedly` 0.5.0 из 2013 — дёргать REST напрямую

## Python-библиотеки парсинга: кто жив

| Пакет | Версия | Последний релиз | Статус |
|---|---|---|---|
| **trafilatura** | **2.2.0** | **2026-07-31** | Эталон. 6.4k звёзд |
| **htmldate** | 1.10.0 | 2026-06-01 | жив, тот же автор (adbar) |
| **courlan** | 1.4.0 | 2026-06-01 | жив, тот же автор |
| **newspaper4k** | 0.9.6 | 2026-07-19 | живой форк newspaper3k, 1.1k звёзд |
| **goose3** | 3.1.22 | 2026-07-23 | жив, но узкий (precision высокая, recall низкий) |
| **metadata-parser** | 1.0.0 | 2025-08-30 | жив, 1.0 — breaking-релиз |
| **readability-lxml** | 0.8.4.1 | 2025-05-03 | вяло, но работает |
| **linkpreview** | 0.12.1 | 2025-08-15 | мелкий (54 звезды), актуальный |
| **extruct** | 0.18.0 | 2024-11-08 | ПОЛУДОХЛЫЙ: коммит 2025-03-24, релиза 21 мес |
| **newspaper3k** | 0.2.8 | **2018-09-28** | МЁРТВ |
| **opengraph-py3** | 0.71 | **2018-02-27** | МЁРТВ |
| python-oembed / pyembed / webpreview / lassie / dragnet | — | 2016–2022 | МЁРТВЫ |

Про newspaper3k: коммиты в репо есть (`add swiftproxy`, `remove webshare`) — это
спам-правки README со ссылками на прокси-спонсоров, кода не трогают 8 лет.

### trafilatura покрывает почти всё сразу

Проверено по исходникам: `trafilatura/metadata.py` читает `og:*`, `twitter:*`
**и** `<script type="application/ld+json">` (JSON-LD переопределяет остальное).

Поля `Document` (`settings.py:229`):

```
title author url hostname description sitename date categories tags
fingerprint id license body comments commentsbody raw_text text
language image pagetype filedate
```

```bash
pip install "trafilatura[all]"   # + htmldate, courlan, py3langid, brotli, zstandard
```

```python
import trafilatura
html = trafilatura.fetch_url(url)
meta = trafilatura.extract_metadata(html).as_dict()      # OG + Twitter + JSON-LD
text = trafilatura.extract(html, output_format="markdown",
                           with_metadata=True, include_tables=True)
```

### Когда нужен extruct

Только для **microdata, RDFa, microformats, Dublin Core** — например товарные
`schema.org/Product` с ценой, если их нет в JSON-LD. Альтернатив уровня extruct
нет.

```python
import extruct
data = extruct.extract(html, base_url=url,
                       syntaxes=["json-ld","microdata","opengraph","rdfa","dublincore"])
```

`turbohtml` 1.5.1 (2026-07-27) заявляет `structured_data()` на C-ядре, но репо
2 месяца и 19 звёзд — смотреть, не ставить в прод.

### Рекомендуемый стек

```bash
pip install "trafilatura[all]" extruct micawber curl_cffi selectolax
```

- `micawber` — oEmbed, первый тир
- `trafilatura` — метаданные + текст статьи одним проходом
- `extruct` — добить structured data где нужен товар/рецепт/событие
- `curl_cffi` — транспорт (см. 04-anti-bot.md)
- `selectolax` 0.4.11 (2026-07-15) — быстрый парсинг head своими руками

## Бенчмарки экстракторов

Официальный бенч trafilatura (750 документов, 2236 text / 2250 boilerplate), F1:

| Пакет | Precision | Recall | F1 | Замедление |
|---|---|---|---|---|
| trafilatura (standard) | 0.914 | 0.904 | **0.909** | 7.1x |
| trafilatura (precision) | 0.932 | 0.874 | 0.902 | 9.4x |
| trafilatura (fast) | 0.914 | 0.886 | 0.900 | **4.8x** |
| readabilipy | 0.877 | 0.870 | 0.874 | 248x |
| news-please | 0.898 | 0.734 | 0.808 | 61x |
| readability-lxml | 0.891 | 0.729 | 0.801 | 5.8x |
| goose3 | **0.934** | 0.690 | 0.793 | 22x |
| boilerpy3 | 0.814 | 0.744 | 0.777 | 4.1x |
| justext | 0.865 | 0.650 | 0.742 | 5.2x |
| newspaper3k | 0.895 | 0.593 | 0.713 | 12x |
| inscriptis | 0.534 | 0.959 | 0.686 | 3.5x |

Таблица датирована 2022-05-18 и сравнивает trafilatura 1.2.2 — свежее
официальных цифр нет.

**Независимая работа, февраль 2026** — «Beyond a Single Extractor»
([arxiv 2602.19548](https://arxiv.org/html/2602.19548v1)), Common Crawl:
однозначного победителя на общем вебе нет, но по типам страниц расхождение
огромное. Таблицы: resiliparse **11.9** vs trafilatura **3.7** vs jusText **1.6**
(jusText таблицы просто выкидывает). Экстракторы захватывают **разные
подмножества страниц** — после фильтрации пересечение всего 39%.

Практика: для «превью ссылки в чате» разница между trafilatura и resiliparse
несущественна. Если сохраняете текст статьи для поиска — `resiliparse` 1.0.9
(2026-07-20) вторым проходом для табличных страниц.

## Хостед-сервисы: цены на август 2026

### Специалисты по link preview

| Сервис | Free | Дешёвый платный | $/1k | JS/анти-бот |
|---|---|---|---|---|
| **LinkPreview.net** | 60 req/hour (~43k/мес), только personal | **$8/мес** = 200 req/hr (~144k) | **$0.06** | нет |
| **urlmeta** | 500 req/мес | $9/мес = 25k | $0.36 | нет; сайт с копирайтом 2024 — риск |
| **jsonlink.io** | 100 кредитов | $15/мес = 50k | $0.30 | markdown/скриншот = 2 кредита |
| **Peekalink** | 50 req/hour | $42/мес (годовой) = 500 req/hr | $0.12–0.30 | лимит почасовой, бёрсты страдают |
| **Microlink** | 25 req/день; аноним ~25 req/min | Pro $49/мес = 46k–420k | $0.12–1.07 | да, реальный браузер + скриншоты/PDF |
| **Iframely** | 2k hits/мес, 1 домен | $49/мес = 25k hits | $1.96 | «hit» = час активности URL |
| **OpenGraph.io** | 100 запросов | $25 разово = 50k кредитов | **$8.40–16.40** с JS+proxy | множители: render +10, proxy +10…+30 |
| **Diffbot** | **10k кредитов/мес** (лучший free) | $299/мес = 250k | $2.39 | 5 req/**min** на free |
| **Jina Reader** (r.jina.ai) | **20 RPM без ключа, бесконечно**; с ключом 500 RPM | PAYG | **~$0.10/1k страниц** | слаб против анти-бота |

По Iframely два источника разошлись (free 1k vs 2k hits; $49 = 10k vs 25k) —
перед закупкой проверить прайс самому.

### Рекомендации по объёму

- **~10k/мес обычных OG:** Diffbot Free ($0), если терпите 5 req/min. Иначе
  **LinkPreview Basic $8/мес**. Или **Jina Reader без ключа — $0 навсегда**
  при 20 RPM (~864k/мес), если устраивает markdown и отсутствие SLA
- **~100k/мес:** LinkPreview Pro $25/мес ($0.035/1k). С рендерингом — Scrapfly
  Discovery $30 или Microlink Pro $49
- **Жёсткий анти-бот:** см. 04-anti-bot.md

## Итог

1. **oEmbed сначала** (micawber 0.7.0) — бесплатно, идеально, покрывает топ
   соцсетей. X и Instagram снова открыты анонимно
2. **trafilatura 2.2.0** парсит OG + Twitter cards + JSON-LD + текст статьи
   одним вызовом. `extruct` — добить microdata/RDFa
3. **newspaper3k мёртв** (2018), `opengraph-py3` мёртв (2018). Если встретите
   в туториале — туториал устарел
