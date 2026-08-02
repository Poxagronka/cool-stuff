"""Turning what someone typed into terms the index actually holds.

Plain substring matching was the whole of the search, and it is not enough:
"jackets" missed "jacket", "хока" missed "hoka", and a brand in the title
counted for no more than the same word in a passing chat remark. Three things
fix that, none of which need a model or a service:

- every word, in the notes and in the query alike, is folded to latin, so a
  name typed in Cyrillic and the same name written in English meet on one term
- an unknown word is resolved by prefix, then by near-spelling, then by
  substring, each step worth a little less than the one before, so a typo still
  lands and precision still comes first
- rare terms count for more than common ones, so "arcteryx" decides the order
  while "jacket", which half the vault carries, barely moves it
"""

import difflib
import math
import re

WORD = re.compile(r"[^\W_]+", re.U)

# the parts of a url that say nothing about the thing behind it
NOISE = {"http", "https", "www", "com", "org", "net", "html", "php", "index"}

# this is a search box, not an api. nobody types anywhere near this much, and
# the wordiest note in the vault indexes a couple of hundred words, so neither
# a person nor a note ever meets these. they are here so that a pasted wall of
# text cannot turn one request into thousands of walks over the vocabulary.
MAX_TEXT = 8000
MAX_TOKENS = 500

# a resolved word is remembered so the next query asking the same thing is
# free. misses are worth remembering too, and misses are the unlimited kind:
# left alone the cache grows with every new bit of nonsense typed until the
# index reloads. past the limit the oldest entry makes room.
MAX_CACHE = 2048

# ru and uk, folded the way a person would type the name in latin rather than
# the way a standard would: "х" is the h of hoka, not a kh nobody writes
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e",
    "ё": "e", "є": "e", "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}


def latin(word: str) -> str:
    return "".join(TRANSLIT.get(ch, ch) for ch in word)


def tokens(text: str) -> list[str]:
    """The searchable words of a piece of text, folded to latin."""
    out = []
    for raw in WORD.findall((text or "")[:MAX_TEXT].lower()):
        word = latin(raw)
        if word and word not in NOISE:
            out.append(word)
            if len(out) >= MAX_TOKENS:
                break
    return out


class Terms:
    """Which words the vault holds, how rare each one is, and what a typo meant."""

    def __init__(self) -> None:
        self.df: dict[str, int] = {}
        self.total = 0
        self.vocab: list[str] = []
        self.cache: dict[str, list[tuple[str, float]]] = {}

    def add(self, words: set[str]) -> None:
        self.total += 1
        for word in words:
            self.df[word] = self.df.get(word, 0) + 1

    def finish(self) -> None:
        self.vocab = sorted(self.df)
        self.cache = {}

    def idf(self, term: str) -> float:
        """A word in every note tells us nothing; a word in two notes tells us a lot."""
        return math.log(1 + self.total / max(1, self.df.get(term, 1)))

    def expand(self, word: str) -> list[tuple[str, float]]:
        """Terms this word could mean, best first, each with what it is worth.

        Exact is worth all of it. A longer word starting the same way is nearly
        as good ("shoe" wanting "shoes"). Only when neither exists is it worth
        guessing at a misspelling, and only then at a word buried inside another.
        """
        found = self.cache.get(word)
        if found is not None:
            return found
        out: dict[str, float] = {}
        if word in self.df:
            out[word] = 1.0
        for term in self.vocab:
            if len(term) > len(word) and term.startswith(word):
                out.setdefault(term, 0.85)
        if not out:
            for term in difflib.get_close_matches(word, self.vocab, n=6, cutoff=0.8):
                out.setdefault(term, 0.65)
        if not out:
            for term in self.vocab:
                if word in term:
                    out.setdefault(term, 0.5)
        ranked = sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))[:24]
        if len(self.cache) >= MAX_CACHE:
            del self.cache[next(iter(self.cache))]
        self.cache[word] = ranked
        return ranked
