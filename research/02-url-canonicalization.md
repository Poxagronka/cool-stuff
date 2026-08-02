# Канонизация URL, резолв редиректов, дедуп

Проверено 2026-08-02, часть выводов — эмпирические прогоны, не документация.

## Порядок операций

```
раскрыть ClearURLs redirections (офлайн)
  → RFC-нормализация
  → ClearURLs rules + rawRules
  → свои site-specific канонизаторы
  → сортировка параметров (ПОСЛЕДНИМ шагом)
```

Сортировка последней, потому что `rawRules` работают на сырой строке.

## Библиотеки: версии на 2026-08-02

| Пакет | Версия | Дата | Роль |
|---|---|---|---|
| `url-normalize` | **3.0.0** | 2026-04-25 | RFC 3986 + IDN + CLI |
| `w3lib` | **2.4.1** | 2026-03-20 | `canonicalize_url`, `url_query_cleaner` |
| `courlan` | **1.4.0** | 2026-06-01 | нормализация + трекеры + `UrlStore` |
| `yarl` | 1.24.5 | 2026-07-20 | immutable URL, ядро aiohttp |
| `furl` | 2.1.4 | 2025-03-09 | mutable, удобно для ad-hoc |
| `urlcanon` | 0.3.1 | **2019-07-02** | стар, но уникален SSURT |
| `Unalix` | 0.9 | 2021 | МЁРТВ — **репо архивировано 2022-09-13** |
| `url-sanitize` | 2.0.2 | 2026-06-11 | НЕ РАБОТАЕТ — shim, требует Rust-бинарь |

```bash
pip install url-normalize w3lib courlan yarl furl urlcanon
```

## Измеренное поведение

Один вход: `HTTPS://WWW.Example.com:443/a/../b/?utm_source=x&b=2&a=1#frag`

```
url_normalize                 -> https://www.example.com/b/?utm_source=x&b=2&a=1#frag
url_normalize(filter_params=True)
                              -> https://www.example.com/b/#frag      <-- убил a=1 и b=2
w3lib.canonicalize_url        -> https://www.example.com:443/a/../b/?a=1&b=2&utm_source=x
urlcanon.whatwg               -> https://www.example.com/b/?utm_source=x&b=2&a=1#frag
urlcanon ssurt                -> com,example,www,//https:/b/?utm_source=x&b=2&a=1#frag
courlan.clean_url             -> https://www.example.com/a/../b/?a=1&b=2#frag
courlan.normalize_url(strict) -> https://www.example.com/a/../b/
```

### Три ловушки, которые это вскрывает

**1. `w3lib.canonicalize_url` НЕ убирает дефолтный порт и НЕ резолвит `..`.**
Он только сортирует параметры, чинит регистр процент-кодирования и сносит
фрагмент. Это *сортировщик*, не RFC-нормализатор. Никогда не использовать
в одиночку как ключ дедупа.

**2. `url_normalize(filter_params=True)` — allowlist из 4 доменов.**
Исходник `url_normalize/param_allowlist.py`, 48 строк:
`{"google.com":["q","ie"], "baidu.com":["wd","ie"], "bing.com":["q"],
"youtube.com":["v","search_query"]}`.

На любом другом домене выкидывает **все** параметры. `?id=9&page=2` схлопнется
в тот же ключ, что `?id=17`. Не включать без явного `param_allowlist`.

**3. `courlan.check_url()` применяет спам-фильтры** и может вернуть `None`
(например, для `example.com`). На реальном URL работает:

```python
check_url("https://www.zalando.de/x.html?utm_medium=cpc&size=42&color=red")
# -> ('https://www.zalando.de/x.html?color=red&size=42', 'zalando.de')
```

**courlan — лучший однострочник** для дедупа чат-ссылок: срезает utm/gclid/
fbclid, сортирует, лоуркейсит, возвращает `(url, domain)`. Минус: сносит
фрагменты и не резолвит `..`.

### `urlcanon` и SSURT

Последний релиз 2019, но ставится и работает на 3.11. Уникальная ценность —
**SSURT** (`com,example,www,//https:/path`): сортируемая, префиксно-искомая
сериализация. Если захочется range-запросов «все ссылки с этого домена/поддерева»
в SQLite — храните SSURT второй индексированной колонкой.

