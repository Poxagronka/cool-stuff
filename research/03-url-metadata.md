# Metadata from a URL: oEmbed, parsing, hosted services

Checked 2026-08-02 with live probes and the PyPI JSON API.

## Main conclusion: oEmbed first, scraping second

The common mistake is to go straight to parsing meta tags. The big social sites
have oEmbed: free, official, dead reliable.

## oEmbed is alive, and in better shape than in 2023

All results are live probes, no tokens and no cookies.

| Provider | Endpoint | Auth | Anonymous |
|---|---|---|---|
| **YouTube** | `youtube.com/oembed?url=...&format=json` | no | yes |
| **Vimeo** | `vimeo.com/api/oembed.json?url=...` | no | yes |
| **Twitter/X** | `publish.twitter.com/oembed` → 301 → `publish.x.com/oembed` | **no** | yes, **NOT dead** |
| **TikTok** | `www.tiktok.com/oembed?url=...` | no | yes |
| **Instagram** | `graph.facebook.com/v25.0/instagram_oembed?url=...` | **none since 2026-06-15** | yes, 1000 req/hour |
| **Facebook** | `graph.facebook.com/v25.0/oembed_page` / `oembed_video` | no | yes (`oembed_post` is finicky) |
| **Reddit** | `www.reddit.com/oembed?url=...` | no | yes (broken URL → **403 HTML**) |
| **SoundCloud** | `soundcloud.com/oembed?format=json&url=...` | no | yes |
| **Spotify** | `open.spotify.com/oembed?url=...` | no | yes |
| **Flickr** | `flickr.com/services/oembed?format=json&url=...` | no | yes |
| **Giphy** | `giphy.com/services/oembed?url=...` | no | yes |
| **Bluesky** | `embed.bsky.app/oembed?url=...` | no | yes |
| **Mastodon** | `{instance}/api/oembed?url=...` | no | yes (in core, but NOT in providers.json) |
| **Figma** | `www.figma.com/api/oembed?url=...` (not `api.figma.com`!) | no | yes |
| **Loom** | `www.loom.com/v1/oembed?url=...` | no | yes |
| Twitch | ~~`api.twitch.tv/v5/oembed`~~ | — | DEAD since v5 (2022) |
| Threads | — | — | token-gated / none |
| Substack / Notion / GitHub gists | — | — | never had it |
| Medium | `medium.com/services/oembed?url=...` | no | Cloudflare 403 from a server |

### Two things that break the common wisdom

**1. X/Twitter oEmbed works anonymously.** Checked on `x.com/jack/status/20` — it
returns the tweet text, the author and a ready blockquote. The "it's dead" myth
comes from `publish.twitter.com` returning **a 301 with an empty body**; without
`follow_redirects` that looks like a breakage. The real host is now
`publish.x.com/oembed`.

**2. Meta dropped the token gate on 2026-06-15.** For six years
`instagram_oembed` required `oembed_read` + App Review. Now it works without an
`access_token`. Verified: without a token you get either the embed HTML or an
honest `code: 24 / Media Not Found` — not an auth error.

### providers.json

