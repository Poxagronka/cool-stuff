# Blocked sites: UA, TLS fingerprint, proxies

Checked 2026-08-02 with live probes from a datacentre IP, some of them from a
Polish residential IP for comparison.

## Live probes (Chrome UA, `curl -L`)

| Site | HTTP | og tags |
|---|---|---|
| youtube.com/watch | 200 | 40 |
| github.com | 200 | 9 |
| nytimes.com | 200 | 5 |
| linkedin.com/company | 200 | 5 |
| **x.com/elonmusk** | 200 | **0** |
| **instagram.com** | 200 | **0** |
| **tiktok.com** | 200 | **0** |
| **reddit.com** | 200 | **0** (8 KB stub) |
| **medium.com** | **403** | 0 |
| **stackoverflow.com** | **403** | 0 |
| **hm.com** | **403** | 0 |
| zara.com | 200 | 0 (JS shell, 2 KB) |
| amazon.com/dp | 404 | 0 |
| **ozon.ru** | **307** | 0 |
| **wildberries.ru** | **498** | 0 |
| **avito.ru** | **429** | 0 |

## Main finding: a social crawler UA opens almost everything

Same `curl`, only the User-Agent changes:

| Site | Chrome UA | `facebookexternalhit` | `Twitterbot` | `TelegramBot` | `WhatsApp/2.23` | Slackbot |
|---|---|---|---|---|---|---|
| x.com | 0 | **404** | **404** | 6 | 6 | 6 |
| instagram.com | 0 | 5 | 5 | 5 | 5 | 5 |
| reddit.com | 0 | 9 | 9 | 9 | 9 | 9 |
| tiktok.com | 0 | 6 | 6 | 6 | 6 | 0 |
| amazon.com/dp | 0 | 8 | 8 | 0 | 0 | 8 |
| **zara.com** | 403 | 403 | 403 | 403 | **5** | 403 |
| avito.ru | 0 | 10 | 10 | 10 | 10 | — |
| ozon.ru (product) | 0 | 307 | 307 | 307 | **6** | — |
| medium.com | 403 | 403 | 403 | 403 | 403 | 403 |
| stackoverflow.com | 403 | 403 | 403 | 403 | 403 | 403 |

**No single UA covers everything — you need a fallback chain.**

`WhatsApp/2.23.20.0` is unexpectedly the most universal: the only one that got
through Zara and Ozon.

Medium and StackOverflow validate the crawler's reverse DNS and hand out 403s to
everyone — those need a real TLS fingerprint.

### IP reputation matters more than it seems

A parallel run from a *residential* Polish IP returned OG tags on
x.com/instagram/facebook even with a bare `python-requests` UA. So the zeros in
the first table are datacentre ASN reputation, not a UA block.

**This is the cheapest lever in the whole scheme.**

## What each site is protected with

From response headers, not from blog posts:

| Site | Protection | Tell |
|---|---|---|
| Amazon, Zara | **Akamai Bot Manager** | `ak_bmsc` cookie |
| Glassdoor, Medium, StackOverflow | **Cloudflare managed challenge** | `cf-mitigated: challenge` |
| G2 | Cloudflare + DataDome stacked | both |
| **Wildberries** | **their own WBaaS**, NOT Qrator | HTTP **498** + `/__wbaas/challenges/antibot/` |
| **Avito** | **Qrator** | literally `server: QRATOR` |
| **Ozon** | their own Antibot Captcha | 307 `?__rr=1` → `__Secure-ETC` cookie |
| Yandex Market | geo | `Доступ ограничен: проблема с IP` |