### Изменения API `url-normalize`

- **2.0.0** (2025-03-29): дефолтная схема `http`→**`https`**; IDNA 2008 + UTS46;
  **удалён `sort_query_params`** (порядок параметров семантически значим);
  дропнут py2
- **2.1.0**: CLI. **2.2.0**: `default_domain=`. **2.2.1**: PEP 561 `py.typed`
- **3.0.0** (2026-04-24): py≥3.10; новый **`url_humanize()`** — обратная
  операция, декодирует punycode/процент-кодирование для показа

```python
url_normalize(url, default_scheme="https", default_domain=None,
              filter_params=False, param_allowlist=None)
```

### Сигнатуры w3lib

```python
canonicalize_url(url, keep_blank_values=True, keep_fragments=False, encoding=None)
url_query_cleaner(url, parameterlist=(), sep='&', kvsep='=', remove=False,
                  unique=True, keep_fragments=False)
```

`url_query_cleaner(url, ['utm_source','gclid'], remove=True)` — режим блоклиста.

## ClearURLs — рекомендуемый путь

**Живой URL:** `https://rules1.clearurls.xyz/data.minify.json`
(зеркало `rules2`). Отдаётся с `ETag` + `Last-Modified` + `Cache-Control: max-age=600`.
Текущий payload: **37 КБ, 206 провайдеров**, `Last-Modified: 2026-03-25`.
Также `raw.githubusercontent.com/ClearURLs/Rules/master/data.min.json`.

### Схема

```
{"providers": {"<name>": {
   "urlPattern": regex,          // обязательно
   "rules": [regex],             // резать query-параметры по имени
   "rawRules": [regex],          // regex-замена по всему URL (Amazon "\/ref=[^/?]*")
   "referralMarketing": [regex], // партнёрские, резать только если opt-in
   "exceptions": [regex],        // пропустить провайдера целиком
   "redirections": [regex],      // группа 1 = настоящий таргет, urldecode + рекурсия
   "completeProvider": bool,     // заблокировать URL (10 таких провайдеров)
   "forceRedirection": bool
}}}
```

### Все 206 провайдеров компилируются в Python `re` без единой ошибки

Прогнан полный sweep. JS-специфичных конструкций нет. **Обёртка не нужна** —
~40 строк Python потребляют ClearURLs напрямую.

Проверенный выход:

```
youtube.com/watch?v=abc&si=XYZ&pp=zz&t=30      -> ...watch?v=abc&t=30
amazon.com/Some-Product/dp/B08N5WRWNW/ref=sr_1_3?keywords=x&qid=17&sr=8-3&th=1
                                               -> amazon.com/Some-Product/dp/B08N5WRWNW
example.com/p?utm_source=a&utm_medium=b&id=5&fbclid=zz&gclid=q -> example.com/p?id=5
x.com/user/status/123?s=20&t=abc               -> x.com/user/status/123
youtube.com/redirect?q=https%3A%2F%2Fexample.org%2Fa%3Futm_source%3Dyt
                                               -> example.org/a
```

⭐ Последний случай: `redirections` **распаковывает обёртки YouTube/Facebook/
Google без сетевого запроса**. Бесплатный резолв для большого класса ссылок.

### Правила реализации

- `rules` матчить **заякорено** (`'^'+r+'$'`) против *имён* параметров
- `rawRules` — `re.sub` по всей строке URL
- после срабатывания `redirections` — рекурсия с `unquote`
- `exceptions` проверять **до** всего остального
- всё case-insensitive

### Обёртки с PyPI — все ловушки

- **`Unalix` 0.9 — мёртв.** Репо `archived: true`, последний push 2022-09-13,
  38★. Правила протухли на 4 года
- **`url-sanitize` 2.0.2** заявляет «ClearURLs-compatible, Python wheels» —
  **не работает standalone**. Wheel это тонкий subprocess-shim, вызов падает:
  `url-sanitize binary not found. Install the Rust CLI with 'cargo install ...'`
- `url-cleaner` 0.1.5 — 2022-11-08, AdGuard-based, протух

**Вердикт: качать `data.minify.json` самому (ETag-кеш, обновление раз в сутки),
применять ~40 строками `re`.** Ноль зависимостей, всегда актуально.

## Site-specific: чего ClearURLs не добьёт

