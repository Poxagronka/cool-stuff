# Model providers — rules

**R1.** Every model call in this project is one forced tool call with a schema
and nothing else. `llm.call` is the only entry point; it speaks two dialects
(OpenAI `/chat/completions` for Groq, Cerebras and Gemini, Anthropic
`/v1/messages`) and returns the tool input as a dict. No provider ever writes
prose that reaches a user or a note.

**R2.** A provider that answers with anything other than a well-formed call to
the one tool it was given counts as unavailable, and the chain moves on. Quota
errors, timeouts, malformed JSON and "here is my answer in a `<tool_call>`
block" are all the same failure. Better to pay Anthropic for one request than to
put a bad note in the vault.

**R3.** Chains are configured as strings — `SEARCH_CHAIN`, `SORT_CHAIN`,
`TRIAGE_CHAIN` — in the form `provider/model,provider/model`. Free providers
first, Anthropic last. An unknown provider in a chain is logged and skipped, so
a typo degrades instead of crashing.

**R4.** Retries are per provider and only for work nobody is waiting on.
Sorting a link retries twice; the search box does not retry at all, it moves to
the next provider — a person watching a spinner would rather have a slightly
worse answer now than a better one after a backoff.

**R5.** A model asked for an array will sometimes send `"a, b, c"`. Coerce, do
not discard: `categorize.listed()` accepts both. Throwing the string away once
cost 316 of 374 notes their keywords, and nothing in the pipeline noticed
because the field was merely empty, not wrong.

**R6.** No verdict from the triage gate means the link is dropped. What the
gate lets through is published with the chat lines that came with it, marked
`source: saved` — so an unreachable provider must not turn into an implicit
yes. Hosts that are private or adult by construction never reach a model at
all: a model that has to be asked "is this porn" will occasionally say no.
Which lines count as "came with it" is telegram R10, not this rule.

**R7.** A tool payload is checked against the schema the tool declared before
anyone reads it: every required key present, and every property that is there
of the declared type. A provider answering `{"keep": "false"}` is not
disagreeing with the triage gate, it is failing to call the tool — `bool()` of
that string is True and the private link gets published. An empty object is the
same failure wearing a note's clothes. The check is deliberately shallow, and
`array` still takes a string because of R5. Anything malformed anywhere in the
envelope — not an object, no message, no tool call, arguments that are not
json — becomes `Unavailable`, so R2 applies and the chain moves on.

**R8.** Anything built out of the vault travels in the user turn, fenced as
data, never in the system message. The tag hints the search box gets are made
from tags a model wrote while reading arbitrary web pages, and untrusted text
in a system block is the model being told to obey it. On Anthropic the hint and
the question share one user turn, because that api wants the roles to
alternate. Same reasoning as portal R6, one layer down.

**R9.** A model asked for tags writes descriptions of the one link in front of
it, not shelves the collection can stand on, and every failure of that is a tag
holding a single note for ever:

- A place or a brand glued to the kind. `athens-radio` gathers nothing;
  `radio` plus `athens` are two shelves that do.
- The same thing said twice. `radio` and `online-radio` on one note.
- Plural against singular. `piano-tutorial` and `piano-tutorials` are two
  shelves holding the same thing, so the trailing `s` is folded in code — only
  where a word is left, or `css` and `bass` become plurals of nothing.
- No broad word at all. Asking for "up to 6 tags" got a radio station
  `athens-radio`, `online-radio`, `experimental-music` — three tags, no
  `music`, filed under nothing. The broad word is asked for by position: the
  first tag is the plain one.

And tagging note by note is what makes them: three neighbouring links came back
`web-app`, `browser-based` and `online-software`. The tags the collection
already uses go in the same turn as the note, most-used first, with the
instruction that any of them which fits belongs in the answer. That is the
whole difference between ten tags and ten shelves.
