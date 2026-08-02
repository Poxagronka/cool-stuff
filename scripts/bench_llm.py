"""Which model can do this project's two jobs, and can a free one do them.

Two jobs, measured the way they are actually used rather than by vibes:

- sorting a link: the production prompt and schema, run over real entries from
  the database, scored on whether every field came back usable and English
- answering a question: the production prompt, run over questions in Russian,
  Ukrainian and English whose answer is a note that really is in the vault,
  scored on whether the search words the model produced put that note in the
  top five of the real index

Usage: .venv/bin/python scripts/bench_llm.py [--jobs search,sort] [--n 10]
"""

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tglinks import ask, categorize, llm, portal  # noqa: E402

SEARCH_MODELS = [
    "groq/openai/gpt-oss-120b",
    "groq/llama-3.3-70b-versatile",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3.5-flash-lite",
    "anthropic/claude-haiku-4-5-20251001",
]
SORT_MODELS = [
    "groq/openai/gpt-oss-120b",
    "groq/llama-3.3-70b-versatile",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3.5-flash-lite",
    "anthropic/claude-sonnet-5",
]

# a question someone would really type, and a note that really is in the vault.
# the target is matched on the title, which is what the model never sees
GOLDEN = [
    ("ru", "сандалии хока", "HOKA Hopara"),
    ("ru", "носки из мериноса", "Merino Wool Socks|Darn Tough"),
    ("uk", "вітрівка з конопель", "Windbreaker"),
    ("ru", "обзор кофемашины", "Wendougee"),
    ("en", "barefoot shoes", "Vivobarefoot"),
    ("ru", "приложение для учёта расходов", "SyncSpend|expenses to Notion"),
    ("ru", "плагин для клода", "Claude Design Plugin"),
    ("ru", "веломаршрут по побережью", "Velo Baltica"),
    ("ru", "мешочек для магнезии", "Chalk Bag"),
    ("ru", "посуда из икеи", "IKEA"),
    ("ru", "где скопировать эмодзи", "EmojiDB"),
    ("ru", "штаны для велосипеда", "Barrel Legged Pant"),
    ("ru", "потолочные вентиляторы", "Ceiling fans"),
    ("ru", "снаряжение для похода лёгкое", "Ultralight Outdoor Gear"),
]

