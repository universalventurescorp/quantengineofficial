"""Topic queue that refills itself with Claude when it runs low, learning from what performed best."""
import json

from .common import DATA, LANG_NAMES, extract_json, read_json, write_json
from .script import ask_claude


def next_topic(cfg):
    backlog = read_json(DATA / "topics.json", [])
    done = {d["topic"] for d in read_json(DATA / "done.json", [])}
    remaining = [t for t in backlog if t not in done]
    if len(remaining) < 5:
        fresh = [t for t in generate_topics(cfg, backlog) if t not in backlog]
        backlog += fresh
        write_json(DATA / "topics.json", backlog)
        remaining = [t for t in backlog if t not in done]
    if not remaining:
        raise SystemExit("No topics left")
    return remaining[0]


def _performance_notes():
    """Best and worst episodes by views per day (written weekly by pipeline/analytics.py)."""
    stats = read_json(DATA / "analytics.json", {}).get("episodes", [])
    if len(stats) < 4:
        return "Not enough published episodes yet to learn from."
    ranked = sorted(stats, key=lambda s: -s.get("views_per_day", 0))
    fmt = lambda s: (f'"{s["title"]}": {s.get("views_per_day", 0):.0f} views/day, '
                     f'average viewed {s.get("avg_view_minutes", "?")} min')
    return ("Best performing so far:\n" + "\n".join(fmt(s) for s in ranked[:5]) +
            "\nWeakest so far:\n" + "\n".join(fmt(s) for s in ranked[-3:]))


def generate_topics(cfg, existing):
    ch = cfg["channel"]
    prompt = f"""You plan episodes for "{ch['name']}", a YouTube channel of calm, cinematic long-form documentaries about the history of money, markets, empires, trade, crises and economic ideas, made for relaxing and falling asleep, narrated in {LANG_NAMES[ch['language']]}.
Episodes already made or planned: {json.dumps(existing[-120:], ensure_ascii=False)}

What the audience has responded to:
{_performance_notes()}

Propose 20 NEW episode topics that (1) people actively search for on YouTube (history of money, famous bubbles and crashes, empires and their finances, how things like banks, gold, inflation and stock markets really work), (2) have enough well-documented history for a {cfg['video']['target_minutes']}-minute episode, (3) have beautiful archival imagery available (coins, paintings, engravings, historic photographs), and (4) do not overlap with the list. Lean toward the kinds of topics that performed best, but keep variety.
Return ONLY a JSON array of 20 strings, each a one-line topic brief."""
    try:
        return [str(t).strip() for t in extract_json(ask_claude(prompt))][:20]
    except Exception as exc:
        print(f"  topic refill failed: {exc}")
        return []
