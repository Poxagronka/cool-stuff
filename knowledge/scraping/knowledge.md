# Metadata enrichment — facts

Verified 2026-08-02 on 388 real links from the chat.

## Which tier covered what

Over the run, most of the links were pulled by `curl_cffi` with TLS
impersonation — noticeably more often than the research stage assumed. A plain
request with a full set of Chrome headers works on the calm sites (notion,
apple), oEmbed works on youtube, flickr and the other providers on the list.

Takeaway for future edits: tier 4 is not a fallback for rare cases, it is the
workhorse. It must not be removed, and `curl_cffi` belongs in the main
dependencies, not the optional ones.

## Tier race

Tiers 2 and 3 run in parallel, not in sequence. Before the challenge-page check
existed, chrome consistently won the race against the crawler UA and brought back
a Cloudflare stub with status 200 — Reddit got saved with the title "Please wait
for verification". With the check in place, that same Reddit resolves fine
through `crawler:WhatsApp`.

## Speed

A sequential pass over 388 links took about an hour, almost all of it waiting on
the network. A semaphore of 4 concurrent jobs cut the run to a few minutes.
SQLite is safe here: asyncio is single-threaded and each write commits one after
another.

## Cost

388 links on Sonnet 5 without the Batch API — under a dollar. The $0.002 per link
estimate held up.