**utm_\* и трекеры** — покрыто `globalRules`: `utm_*`, `mtm_*`, `ga_*`, `yclid`,
`_openstat`, `fbclid`, `fb_action_*`, `gclid`, **`srsltid`** (Google Merchant,
новее, часто пропускают в самописных списках), `dclid`, `mkt_tok`, `_ga`, `_gl`,
`__twitter_impression`, `msclkid`, `igshid`.

**YouTube.** ClearURLs режет `si`, `pp`, `feature`, `gclid`, `kw`. Добавить
самому: `youtu.be/<ID>`, `youtube.com/shorts/<ID>` и `youtube.com/watch?v=<ID>` —
**одно и то же видео**. Канонизировать к `watch?v=<ID>`, `t=`/`list=` из ключа
исключить. Проверено: `youtu.be/dQw4w9WgXcQ` → **303** → `youtube.com/watch?v=...`

**Amazon.** `rawRules: ["\\/ref=[^/?]*"]` + 40 правил параметров закрывают
основное. Добить самому: извлечь ASIN регуляркой
`/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})/?` → переписать в
**`https://www.amazon.<tld>/dp/<ASIN>`**. Это собственная каноническая форма
Amazon, стабильна. **TLD оставить в ключе** — amazon.com ≠ amazon.de (разный
товар и цена). `a.co/d/<code>` — собственный сокращатель Amazon.

**AliExpress.** Канон `https://www.aliexpress.com/item/<itemId>.html`, item ID —
единственная идентичность. Резать `spm`, `algo_pvid`, `algo_exp_id`, `pdp_npi`,
`pdp_ext_f`, `scm*`, `gatewayAdapt`, `sk`, `aff_*`, `curPageLogUid`, `_randl_*`,
`gps-id`, `srcSns`. ⚠️ **ClearURLs оставляет `pdp_npi`** — добавить своё правило.
Локальные хосты (`de.`, `best.`, `.us`) нормализовать к одному.

**Instagram** — `igshid` (в globalRules) + резать `?img_index=`.
**eBay** — `ebay.<tld>/itm/<itemId>`, убрать `hash=`, `var=`, `_trkparms`.
**Etsy** — `/listing/<id>`.

## Резолв коротких ссылок — измерено, не угадано

Живые прогоны HEAD vs GET сегодня:

```
url                                    HEAD          GET
amzn.to/ZZZZZZZ (невалидный)           302 -> http://www.amazon.com/     то же
bit.ly/2FhfxOu (мёртвый)               404                               404
tinyurl.com/2p8dyhwx                   301 -> реальный таргет            то же
a.co/d/0000000 (невалидный)            404                               404
s.click.aliexpress.com/e/_DdJhtaX      302 -> best.aliexpress.com        то же
lnkd.in/abcd                           403  (!)     301 -> реальный таргет
t.me/durov/1                           200 (HTML, без Location)
youtu.be/dQw4w9WgXcQ                   303 -> youtube.com/watch?v=...
```

### Четыре вывода

**1. HEAD не универсален.** LinkedIn отдаёт **403 на HEAD и 301 на GET**.
Схема: HEAD первым (дёшево), при `403/405/501` — retry `GET` со `stream=True` /
`Range: bytes=0-0` и обрывом тела.

**2. ⚠️ Мёртвые короткие ссылки редиректят на главную, а не в 404.**
`amzn.to/<мусор>` → `http://www.amazon.com/`;
`s.click.aliexpress.com/<мусор>` → `https://best.aliexpress.com/`.

Резолвер обязан считать «резолвнулось в голый корень домена / известную
главную» **провалом, а не каноном**. Иначе все дохлые партнёрские ссылки в чате
схлопнутся в одну ложную запись. **Для чата за полтора года это критично.**

**3. t.co отдаёт 200 с meta-refresh** для браузерных UA и флагнутых ссылок,
а не 301. `requests` за meta-refresh не пойдёт. После 3xx: если финальный ответ
`200 text/html` с известного хоста-сокращателя — парсить
`<meta http-equiv="refresh">` и `location.replace(...)` / `window.location`
из тела. JS для этого не нужен, URL лежит в HTML.

**4. Не всё короткое — редирект.** `t.me` отдаёт 200 с контентом. Telegram/
Mastodon-подобные хосты считать терминальными.

