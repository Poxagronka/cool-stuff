# URL canonicalization, redirect resolution, dedup

Checked 2026-08-02; some conclusions come from empirical runs, not from docs.

## Order of operations

```
expand ClearURLs redirections (offline)
  → RFC normalization
  → ClearURLs rules + rawRules
  → own site-specific canonicalizers
  → parameter sorting (LAST step)
```

Sorting goes last because `rawRules` operate on the raw string.

## Libraries: versions as of 2026-08-02

| Package | Version | Date | Role |
|---|---|---|---|
| `url-normalize` | **3.0.0** | 2026-04-25 | RFC 3986 + IDN + CLI |
| `w3lib` | **2.4.1** | 2026-03-20 | `canonicalize_url`, `url_query_cleaner` |
| `courlan` | **1.4.0** | 2026-06-01 | normalization + trackers + `UrlStore` |
| `yarl` | 1.24.5 | 2026-07-20 | immutable URL, the core of aiohttp |
| `furl` | 2.1.4 | 2025-03-09 | mutable, handy for ad-hoc work |
| `urlcanon` | 0.3.1 | **2019-07-02** | old, but unique for SSURT |
| `Unalix` | 0.9 | 2021 | DEAD — **repo archived 2022-09-13** |
| `url-sanitize` | 2.0.2 | 2026-06-11 | DOESN'T WORK — a shim, needs a Rust binary |

```bash
pip install url-normalize w3lib courlan yarl furl urlcanon
```

## Measured behaviour

One input: `HTTPS://WWW.Example.com:443/a/../b/?utm_source=x&b=2&a=1#frag`

```
url_normalize                 -> https://www.example.com/b/?utm_source=x&b=2&a=1#frag
url_normalize(filter_params=True)
                              -> https://www.example.com/b/#frag      <-- killed a=1 and b=2
w3lib.canonicalize_url        -> https://www.example.com:443/a/../b/?a=1&b=2&utm_source=x
urlcanon.whatwg               -> https://www.example.com/b/?utm_source=x&b=2&a=1#frag
urlcanon ssurt                -> com,example,www,//https:/b/?utm_source=x&b=2&a=1#frag
courlan.clean_url             -> https://www.example.com/a/../b/?a=1&b=2#frag
courlan.normalize_url(strict) -> https://www.example.com/a/../b/
```

### Three traps this exposes

**1. `w3lib.canonicalize_url` does NOT drop the default port and does NOT resolve
`..`.** It only sorts parameters, fixes percent-encoding case and strips the
fragment. It's a *sorter*, not an RFC normalizer. Never use it alone as a dedup
key.

**2. `url_normalize(filter_params=True)` has an allowlist of 4 domains.**
Source `url_normalize/param_allowlist.py`, 48 lines:
`{"google.com":["q","ie"], "baidu.com":["wd","ie"], "bing.com":["q"],
"youtube.com":["v","search_query"]}`.

On any other domain it throws away **all** parameters. `?id=9&page=2` collapses
to the same key as `?id=17`. Don't turn it on without an explicit
`param_allowlist`.

**3. `courlan.check_url()` applies spam filters** and can return `None`
(for `example.com`, for instance). On a real URL it works:

```python
check_url("https://www.zalando.de/x.html?utm_medium=cpc&size=42&color=red")
# -> ('https://www.zalando.de/x.html?color=red&size=42', 'zalando.de')
```

**courlan is the best one-liner** for deduping chat links: it strips utm/gclid/
fbclid, sorts, lowercases, returns `(url, domain)`. Downside: it drops fragments
and doesn't resolve `..`.

### `urlcanon` and SSURT

Last release in 2019, but it installs and works on 3.11. Its unique value is
**SSURT** (`com,example,www,//https:/path`): a sortable, prefix-searchable
serialization. If you ever want range queries like "all links from this
domain/subtree" in SQLite, store SSURT as a second indexed column.

### `url-normalize` API changes

