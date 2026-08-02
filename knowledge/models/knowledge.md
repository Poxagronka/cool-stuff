# Model providers — what was measured

Measured 2026-08-02 against the real vault (374 notes) and the real `links.db`,
with `scripts/bench_llm.py`.

## Search: a question turned into search words

Fourteen questions in Russian, Ukrainian and English; the target note has to
land in the top five. `--pause 13` between requests, so the numbers are the
models and not the rate limits.

| model | found | failed | s/question |
|---|---|---|---|
| anthropic/claude-haiku-4-5 | 13/14 | 0 | 1.53 |
| groq/openai/gpt-oss-120b | 12/14 | 0 | 0.71 |
| groq/llama-3.3-70b-versatile | 12/14 | 0 | 0.30 |
| gemini/gemini-3.6-flash | 5/14 | 9 | 6.40 |

The one question every model misses — «обзор кофемашины» — is a gap in the
index, not in the models: that note has no keywords.

## Sort: a link turned into a note

Eight real links, six checks each (category not `misc`, title ≤ 60 chars,
description ≥ 40 chars, no Cyrillic in the English fields, ≥ 6 keywords,
kebab-case tags).

| model | points | failed | s/link |
|---|---|---|---|
| groq/llama-3.3-70b-versatile | 46/48 | 0 | 0.52 |
| gemini/gemini-3.5-flash-lite | 46/48 | 0 | 0.81 |
| groq/openai/gpt-oss-120b | 45/48 | 0 | 0.92 |
| anthropic/claude-sonnet-5 | 45/48 | 0 | 3.56 |
| anthropic/claude-haiku-4-5 | 45/48 | 0 | 2.40 |
| gemini/gemini-3.6-flash | 40/48 | 1 | 24.10 |

Sonnet first scored 37/48 with zero keywords on seven of eight links. That was
our bug, not the model's — see models R5.

## What each provider actually does

- **Groq** is the one to build on. Free tier, no card, and it returns its own
  limits in the response headers: `llama-3.3-70b-versatile` 1000 req/day and
  12000 tok/min, `openai/gpt-oss-120b` 1000/day and 8000 tok/min,
  `llama-3.1-8b-instant` 14400/day and 6000 tok/min. Fastest of everything
  tested, including the paid models.
- **`llama-3.1-8b-instant` cannot be used despite its 14400/day.** Asked for an
  English query it returns «теплое зимнее». It does not translate.
- **`qwen/qwen3.6-27b` on Groq cannot be used** either: HTTP 400
  `tool_use_failed`, because it emits a `<tool_call>` text block instead of a
  function call.
- **Gemini's free tier is only 3.x now.** On a fresh key `gemini-2.5-flash-lite`
  is 404 "no longer available to new users" and `gemini-2.0-flash-lite` is 429
  with "limit: 0". `gemini-3.5-flash-lite` works and sorts as well as anything.
  `gemini-3.6-flash` 429s after roughly six requests and read-times-out at 24s,
  which rules it out for the search box.
- **Cerebras is not free on this account.** All three models answer HTTP 402
  `payment_required`. Kept in the provider registry, kept out of the chains.

## The chains this produced

- `SEARCH_CHAIN`: groq llama-3.3-70b → groq gpt-oss-120b → anthropic haiku
- `SORT_CHAIN`: groq llama-3.3-70b → gemini 3.5-flash-lite → anthropic sonnet
- `TRIAGE_CHAIN`: groq llama-3.3-70b → gemini 3.5-flash-lite → anthropic haiku

At roughly 400 links and a few hundred questions a month the whole thing runs
inside the free allowances, and Anthropic is only reached on a bad day.