### Конфиг клиента

```python
import httpx
client = httpx.AsyncClient(
    follow_redirects=False,          # следовать вручную — нужна цепочка хопов
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
             "Accept-Language": "en-US,en;q=0.9"},
    http2=True,
)
```

- Следовать редиректам вручную, кап 5–8 хопов, хранить всю цепочку
- **Слать реальный браузерный UA** — дефолтный `python-httpx/0.28` ловит 403
- `asyncio.Semaphore(5–8)` глобально + **по хосту 1–2**: чат-ссылки бёрстовые
  и часто с одного хоста
- ≤2 req/s на хост-сокращатель, экспоненциальный backoff на 429/503,
  уважать `Retry-After`
- **Кешировать вечно** — короткие ссылки иммутабельны по дизайну.
  `requests-cache` 1.3.3 для sync; для async — таблица
  `shortlink(src_url PK, final_url, status, chain_json, resolved_at)`
- `httpx` **0.28.1** (2024-12-06 — это текущий релиз, не протухшее зеркало),
  `aiohttp` 3.14.3
- Если хост режет по TLS-фингерпринту — **`curl-cffi` 0.16.0** с
  `impersonate="chrome"`

## Стратегия ключа дедупа

**Три уровня с явной уверенностью**, не один магический ключ.

**Tier 1 — `norm_key`** (всегда, дёшево, без сети). Основной индекс.

```
lowercase scheme+host -> strip "www." -> drop default port -> resolve dot-segments
  -> unwrap ClearURLs redirections (рекурсивно, офлайн)
  -> ClearURLs rules + rawRules + свои канонизаторы (/dp/ASIN, item/<id>.html, watch?v=)
  -> drop fragment (кроме SPA-роутов #!/ и path-подобных)
  -> сортировка параметров по (key, value)
  -> trailing slash долой на неkorневых путях
```

**Tier 2 — `resolved_key`.** Тот же пайплайн к финальному URL после редиректов.
Две ссылки дедупятся, если совпал любой ключ. Это то, что склеивает
`amzn.to/x` с `amazon.com/dp/B0...`.

**Tier 3 — `canonical_key`** из `<link rel="canonical">`. Фетчить только для
переживших tier 1–2. **Доверять условно, никогда слепо:**

- ПРИНЯТЬ, если канон на **том же registrable-домене**
- ОТВЕРГНУТЬ кросс-доменный (синдикация и SEO-спам указывают на первоисточник
  — склейка потеряет ту ссылку, которую человек реально скинул)
- ОТВЕРГНУТЬ, если ведёт на главную или категорию (частый косяк CMS)
- заодно собрать `og:url` и `<link rel="alternate" hreflang>` для локалей

**Контент-хеш — сигнал, не ключ.** Сырой SHA-256 HTML бесполезен (CSRF-токены,
таймстемпы, рекламные слоты, A/B-бакеты меняются каждый фетч). Для
контентного дедупа: `trafilatura` вытаскивает основной текст → **SimHash/MinHash**
по шинглам, расстояние Хэмминга ≤3 = «вероятно та же статья». Ловит
синдицированные перепечатки — но держать как ребро *related*, не merge:
человек скинул конкретный источник.

## Схема БД

```sql
CREATE TABLE link (
  id INTEGER PRIMARY KEY,
  raw_url TEXT NOT NULL,
  norm_key TEXT NOT NULL,
  resolved_url TEXT, resolved_key TEXT,
  canonical_url TEXT, canonical_key TEXT,
  ssurt TEXT,                       -- urlcanon, для префиксных range-скан
  simhash INTEGER,
  redirect_chain TEXT,              -- JSON
  cluster_id INTEGER,               -- union-find по трём ключам
  first_seen_at TEXT, chat_msg_id TEXT
);
CREATE INDEX ix_norm  ON link(norm_key);
CREATE INDEX ix_res   ON link(resolved_key);
CREATE INDEX ix_can   ON link(canonical_key);
CREATE INDEX ix_ssurt ON link(ssurt);
```

⚠️ **`raw_url` хранить вечно.** Нормализация лossy, правила поменяются —
нужна возможность пересчитать ключи через `UPDATE ... SELECT`, когда ClearURLs
выкатит новые правила.