- **2.0.0** (2025-03-29): default scheme `http`→**`https`**; IDNA 2008 + UTS46;
  **`sort_query_params` removed** (parameter order is semantically meaningful);
  py2 dropped
- **2.1.0**: CLI. **2.2.0**: `default_domain=`. **2.2.1**: PEP 561 `py.typed`
- **3.0.0** (2026-04-24): py≥3.10; new **`url_humanize()`** — the reverse
  operation, decodes punycode/percent-encoding for display

```python
url_normalize(url, default_scheme="https", default_domain=None,
              filter_params=False, param_allowlist=None)
```

### w3lib signatures

```python
canonicalize_url(url, keep_blank_values=True, keep_fragments=False, encoding=None)
url_query_cleaner(url, parameterlist=(), sep='&', kvsep='=', remove=False,
                  unique=True, keep_fragments=False)
```

`url_query_cleaner(url, ['utm_source','gclid'], remove=True)` — blocklist mode.

## ClearURLs — the recommended path

**Live URL:** `https://rules1.clearurls.xyz/data.minify.json`
(mirror `rules2`). Served with `ETag` + `Last-Modified` + `Cache-Control: max-age=600`.
Current payload: **37 KB, 206 providers**, `Last-Modified: 2026-03-25`.
Also `raw.githubusercontent.com/ClearURLs/Rules/master/data.min.json`.

### Schema

```
{"providers": {"<name>": {
   "urlPattern": regex,          // required
   "rules": [regex],             // strip query params by name
   "rawRules": [regex],          // regex replace over the whole URL (Amazon "\/ref=[^/?]*")
   "referralMarketing": [regex], // affiliate, strip only if opted in
   "exceptions": [regex],        // skip the provider entirely
   "redirections": [regex],      // group 1 = the real target, urldecode + recurse
   "completeProvider": bool,     // block the URL (10 such providers)
   "forceRedirection": bool
}}}
```

### All 206 providers compile in Python `re` without a single error

Ran a full sweep. No JS-specific constructs. **No wrapper needed** — ~40 lines of
Python consume ClearURLs directly.

Verified output:

```
youtube.com/watch?v=abc&si=XYZ&pp=zz&t=30      -> ...watch?v=abc&t=30
amazon.com/Some-Product/dp/B08N5WRWNW/ref=sr_1_3?keywords=x&qid=17&sr=8-3&th=1
                                               -> amazon.com/Some-Product/dp/B08N5WRWNW
example.com/p?utm_source=a&utm_medium=b&id=5&fbclid=zz&gclid=q -> example.com/p?id=5
x.com/user/status/123?s=20&t=abc               -> x.com/user/status/123
youtube.com/redirect?q=https%3A%2F%2Fexample.org%2Fa%3Futm_source%3Dyt
                                               -> example.org/a
```

⭐ That last case: `redirections` **unwraps YouTube/Facebook/Google wrappers with
no network request**. Free resolution for a large class of links.

### Implementation rules

- match `rules` **anchored** (`'^'+r+'$'`) against parameter *names*
- `rawRules` — `re.sub` over the whole URL string
- after `redirections` fires, recurse with `unquote`
- check `exceptions` **before** everything else
- everything case-insensitive

### PyPI wrappers — all the traps

- **`Unalix` 0.9 is dead.** Repo `archived: true`, last push 2022-09-13,
  38★. Rules four years stale
- **`url-sanitize` 2.0.2** claims "ClearURLs-compatible, Python wheels" —
  **doesn't work standalone**. The wheel is a thin subprocess shim, the call
  fails with:
  `url-sanitize binary not found. Install the Rust CLI with 'cargo install ...'`
- `url-cleaner` 0.1.5 — 2022-11-08, AdGuard-based, stale

**Verdict: fetch `data.minify.json` yourself (ETag cache, refresh once a day) and
apply it with ~40 lines of `re`.** Zero dependencies, always current.

