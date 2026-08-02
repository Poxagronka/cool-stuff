# Vault structure in Obsidian

## Principle: one link = one note

The alternative — a single big table file — is easier to generate, but it kills
everything you take Obsidian for: backlinks, tags, search by fragment, opening a
note in its own pane.

There will be 1000–5000 notes. Obsidian handles that fine; what slows it down is
Graph view and plugins, not the number of files.

## Folder layout

```
LinksVault/
  links/
    2024/
    2025/
    2026/
  bases/
    All Links.base
    Inbox.base
    Clothing.base
  attachments/
  _templates/
```

Split by year, not by category. The category lives in frontmatter and is filtered
in Bases; the folder only exists so that 5000 files don't sit in one directory
(that's already awkward even in a file manager).

File name:

```
2024-11-03 arcteryx — Beta LT Jacket.md
```

Date first, so sorting by name is already chronological. Then the domain, because
that's what people scan for.

## Frontmatter

```yaml
---
url: https://arcteryx.com/eu/en/shop/mens/beta-lt-jacket
canonical_url: https://arcteryx.com/eu/en/shop/mens/beta-lt-jacket
domain: arcteryx.com
title: Arc'teryx Beta LT
category: clothing
tags: [gore-tex, jacket, expensive]
shared_by: Dima
shared_at: 2024-11-03T21:14:00
status: ok
price: "€500"
image: https://images.arcteryx.com/...
tg_link: https://t.me/c/1234567890/45678
---
```

Worth calling out:

- **`tg_link`** — a direct link to the original message. Format for private
  groups: `https://t.me/c/<chat_id without -100>/<message_id>`. It's clickable in
  Obsidian and opens Telegram on that message. The most underrated field: when
  the note doesn't answer the question, the original thread does
- **`status`** — `ok` / `dead` / `inbox`. **Don't delete** dead links: the name
  and the discussion are still useful
- **`shared_by`** — in a chat with several people this is a real search key
  ("Dima posted something about boots")
- **`price`** — in quotes, otherwise Obsidian tries to parse it as a number

Obsidian stores property types in `.obsidian/types.json`. Set them once in the UI
(right-click a property → Property type): `tags` → Tags, `shared_at` →
Date & time, `url` → URL, `category` → Text.

## Note body

```markdown
![](https://images.arcteryx.com/...)

A shell jacket for the shoulder seasons, the lightest in the Beta line.

## From the chat

> **Dima**, 3 Nov 2024, 21:14
> this one's decent for autumn, I've had mine three years
>
> **Sasha**, 21:16
> pricey though
>
> **Dima**, 21:18
> in the end-of-January sale people get it for 350

[Open in Telegram](https://t.me/c/1234567890/45678)
```

**The verbatim chat lines are the most valuable part of the note.** Obsidian
search runs over the file body and finds things by them: you remember "something
about Norway and a membrane", not the model name. og:description will never give
you that.

## Bases instead of Dataview

**Bases is a core plugin** as of Obsidian 1.9 (June 2025), and by 1.13.x it has
grown formulas, pivot tables and built-in views. There's no need to install
Dataview for a new vault anymore: Bases is faster (a native implementation, not
JS recomputed on every render) and won't fall over along with the plugin.

`bases/All Links.base`:

```yaml
filters:
  and:
    - file.hasProperty("url")
views:
  - type: table
    name: All links
    order:
      - file.name
      - category
      - domain
      - shared_by
      - shared_at
    sort:
      - property: shared_at
        direction: DESC
  - type: cards
    name: Showcase
    filters:
      and:
        - category == "clothing"
    image: image
```

`bases/Inbox.base` — the stuff that needs manual triage:

```yaml
filters:
  or:
    - status == "inbox"
    - category == "misc"
```

**In practice:** build the view in the UI, then tidy the YAML by hand. The
`.base` syntax is documented sparsely, and the UI generates a correct file.

A cards view with `image` from frontmatter turns the clothing section into a
proper visual showcase — you recognize an item from the picture instantly, from
the name you don't.

## Three layers of search

1. **Built-in search** — exact strings, `tag:#gore-tex`, `path:2024`,
   `["category":"clothing"]`. Fast, always at hand
2. **Omnisearch** — fuzzy, tolerant of typos, ranked by relevance. Install it
   right away, it's what the built-in one is missing
3. **Smart Connections** — local embeddings, semantic search and "similar notes".
   Install it **a month in**, once data has piled up, not earlier: there's
   nothing to connect in an empty vault, and indexing isn't free

The layers complement each other. Start with 1+2, add the third if you need it.

## Plugins

Minimum:

- **Omnisearch** — fuzzy search
- **Bases** — core, enable it in settings

Optional:

- **Smart Connections** — semantics, later
- **Templater** — if you'll be adding links by hand
- **Local REST API** — if you want an external service to write notes straight
  into the vault (see 09-deployment.md; the alternative is writing `.md` into a
  folder via git/sync, which is simpler)

**Turn off Graph view.** At 5000 notes it eats resources and gives nothing:
there are almost no links between notes, so the graph degenerates into a cloud
of dots.

## Syncing

| Option | Pros | Cons |
|---|---|---|
| **Obsidian Sync** | $4–8/mo, works on mobile with no fuss | paid |
| **git + Obsidian Git** | free, version history | conflicts on mobile, painful on iOS |
| **iCloud / Dropbox** | free, transparent | periodic `.obsidian/` conflicts, lazy file loading on iOS |
| **Syncthing** | free, P2P, fast | no decent iOS client |

If the vault is generated by a script and mobile is read-only, git is enough. If
you plan to edit from your phone, use Obsidian Sync — anything else will annoy
you.

Separately: `.obsidian/` in sync is the source of half the conflicts. Keep
everything in `.gitignore` except `.obsidian/types.json` and the plugin folder
you want to share.