Correction to the common belief: WB is **not** on Qrator (that's Avito), and
Ozon is **not** on DDoS-Guard. Both run their own stacks.

## RU marketplaces: geo comes first

Avito and Yandex.Market from a Polish residential IP return literally
"Доступ ограничен: проблема с IP". No amount of TLS spoofing fixes that — you
need a Russian exit.

On top of that, since April 2026 the marketplaces have moved from a warning
banner to **functionally blocking VPN traffic**.

None of the four gives OG to an anonymous non-RU bot. For them it's more honest
to give up: geo + a custom challenge + ToS = bad ROI.

## Cloudflare: what changed

- **JA4 has displaced JA3** as the industry standard (Cloudflare, Akamai,
  AWS WAF, VirusTotal). The reason is that TLS extension randomization in Chrome
  (GREASE + shuffling) made raw JA3 hashes unstable; JA4 sorts extensions before
  hashing
- **JA4 Signals** — reputation attached to a fingerprint, not a bare hash. A
  technically correct Chrome JA4 that has been seen doing scraper-like things
  still gets a bad score. That finishes off "just spoof your JA3"
- `cf-mitigated: challenge` is a reliable programmatic tell for a managed
  challenge
- A managed challenge fires by default at bot score **2–29**
- **Signed Agents / Web Bot Auth** — the legitimate route onto the allowlist,
  through a cryptographically signed operator identity. For a permanent preview
  product it turns an adversarial problem into an administrative one
- "Please unblock challenges.cloudflare.com" means your own proxy/DNS is
  blocking the Turnstile widget host. Fix egress, not the challenge

## TLS impersonation

**`curl_cffi` 0.16.0 (released 2026-08-01)** is the unconditional pick. MIT,
6.2k stars, Python >=3.10. The maintainer changed from `yifeikong` to
`lexiforest`. In 0.16.0: curl 8.21 + curl-impersonate 2.0, more HTTP/3 options,
**a new HTTP header order option**.

```bash
pip install curl_cffi
```
```python
from curl_cffi import requests
r = requests.get(url, impersonate="chrome", timeout=25)
# async: from curl_cffi.requests import AsyncSession
```

53 profiles: `chrome99…chrome146`, `chrome99_android`/`chrome131_android`,
`edge99`/`edge101`, `firefox133/135/144/147`, `safari153…safari2601` + iOS,
`tor145`.

**Use the versionless aliases** (`"chrome"`, `"safari"`, `"firefox"`) — they
point at the freshest profile automatically after an upgrade.

| Package | Version | Date | Verdict |
|---|---|---|---|
| **curl_cffi** | **0.16.0** | **2026-08-01** | the default |
| **primp** (Rust) | 1.3.1 | 2026-05-23 | lighter, fewer profiles |
| **wreq** (formerly `rnet`) | 0.12.1 | 2026-07-11 | `rnet` was renamed; `rnet` on PyPI is stale at 2.4.2. Install `wreq` |
| tls-client / python-tls-client | 1.0.1 | **2024-02-02** | abandoned |
| hrequests | 0.9.2 | **2024-12-01** | ~20 months stale |
| curl-impersonate (C, lwthiker) | — | push 2024-07-18 | upstream is asleep, the lexiforest fork lives inside curl_cffi |
| httpx + your own TLS | — | — | dead end: Python's `ssl` can't build a Chrome ClientHello |

### JA3/JA4 alone is not enough in 2026

You need four layers to be coherent at once:

1. A TLS ClientHello with the right GREASE
2. The HTTP/2 fingerprint — SETTINGS/WINDOW_UPDATE/priority tree/pseudo-header
   order
3. HTTP header order and casing (JA4H)
4. Client hints that agree — `sec-ch-ua` has to match the UA and the JA4

A mismatch between layers is a strong signal on its own.

Telling detail: **H&M and ASOS turned out to hinge not on TLS but on header
completeness.** A bare UA got a 403; a full Chrome set (`sec-ch-ua`,
`sec-fetch-*`, `accept-language`, `br`) got 200 + OG.

## Stealth browsers: the one benchmark worth reading

7 tools x 31 Cloudflare targets x 3 runs = 651 verdicts.
[Anti-Detect Browser Benchmark 2026](https://ianlpaterson.com/blog/anti-detect-browser-benchmark-patchright-nodriver-curl-cffi/),
run on 2026-05-13 from a residential IP.

| Tool | OK | Gated | **Blocked** | Engine |
|---|---|---|---|---|
| **nodriver** | 28 | 3 | **0** | Chrome 148 |
| CloakBrowser 0.3.28 | 26 | 3 | 2 | Chromium 145 |
| **curl_cffi 0.15.0** | 26 | 3 | 2 | **no browser** |
| Patchright | 25 | 3 | 3 | Chrome 148 |
| Camoufox | 25 | 3 | 3 | Firefox 135 |
| Vanilla Playwright | 24 | 2 | 5 | Chromium 147 |
| rebrowser-playwright | 24 | 2 | 5 | Chromium 136 |

Two conclusions:

- **curl_cffi (6.4 MB, no browser) tied with CloakBrowser (130 MB of patched
  Chromium)** — 26/31. For pulling OG tags, where you don't need a rendered DOM,
  the HTTP path is far better than its reputation
- What decides it is **automation-protocol fingerprinting** — detecting *how* the
  browser is driven, not how it looks. nodriver wins because it drives Chrome
  over raw WebSocket/CDP with no Playwright in the control plane. The Turnstile
  target blocked everyone except nodriver

### Tool status

| Tool | Version | Date | Status |
|---|---|---|---|
| **nodriver** | 0.50.3 | 2026-05-13 | best result. **AGPL-3.0**, quirky asyncio API |
| **zendriver** | 0.15.5 | 2026-07-15 | nodriver fork under `cdpdriver`, more regular releases. Also **AGPL-3.0** |
| **camoufox** | 0.5.4 | 2026-07-16 | MPL-2.0, 10.7k stars. Patches Firefox at the **C++** level, not JS — there's no shim for a detector to find. Juggler protocol. ~200 MB RAM |
| **patchright** | 1.61.2 | 2026-07-05 | Apache-2.0, monthly releases. Drop-in Playwright. +1 target over vanilla — real, but modest |
| **seleniumbase** | 4.51.8 | 2026-07-26 | **MIT** — the pragmatic pick when AGPL is a blocker. `--uc --cdp` is nodriver's approach under a permissive licence |
| **scrapling** | 0.4.12 | 2026-07-26 | BSD-3, 72k stars. A framework over curl_cffi + Camoufox with adaptive selectors |
| **pydoll-python** | 2.23.1 | 2026-07-16 | CDP-native, no webdriver |
| **botasaurus** | 4.0.97 | 2026-01-06 | slowed down (7 months). Its trick is human-like mouse movement |
| **playwright-stealth** | 2.0.3 | 2026-04-04 | CONCEPTUALLY OBSOLETE: JS injection is exactly what detectors look for |
| **rebrowser-playwright** | 1.52.0 | 2025-05-09 | the benchmark's verdict: "functionally identical to vanilla". Don't use |
| **undetected-chromedriver** | 3.5.5 | **2024-02-17** | DEAD (2.5 years), despite 12.8k stars. Successor is `nodriver` by the same author |

### The licence trap

`nodriver` and `zendriver` are **AGPL-3.0**. Embed one in a service users talk to
over the network and the network clause forces you to open the service's source.
For a commercial product that's usually disqualifying.

**SeleniumBase (MIT) with `--uc --cdp`** gives the same CDP-native approach under
a permissive licence; `patchright` is Apache-2.0.

Check this BEFORE you build a fifth tier around nodriver.

## Proxies: per-GB prices, 2026

| Provider | Entry (~10 GB) | At volume |
|---|---|---|
| **DataImpulse** | **~$1.00/GB** PAYG, traffic doesn't expire | — |
| **Webshare** | below market | **~$1.40/GB** |
| **Decodo** (ex-Smartproxy) | $5.50/GB | **$2.20/GB @ 10 TB** |
| IPRoyal | ~$7/GB | $1.75/GB at volume, doesn't expire |
| Bright Data | $8.40/GB | $3.30/GB @ 10 TB |
| Oxylabs | $8.00/GB (~$4 PAYG) | steep drop from 1 TB |

**Realistic 2026 floor: ~$1.00–1.40/GB** residential. Below $1 usually means
questionable IP sourcing (a compliance risk, not a bargain).

By type: datacentre (from ~$0.50/IP) → ISP/static residential → residential
($1–8/GB) → mobile (2–5x residential; the premium buys CGNAT plausibility, which
is what works against DataDome/Akamai).

## The most underrated optimization: cut off at `</head>`

Measured on 10 real sites: the average full response is **551 KB** → ~1900
fetches per GB. But OG tags live in `<head>`:

| Site | Full | Up to `</head>` |
|---|---|---|
| nytimes.com | 1188 KB | 200 KB |
| hm.com | 2116 KB | **22 KB** |
| x.com | 288 KB | **15 KB** |
| linkedin.com | 341 KB | **17 KB** |
| github.com | 387 KB | 31 KB |

The average head is **~47 KB, 12x smaller**. Stream the response and drop the
connection at `</head>` → **20000+ OG fetches per GB** instead of 1900. On top of
that gzip/br cuts another 3–4x, and proxies bill compressed bytes.

**In money: an OG fetch through a $2/GB residential proxy costs ~$0.0001 when you
cut at `</head>` versus ~$0.001 for a full download.** That single optimization
beats any negotiation with a provider.

A headless browser does the opposite — it pulls JS/CSS/images, 2–10 MB per page,
**100–500x more expensive in traffic**. If a browser is unavoidable, block
everything except the document.

## Scraping APIs for the 2-5% that hold out

| Service | Free | Entry | **$/1k JS + anti-bot** | Stealth multiplier |
|---|---|---|---|---|
| **Bright Data Web Unlocker** | **5000 req/mo** | PAYG | **$1.50** (→$1.30 on Scale $499) | **x1 — no multipliers** |
| **Oxylabs Web Scraper** | 2000 results | $49/mo | **$0.40–1.35** | x1, headless included |
| **Zyte API** | trial | pure PAYG | HTTP T1 $0.13 → browser T3 **$1.92** | Zyte picks the tier, not you |
| **ZenRows** | trial | $69/mo | $2.08–7.00 | x25 |
| **Scrapfly** | 1000 credits | $30/mo | $2.73–4.50 | x30 (res 25 + JS 5) |
| **Firecrawl** | 1000 credits/mo | $16/mo (annual) | $3.33–4.95 | **x5** — the fairest; `proxy: auto` charges 1 credit if the cheap path was enough |
| **ScrapingBee** | 1000 credits | $49/mo | **$5.63–14.70** | **x75** (stealth_proxy) |
| **ScraperAPI** | 1000/mo | $49/mo | **$7.48–36.75** | **x75**; Amazon x5, Google x25, LinkedIn x30. **No PAYG below $475** |

**The key pricing takeaway:** the cheap $30–49 plans at ScrapingBee/ScraperAPI/
ZenRows/Scrapfly are priced for *ordinary* requests. On a protected target you
pay 25–75x the credits. Bright Data and Oxylabs quote one flat number — in
practice they are cheaper than they look on the storefront.

**2025–2026 shifts:** Bright Data introduced a free 5k req/mo tier and PAYG at
$1.50/1k with no multipliers — that reset the market floor. Zyte moved to 5 tiers
per 1000 *successful* responses (failures are free) with 25–52% commit discounts.
ScraperAPI killed PAYG on the lower plans.

## Decision tree

```
URL from the chat
 |
 +-0. Cache + normalization (courlan). Dedup by canonical, TTL >=24h.
 |    Cache NEGATIVE results too (shorter TTL), otherwise
 |    a WB link runs the whole ladder on every paste.
 |
 +-1. oEmbed / native API           ~$0, ~100% where it exists
 |    YouTube, Vimeo, X, TikTok, Instagram, Spotify, Reddit,
 |    Bluesky, SoundCloud, Flickr, Giphy, Mastodon.
 |    NEVER scrape these sites.
 |
 +-2. httpx, FULL set of Chrome headers,
 |    stream + abort at </head>     ~$0, ~50-60%
 |    Header completeness matters as much as the UA (it fixed H&M and ASOS).
 |
 +-2b. Rotate social-crawler UAs    ~$0, +a significant chunk
 |    Chain: WhatsApp -> facebookexternalhit -> Twitterbot
 |           -> TelegramBot -> Slackbot
 |    Opens x.com, instagram, reddit, tiktok, amazon,
 |    zara, avito, ozon. No single UA covers everything.
 |
 +-3. curl_cffi impersonate="chrome"  ~$0 + proxy, ~75-85%
 |    Flipped 6 of 20 targets: LinkedIn 999->200,
 |    Zillow/Indeed/H&M/ASOS 403->200.
 |    ~$0.0001/fetch on a $2/GB residential proxy.
 |    STOP HERE for the vast majority of links.
 |
 +-4. Rotating residential proxies   +$0.0001-0.001, ~85%
 |    Fixes IP-reputation blocks. For .ru a Russian exit is
 |    MANDATORY, otherwise it's pointless.
 |
 +-5. Stealth browser                ~$0.001-0.01, ~90-95%
 |    SeleniumBase --uc --cdp (MIT)  <- default
 |    nodriver (best measurement, but AGPL-3.0)
 |    Block images/media/fonts, otherwise traffic goes up x100.
 |    Needed for: Zara (JS shell), CF managed challenge, Turnstile.
 |
 +-6. Paid scraping API              $0.0001-0.01/req, ~95-99%
      Bright Data Web Unlocker ~$1.50/1k — the hard targets
      Justified for: Akamai (Amazon, Zara), DataDome, Kasada, HUMAN.
      For .ru marketplaces it's more honest to give up.
```

**Engineering notes.** Run tiers 2–3 in parallel, not in sequence — tier 3 costs
almost nothing on top. Hard budget and time cap per URL: a preview after
20 seconds is a failed preview, even if it eventually arrived. Record which tier
worked for a domain and start there next time.

## Legal caveats

Not legal advice. Fetching public OG tags for a preview is the most defensible
scraping case there is: it's the protocol's stated purpose, the data is published
specifically for third-party consumers, and the volume is low. A fundamentally
different position from bulk data extraction.

`robots.txt` isn't law, but ignoring it is evidence of intent in a dispute.

The risk concentrates on **circumventing a technical access-control measure**
(CFAA in the US; in Russia parsing is legal, but "programs that circumvent
anti-parsing protection" are called out separately) — solving a captcha
programmatically is qualitatively different from swapping a User-Agent.

Personal data (LinkedIn profiles, Avito sellers) pulls in GDPR/152-FZ regardless
of how public it is.

**Cloudflare Signed Agents / Web Bot Auth is the sanctioned route** for a
permanent, identifiable preview service.
