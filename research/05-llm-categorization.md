# Categorizing links with an LLM

## Why an LLM and not rules

Domain rules work right up until the chat gets a link to a Reddit thread about a
jacket, a Substack article about a coffee machine, and a product on a shop
nobody has heard of. The domain says nothing. The context does: the page title,
og:description and, most of all, what people wrote around the link in the chat.

## A closed list of categories

Free-form categorization produces a dump of 400 unique values. You need a
**closed list** the model has to obey (an enum in the schema):

| Category | What goes in |
|---|---|
| `clothing` | clothes, shoes, accessories, brands, gear drops |
| `tech` | hardware, gadgets, devices, audio, photo |
| `software` | apps, services, libraries, repos |
| `site` | a useful site/tool/resource in its own right |
| `article` | article, longread, video, podcast — something to read |
| `food` | food, drinks, coffee, recipes, delivery |
| `place` | venues, cities, hotels, routes |
| `misc` | didn't fit anywhere |

Eight, because the whole list has to fit in your head while you're filtering.
More than twelve doesn't work.

**Free-form tags stay separate from the category.** One category, as many tags as
you like: `arcteryx`, `gore-tex`, `для-похода`, `дорого`. The category is for
filtering, the tags are for "what else was there about membranes".

Quality check on the list: if more than 10% of links land in `misc`, a category
is missing. Look at what piled up there and add one.

## What to feed the model

The main mistake is to hand over only the URL and og:description. Half the links
in the chat look like "here" plus a link. The meaning lives in the neighbouring
messages.

Context per link:

```
1. URL (canonical) + domain
2. Page title, og:description, og:site_name, og:type
3. The text of the message with the link
4. The whole reply chain if the message is part of a thread
5. Messages within ±5 minutes from the same author and nearby authors
6. Author and date
```

Item 5 is the one people usually forget, and it's exactly what surfaces "this is
for autumn, not winter" and "they don't sell it here in Poland".

## Response schema

Structured output through tool use — the model has to return a valid object, no
text parsing needed.

```json
{
  "name": "input_schema",
  "input_schema": {
    "type": "object",
    "properties": {
      "category": {
        "type": "string",
        "enum": ["clothing","tech","software","site","article","food","place","misc"]
      },
      "tags":        {"type": "array", "items": {"type": "string"}, "maxItems": 6},
      "title":       {"type": "string"},
      "description": {"type": "string"},
      "confidence":  {"type": "string", "enum": ["high","medium","low"]}
    },
    "required": ["category","tags","title","description","confidence"]
  }
}
```

On the fields:

- `title` — a human name, not the page's `<title>`. `Arc'teryx Beta LT` instead
  of `Beta LT Jacket Men's | Arc'teryx | Official Online Store EU`
- `description` — **one sentence in its own words**, including what was said in
  the chat. A copy of og:description is useless: it's already in the metadata and
  nobody searches by it
- `confidence: low` → goes into an inbox for manual triage, not into the common
  pile

## The prompt: what actually matters

- **Put the category list with examples in the prompt itself**, not only in the
  enum. The enum gives validity, the examples give sense
- **Explicitly allow `misc`.** Without it the model bends over backwards and
  sorts everything into categories with a confident face
- **Say explicitly: the description in Russian, the tags in Latin kebab-case.**
  Otherwise you get half the tags in Cyrillic and half not, and they won't
  collapse together
- **One call = one link.** Batch classification of 20 at a time in one prompt
  saves tokens, but the model starts fitting answers to their neighbours and
  loses links from the middle of the list
- Batch through the Batch API, not by stuffing things into one prompt

## Cost

Current prices (checked at `platform.claude.com/docs/en/about-claude/pricing`):

| Model | Input $/MTok | Output $/MTok | Batch input | Batch output |
|---|---|---|---|---|
| **Sonnet 5** (intro pricing until 2026-08-31) | $2 | $10 | **$1** | **$5** |
| Haiku 4.5 | $1 | $5 | $0.50 | $2.50 |
| Opus 5 | $15 | $75 | $7.50 | $37.50 |

The Batch API gives **-50%**, with a processing window of up to 24 hours. For a
one-off pass over the chat history that's exactly the case it exists for.

Estimate for 2000 links at ~1200 input / ~150 output tokens per link:

```
input:  2000 x 1200 = 2.4 MTok x $1 = $2.40
output: 2000 x  150 = 0.3 MTok x $5 = $1.50
                                     ------
                                      ~$3.90
```

**Under four dollars to process a year and a half of chat.** There's nothing to
save on here — dropping to Haiku for a $2 difference makes no sense, the quality
of the descriptions matters more.

For continuous collection (one link at a time) you don't need Batch — a plain
synchronous call, ~$0.002 per link.

## Prompt caching

The system prompt with the category list and examples is 500–1500 tokens and is
the same for every call. With `cache_control` it's read at 10% of the price.

On the Batch API the cache and the discount stack. The saving is small in
absolute terms (a dollar), but it's one line of config.

## A two-pass variant if the quality disappoints

1. First pass — all links as they are
2. Collect the tags that actually came up, sort by frequency, take the top 50
3. Second pass — the same links, but with the list of existing tags in the prompt
   and an instruction: "reuse one if it fits; only create a new one if nothing
   really fits"

This cures the main disease of free-form tags: `гортекс` / `gore-tex` /
`goretex` / `мембрана` as four different tags.

The second pass costs the same as the first. Do it only if the first pass shows
the tags have sprawled.

## What NOT to give the model

- **Dedup.** That's a deterministic task (see 02-url-canonicalization.md). An LLM
  will get it wrong in both directions
- **Detecting dead links.** That's an HTTP status
- **The date.** It's in the message metadata