## Site-specific: what ClearURLs won't finish off

**utm_\* and trackers** — covered by `globalRules`: `utm_*`, `mtm_*`, `ga_*`,
`yclid`, `_openstat`, `fbclid`, `fb_action_*`, `gclid`, **`srsltid`** (Google
Merchant, newer, often missing from homegrown lists), `dclid`, `mkt_tok`, `_ga`,
`_gl`, `__twitter_impression`, `msclkid`, `igshid`.

**YouTube.** ClearURLs strips `si`, `pp`, `feature`, `gclid`, `kw`. Add yourself:
`youtu.be/<ID>`, `youtube.com/shorts/<ID>` and `youtube.com/watch?v=<ID>` are
**the same video**. Canonicalize to `watch?v=<ID>`, keep `t=`/`list=` out of the
key. Verified: `youtu.be/dQw4w9WgXcQ` → **303** → `youtube.com/watch?v=...`

**Amazon.** `rawRules: ["\\/ref=[^/?]*"]` plus 40 parameter rules cover the
basics. Finish it yourself: pull the ASIN with the regex
`/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})/?` → rewrite to
**`https://www.amazon.<tld>/dp/<ASIN>`**. That's Amazon's own canonical form and
it's stable. **Keep the TLD in the key** — amazon.com ≠ amazon.de (different
product and price). `a.co/d/<code>` is Amazon's own shortener.

**AliExpress.** Canonical form `https://www.aliexpress.com/item/<itemId>.html`,
the item ID is the only identity. Strip `spm`, `algo_pvid`, `algo_exp_id`,
`pdp_npi`, `pdp_ext_f`, `scm*`, `gatewayAdapt`, `sk`, `aff_*`, `curPageLogUid`,
`_randl_*`, `gps-id`, `srcSns`. ⚠️ **ClearURLs leaves `pdp_npi`** — add your own
rule. Normalize the local hosts (`de.`, `best.`, `.us`) down to one.

**Instagram** — `igshid` (in globalRules) plus strip `?img_index=`.
**eBay** — `ebay.<tld>/itm/<itemId>`, drop `hash=`, `var=`, `_trkparms`.
**Etsy** — `/listing/<id>`.

## Resolving short links — measured, not guessed

Live HEAD vs GET runs today:

```
url                                    HEAD          GET
amzn.to/ZZZZZZZ (invalid)              302 -> http://www.amazon.com/     same
bit.ly/2FhfxOu (dead)                  404                               404
tinyurl.com/2p8dyhwx                   301 -> the real target            same
a.co/d/0000000 (invalid)               404                               404
s.click.aliexpress.com/e/_DdJhtaX      302 -> best.aliexpress.com        same
lnkd.in/abcd                           403  (!)     301 -> the real target
t.me/durov/1                           200 (HTML, no Location)
youtu.be/dQw4w9WgXcQ                   303 -> youtube.com/watch?v=...
```

### Four conclusions

**1. HEAD isn't universal.** LinkedIn returns **403 on HEAD and 301 on GET**.
The scheme: HEAD first (cheap), and on `403/405/501` retry with `GET` using
`stream=True` / `Range: bytes=0-0` and cut the body off.

**2. ⚠️ Dead short links redirect to the homepage, not to a 404.**
`amzn.to/<junk>` → `http://www.amazon.com/`;
`s.click.aliexpress.com/<junk>` → `https://best.aliexpress.com/`.

The resolver must treat "resolved to a bare domain root / a known homepage" as
**a failure, not a canonical result**. Otherwise every dead affiliate link in the
chat collapses into one bogus entry. **For a chat spanning a year and a half
that matters.**

**3. t.co returns 200 with a meta-refresh** for browser UAs and flagged links,
not a 301. `requests` won't follow a meta-refresh. After the 3xx: if the final
response is `200 text/html` from a known shortener host, parse
`<meta http-equiv="refresh">` and `location.replace(...)` / `window.location`
from the body. No JS needed, the URL is right there in the HTML.

