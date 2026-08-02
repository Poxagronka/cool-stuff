# Public portal — rules

**R1.** The model behind the search box does not write the answer. Its only
output is a call to the `search` tool with query/category/tag/reply fields,
forced through `tool_choice`. The user never sees free text from the model, so at
worst an injection in the question spoils the search query instead of replacing
the answer.

**R2.** Note contents never reach the model. It sees only the question, the list
of categories and the top tags. As long as that holds, an injection from a page
that made it into the database cannot reach the chat line.

**R3.** Whatever the model returns is still filtered on the server: category and
tag must come from the known lists, query and reply go through a character
allowlist and a length cap. The model is not a trusted source, not even our own.

**R4.** The limit is 10 questions per minute per address, a question is at most
200 characters, and identical questions are served from cache. The portal is
public and the owner pays for the tokens.

**R5.** Search is tokenised, not substring. Both the notes and the question are
cut into words, folded to latin (so «найк» and "nike" are the same token) and
matched term by term: exact, then prefix, then a difflib near-match for typos,
then substring, each worth less than the one before. A word's contribution is
its IDF, so a rare brand name outweighs "app" appearing in half the vault, and a
hit in the title or keywords counts triple a hit in the body. See
`src/tglinks/textsearch.py`.

**R5.2.** The model's `category`/`tag` guess is a hint, not a filter. When the
plan returns no hits, the server drops the category and tag and searches again
on the words alone. Without that, one wrong guess ("потолочные вентиляторы" →
`tech`) turns a perfectly good query into an empty page.

**R5.1.** Search has two modes. The search box is strict mode: every word must
match, since a person knows what they are typing. A question through the model is
`any` mode: the model's words are a guess at synonyms, and requiring all of them
means finding nothing. There one match is enough, and ranking by the number of
matched words puts the best result on top.

**R6.** Page text that goes into the classifier prompt is wrapped in a marker
saying it is data, not instructions. A page from the internet is untrusted input,
and the only thing protecting the note description is structured output through
forced tool use.

**R7.** The tags are a web, not a cloud: a force-directed graph of bubbles on
threads that floats on its own and doubles as the filter. `GET /api/graph`
answers `{nodes, edges, picked}` for whatever the current results are — nodes
are the top 60 tags with their counts plus any tag already picked, edges are
the pairs that appear on the same note. A picked tag is kept even when the
narrowed results push it out of the top slice: a web missing the node you are
standing on reads as a bug.

**R8.** The web is drawn on a canvas, and that is a security decision as much
as a performance one. Tag strings are written by a model reading arbitrary web
pages, so they are hostile text: labels go through `fillText` and the
screen-reader fallback list through `textContent`, and nothing off the network
is ever parsed as markup. Forty-odd nodes redrawn every frame cost nothing.
The css and js live in `src/tglinks/graph.py`; `web.py` interpolates them.

**R9.** Every input to the search has a ceiling, because the expensive part is
not the match but the vocabulary walk behind each word. A question is 200
characters, the tokeniser reads 8000 characters and stops at 500 words, at most
8 tags are honoured, a page is at most 120 items, and the word-expansion cache
holds 2048 entries with the oldest evicted. Misses are the dangerous half of
that cache: cached, they grow with every new bit of nonsense typed until the
index reloads; uncached, a pasted wall of text turns one request into thousands
of walks. Neither a person nor a note comes anywhere near these numbers.