CYRILLIC = re.compile("[а-яёіїєґ]", re.I)
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def sample(limit: int) -> list[dict]:
    """Real entries, spread across the enrichment tiers rather than the first n."""
    conn = sqlite3.connect(ROOT / "data" / "links.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT url, domain, title, description, site_name FROM entry"
        " WHERE url IS NOT NULL ORDER BY cluster_id"
    ).fetchall()
    conn.close()
    step = max(1, len(rows) // limit)
    return [dict(r) for r in rows[::step]][:limit]


async def plan_with(spec: str, question: str, hint: str) -> tuple[dict | None, float, str]:
    tool = llm.Tool(ask.TOOL["name"], ask.TOOL["description"], ask.TOOL["input_schema"])
    start = time.time()
    try:
        data, _ = await llm.call(
            llm.chain(spec), ask.SYSTEM, f"<question>{question}</question>", tool,
            hint=hint, max_tokens=400, timeout=40,
        )
        return data, time.time() - start, ""
    except llm.Unavailable as err:
        return None, time.time() - start, str(err)[:120]


async def sort_with(spec: str, entry: dict) -> tuple[dict | None, float, str]:
    tool = llm.Tool(
        categorize.TOOL["name"], categorize.TOOL["description"], categorize.TOOL["input_schema"]
    )
    prompt = categorize.build_prompt(entry["url"], entry, [])
    start = time.time()
    try:
        data, _ = await llm.call(
            llm.chain(spec), categorize.SYSTEM, prompt, tool, max_tokens=700, timeout=60,
        )
        return data, time.time() - start, ""
    except llm.Unavailable as err:
        return None, time.time() - start, str(err)[:120]


def score_sort(data: dict) -> tuple[int, list[str]]:
    """Six things the note needs, each worth one point."""
    out = categorize.coerce(data)
    bad = []
    points = 0
    if out["category"] in categorize.CATEGORIES and out["category"] != "misc":
        points += 1
    elif out["category"] == "misc":
        bad.append("misc")
    if out["title"] and len(out["title"]) <= 60:
        points += 1
    else:
        bad.append("title")
    if len(out["description"]) >= 40:
        points += 1
    else:
        bad.append("short description")
    if not CYRILLIC.search(out["title"] + out["description"] + " ".join(out["keywords"])):
        points += 1
    else:
        bad.append("not english")
    if len(out["keywords"]) >= 6:
        points += 1
    else:
        bad.append(f"{len(out['keywords'])} keywords")
    if out["tags"] and all(KEBAB.match(t) for t in out["tags"]):
        points += 1
    else:
        bad.append("tags")
    return points, bad


async def run_search(index: portal.Index, models: list[str], pause: float) -> None:
    tags = index.top_tags(60)
    hint = ask.Asker().hint(tags)
    print(f"\n{'=' * 78}\nSEARCH — {len(GOLDEN)} questions, target must land in the top 5\n")
    for spec in models:
        found, took, fails, lines = 0, 0.0, 0, []
        for n, (lang, question, target) in enumerate(GOLDEN):
            if n and pause:
                await asyncio.sleep(pause)
            data, seconds, err = await plan_with(spec, question, hint)
            took += seconds
            if data is None:
                fails += 1
                lines.append(f"    {lang} {question!r} -> FAILED {err}")
                continue
            plan = ask.coerce(data, {t for t, _ in tags})
            picked = [plan["tag"]] if plan["tag"] else []
            hits = index.find(plan["query"], plan["category"], picked, mode="any")
            if not hits and (plan["category"] or picked):
                hits = index.find(plan["query"], mode="any")   # as the endpoint does
            top = [h.title for h in hits[:5]]
            hit = any(re.search(target, t, re.I) for t in top)
            found += hit
            mark = "ok  " if hit else "MISS"
            lines.append(f"    {mark} {question!r} -> {plan['query']!r}"
                         + ("" if hit else f"  got {top[:3]}"))
        print(f"  {spec}")
        print(f"    {found}/{len(GOLDEN)} found, {fails} failed,"
              f" {took / len(GOLDEN):.2f}s per question")
        print("\n".join(lines))


async def run_sort(entries: list[dict], models: list[str], pause: float) -> None:
    print(f"\n{'=' * 78}\nSORT — {len(entries)} real links, six checks each\n")
    for spec in models:
        total, took, fails, bad = 0, 0.0, 0, []
        for n, entry in enumerate(entries):
            if n and pause:
                # the free tiers cap tokens per minute, not just per day, and a
                # benchmark that trips that cap is measuring the cap
                await asyncio.sleep(pause)
            data, seconds, err = await sort_with(spec, entry)
            took += seconds
            if data is None:
                fails += 1
                bad.append(f"{entry['domain']}: FAILED {err}")
                continue
            points, missing = score_sort(data)
            total += points
            if missing:
                bad.append(f"{entry['domain']}: {', '.join(missing)}")
        best = 6 * len(entries)
        print(f"  {spec}")
        print(f"    {total}/{best} points, {fails} failed, {took / len(entries):.2f}s per link")
        for line in bad[:8]:
            print(f"      {line}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", default="search,sort")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--models", default="")
    parser.add_argument("--pause", type=float, default=0.0)
    args = parser.parse_args()

    jobs = args.jobs.split(",")
    if "search" in jobs:
        index = portal.Index(ROOT / "data" / "vault")
        index.load()
        await run_search(index, args.models.split(",") if args.models else SEARCH_MODELS,
                         args.pause)
    if "sort" in jobs:
        await run_sort(sample(args.n), args.models.split(",") if args.models else SORT_MODELS,
                       args.pause)


if __name__ == "__main__":
    asyncio.run(main())
    print(json.dumps({"done": True}))