**4. Not everything short is a redirect.** `t.me` returns 200 with content. Treat
Telegram/Mastodon-like hosts as terminal.

### Client config

```python
import httpx
client = httpx.AsyncClient(
    follow_redirects=False,          # follow manually — we need the hop chain
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
             "Accept-Language": "en-US,en;q=0.9"},
    http2=True,
)
```

- Follow redirects manually, cap at 5–8 hops, keep the whole chain
- **Send a real browser UA** — the default `python-httpx/0.28` gets 403s
- `asyncio.Semaphore(5–8)` globally plus **1–2 per host**: chat links are bursty
  and often from the same host
- ≤2 req/s per shortener host, exponential backoff on 429/503, respect
  `Retry-After`
- **Cache forever** — short links are immutable by design.
  `requests-cache` 1.3.3 for sync; for async, a table
  `shortlink(src_url PK, final_url, status, chain_json, resolved_at)`
- `httpx` **0.28.1** (2024-12-06 — that is the current release, not a stale
  mirror), `aiohttp` 3.14.3
- If a host filters on TLS fingerprint — **`curl-cffi` 0.16.0** with
  `impersonate="chrome"`

## Dedup key strategy

**Three tiers with explicit confidence**, not one magic key.

**Tier 1 — `norm_key`** (always, cheap, no network). The main index.

```
lowercase scheme+host -> strip "www." -> drop default port -> resolve dot-segments
  -> unwrap ClearURLs redirections (recursively, offline)
  -> ClearURLs rules + rawRules + own canonicalizers (/dp/ASIN, item/<id>.html, watch?v=)
  -> drop fragment (except SPA routes #!/ and path-like ones)
  -> sort parameters by (key, value)
  -> drop the trailing slash on non-root paths
```

**Tier 2 — `resolved_key`.** The same pipeline applied to the final URL after
redirects. Two links dedup if either key matches. This is what glues
`amzn.to/x` to `amazon.com/dp/B0...`.

**Tier 3 — `canonical_key`** from `<link rel="canonical">`. Fetch only for the
ones that survived tiers 1–2. **Trust it conditionally, never blindly:**

- ACCEPT if the canonical is on **the same registrable domain**
- REJECT cross-domain ones (syndication and SEO spam point at the original
  source — merging would lose the link the person actually posted)
- REJECT if it points at the homepage or a category (a common CMS screwup)
- while you're there, collect `og:url` and `<link rel="alternate" hreflang>` for
  locales

**A content hash is a signal, not a key.** A raw SHA-256 of the HTML is useless
(CSRF tokens, timestamps, ad slots, A/B buckets change on every fetch). For
content dedup: `trafilatura` pulls the main text → **SimHash/MinHash** over
shingles, Hamming distance ≤3 means "probably the same article". It catches
syndicated reprints — but keep it as a *related* edge, not a merge: the person
posted a specific source.

## DB schema

```sql
CREATE TABLE link (
  id INTEGER PRIMARY KEY,
  raw_url TEXT NOT NULL,
  norm_key TEXT NOT NULL,
  resolved_url TEXT, resolved_key TEXT,
  canonical_url TEXT, canonical_key TEXT,
  ssurt TEXT,                       -- urlcanon, for prefix range scans
  simhash INTEGER,
  redirect_chain TEXT,              -- JSON
  cluster_id INTEGER,               -- union-find over the three keys
  first_seen_at TEXT, chat_msg_id TEXT
);
CREATE INDEX ix_norm  ON link(norm_key);
CREATE INDEX ix_res   ON link(resolved_key);
CREATE INDEX ix_can   ON link(canonical_key);
CREATE INDEX ix_ssurt ON link(ssurt);
```

⚠️ **Keep `raw_url` forever.** Normalization is lossy and the rules will change —
you need to be able to recompute the keys with `UPDATE ... SELECT` when
ClearURLs ships new rules.