`oembed.com/providers.json`, `last-modified: 2026-08-02`, **366 providers /
372 endpoints**, the `iamcal/oembed` repo is active (PRs #929–932 in late July).

But the list is **accretive** — nobody cleans out dead endpoints, and Meta is
still pinned there at `v16.0` (long past Meta's two-year deprecation window).
Rewrite it to `v25.0`+ by hand.

### Libraries — one alive

```bash
pip install micawber   # 0.7.0, 2026-07-05, 680 stars, 0 open issues
```

```python
from micawber import Cache, bootstrap_oembed
registry = bootstrap_oembed(cache=Cache())      # downloads 162 KB of providers.json
meta = registry.request('https://youtu.be/dQw4w9WgXcQ')
html = registry.parse_text('look at https://youtu.be/dQw4w9WgXcQ')
```

Always wire up `Cache` — otherwise it's 162 KB on every cold start. There's also
`bootstrap_basic()`, `bootstrap_noembed()`, `bootstrap_iframely()`, plus Django
and Flask integrations.

The alternative is `oembedpy` 0.9.0 (2025-12-27), but it has 8 stars. Everything
else (`pyembed`, `python-oembed`, `pyoembed`, `django-oembed`) has been dead
since 2014–2017.

**Honestly: for the 15 sites that actually matter, a dict of 15 templates plus
`httpx` beats any library.** The registry is stale exactly where it hurts most —
Meta versions, the Twitter/X duplicate, no Mastodon.

### Three different shapes of "not found"

YouTube 404 plaintext, X 404 HTML, Bluesky 404 plaintext, Reddit **403 HTML**,
Meta 400 JSON. **Never parse the body as JSON on a non-200.**

### Aggregators

- **noembed.com** — answers 200 without a key, but the code has been frozen
  since January 2021, 55 open issues, **42 providers** vintage 2016: no TikTok,
  Bluesky, Instagram, Reddit, Spotify. `x.com/...` → `no matching providers
  found`. A fallback, not a foundation
- **Iframely** — `iframe.ly/api/oembed?url=...&api_key=...`, 403 without a key.
  A serious commercial option, has a self-hosted core
- **Embedly** — alive, `api.embed.ly/1/oembed`, ~$119/mo for 10k Embed + 10k
  Extract. The `embedly` Python client is 0.5.0 from 2013 — call the REST API
  directly

## Python parsing libraries: who is alive

| Package | Version | Last release | Status |
|---|---|---|---|
| **trafilatura** | **2.2.0** | **2026-07-31** | The reference. 6.4k stars |
| **htmldate** | 1.10.0 | 2026-06-01 | alive, same author (adbar) |
| **courlan** | 1.4.0 | 2026-06-01 | alive, same author |
| **newspaper4k** | 0.9.6 | 2026-07-19 | live fork of newspaper3k, 1.1k stars |
| **goose3** | 3.1.22 | 2026-07-23 | alive but narrow (high precision, low recall) |
| **metadata-parser** | 1.0.0 | 2025-08-30 | alive, 1.0 is a breaking release |
| **readability-lxml** | 0.8.4.1 | 2025-05-03 | sluggish, but works |
| **linkpreview** | 0.12.1 | 2025-08-15 | small (54 stars), current |
| **extruct** | 0.18.0 | 2024-11-08 | HALF-DEAD: commit 2025-03-24, no release in 21 months |
| **newspaper3k** | 0.2.8 | **2018-09-28** | DEAD |
| **opengraph-py3** | 0.71 | **2018-02-27** | DEAD |
| python-oembed / pyembed / webpreview / lassie / dragnet | — | 2016–2022 | DEAD |

On newspaper3k: the repo does have commits (`add swiftproxy`, `remove webshare`)
— those are spam README edits linking proxy sponsors, the code hasn't been
touched in 8 years.

### trafilatura covers almost everything in one go

Checked against the sources: `trafilatura/metadata.py` reads `og:*`, `twitter:*`
**and** `<script type="application/ld+json">` (JSON-LD overrides the rest).

`Document` fields (`settings.py:229`):

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

### When you need extruct

Only for **microdata, RDFa, microformats, Dublin Core** — for example product
`schema.org/Product` with a price when it isn't in JSON-LD. Nothing else is at
extruct's level.

```python
import extruct
data = extruct.extract(html, base_url=url,
                       syntaxes=["json-ld","microdata","opengraph","rdfa","dublincore"])
```

`turbohtml` 1.5.1 (2026-07-27) advertises `structured_data()` on a C core, but
the repo is 2 months old with 19 stars — watch it, don't put it in prod.

### Recommended stack

```bash
pip install "trafilatura[all]" extruct micawber curl_cffi selectolax
```

- `micawber` — oEmbed, the first tier
- `trafilatura` — metadata plus article text in one pass
- `extruct` — finish off structured data where you need product/recipe/event
- `curl_cffi` — the transport (see 04-anti-bot.md)
- `selectolax` 0.4.11 (2026-07-15) — fast head parsing by hand

## Extractor benchmarks

The official trafilatura benchmark (750 documents, 2236 text / 2250 boilerplate),
F1:

| Package | Precision | Recall | F1 | Slowdown |
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

The table is dated 2022-05-18 and compares trafilatura 1.2.2 — there are no
fresher official numbers.

**An independent paper, February 2026** — "Beyond a Single Extractor"
([arxiv 2602.19548](https://arxiv.org/html/2602.19548v1)), Common Crawl: there is
no single winner on the general web, but the spread across page types is huge.
Tables: resiliparse **11.9** vs trafilatura **3.7** vs jusText **1.6**
(jusText just throws tables away). Extractors capture **different subsets of
pages** — after filtering the overlap is only 39%.

In practice: for "a link preview in a chat" the difference between trafilatura
and resiliparse doesn't matter. If you keep the article text for search, run
`resiliparse` 1.0.9 (2026-07-20) as a second pass on table-heavy pages.

## Hosted services: prices as of August 2026

### Link-preview specialists

| Service | Free | Cheap paid tier | $/1k | JS/anti-bot |
|---|---|---|---|---|
| **LinkPreview.net** | 60 req/hour (~43k/mo), personal only | **$8/mo** = 200 req/hr (~144k) | **$0.06** | no |
| **urlmeta** | 500 req/mo | $9/mo = 25k | $0.36 | no; site copyright says 2024 — risky |
| **jsonlink.io** | 100 credits | $15/mo = 50k | $0.30 | markdown/screenshot = 2 credits |
| **Peekalink** | 50 req/hour | $42/mo (annual) = 500 req/hr | $0.12–0.30 | hourly limit, bursts suffer |
| **Microlink** | 25 req/day; anonymous ~25 req/min | Pro $49/mo = 46k–420k | $0.12–1.07 | yes, real browser + screenshots/PDF |
| **Iframely** | 2k hits/mo, 1 domain | $49/mo = 25k hits | $1.96 | a "hit" = an hour of URL activity |
| **OpenGraph.io** | 100 requests | $25 one-off = 50k credits | **$8.40–16.40** with JS+proxy | multipliers: render +10, proxy +10…+30 |
| **Diffbot** | **10k credits/mo** (best free tier) | $299/mo = 250k | $2.39 | 5 req/**min** on free |
| **Jina Reader** (r.jina.ai) | **20 RPM keyless, forever**; 500 RPM with a key | PAYG | **~$0.10/1k pages** | weak against anti-bot |

Two sources disagreed on Iframely (free 1k vs 2k hits; $49 = 10k vs 25k) — check
the pricing yourself before buying.

### Recommendations by volume

- **~10k/mo of plain OG:** Diffbot Free ($0) if you can live with 5 req/min.
  Otherwise **LinkPreview Basic $8/mo**. Or **keyless Jina Reader — $0 forever**
  at 20 RPM (~864k/mo), if markdown and no SLA are fine
- **~100k/mo:** LinkPreview Pro $25/mo ($0.035/1k). With rendering — Scrapfly
  Discovery $30 or Microlink Pro $49
- **Hard anti-bot:** see 04-anti-bot.md

## Bottom line

1. **oEmbed first** (micawber 0.7.0) — free, exact, covers the top social sites.
   X and Instagram are open anonymously again
2. **trafilatura 2.2.0** parses OG + Twitter cards + JSON-LD + article text in
   one call. `extruct` to finish off microdata/RDFa
3. **newspaper3k is dead** (2018), `opengraph-py3` is dead (2018). If you see
   them in a tutorial, the tutorial is out of date
