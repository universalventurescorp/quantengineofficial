"""Writing with Claude Code in headless mode (`claude -p`), using your Claude plan.
If the plan's usage limit is reached (or Claude is unavailable) and GEMINI_API_KEY is set,
the same prompts go to Google's Gemini API (free tier) so the channel never stops.

outline -> chapters -> cold open -> science/TTS review pass -> Shorts scripts
"""
import json
import os
import re
import subprocess
import time

import requests

from .common import ROOT, LANG_NAMES, extract_json

PROMPTS = ROOT / "prompts"
INSTRUCTION = ("Follow the instructions in the input exactly. Reply with only the requested output, "
               "without any preamble or commentary.")


LIMIT_HINTS = ("limit", "quota", "usage", "rate", "credit", "exceeded", "unauthorized", "401", "403")
_claude_out = False            # once Claude hits its limit in a run, skip straight to the fallback
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def ask_gemini(prompt, timeout=600, retries=4):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no GEMINI_API_KEY for fallback")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 16384}}
    last = ""
    for attempt in range(retries):
        try:
            r = requests.post(url, params={"key": key}, json=body, timeout=timeout)
            if r.status_code == 200:
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
            last = r.text[-800:]
            if r.status_code == 429:                      # free-tier rate limit: wait it out
                time.sleep(60 * (attempt + 1))
                continue
        except Exception as exc:
            last = str(exc)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Gemini failed: {last}")


def ask_claude(prompt, timeout=1500, retries=3):
    global _claude_out
    last = ""
    if not _claude_out:
        for attempt in range(retries):
            try:
                r = subprocess.run(["claude", "-p", INSTRUCTION], input=prompt, capture_output=True,
                                   text=True, timeout=timeout)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
                last = (r.stderr or r.stdout)[-1500:]
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                last = str(exc) or "timeout"
            if any(h in last.lower() for h in LIMIT_HINTS) and os.environ.get("GEMINI_API_KEY"):
                break                                     # plan limit: no point retrying Claude
            time.sleep(45 * (attempt + 1))
        if os.environ.get("GEMINI_API_KEY"):
            _claude_out = True
            print(f"    Claude unavailable ({last.strip()[:160]}); using Gemini for the rest of this run")
    if os.environ.get("GEMINI_API_KEY"):
        return ask_gemini(prompt)
    raise RuntimeError(f"claude -p failed: {last}")


def ask_json(prompt, check, tries=3):
    for _ in range(tries):
        try:
            data = extract_json(ask_claude(prompt))
            if check(data):
                return data
        except (ValueError, json.JSONDecodeError):
            pass
    raise RuntimeError("Claude did not return valid JSON")


def fill(name, **values):
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"<<{key}>>", str(value))
    return text


def clean(text, chapter_title=""):
    text = re.sub(r"```.*?\n|```", "", text)
    title = chapter_title.strip().lower().rstrip(".:")
    kept = []
    for line in text.splitlines():
        s = line.strip()
        bare = s.strip("*_# ").rstrip(".:").lower()
        if s.startswith(("#", "---")):
            continue                                   # markdown headings / rules
        if re.match(r"^(chapter|cap[ií]tulo)\s+\w+\s*[:.\-]", bare) or re.match(r"^(chapter|cap[ií]tulo)\s+\w+$", bare):
            continue                                   # "Chapter 5: ..." would be read aloud
        if title and bare == title:
            continue                                   # chapter title repeated as a line
        kept.append(line)
    text = "\n".join(kept).replace("*", "").replace("_", " ")
    text = text.replace("!", ".")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _first_words(text, n=8):
    return " ".join(text.split()[:n])


def apply_fixes(sections, fixes):
    """sections: dict id -> text. Applies exact find/replace fixes; returns count applied."""
    applied = 0
    for fx in fixes if isinstance(fixes, list) else []:
        sid, find, rep = fx.get("section"), fx.get("find", ""), fx.get("replace", "")
        if sid in sections and find and len(find) >= 12 and find in sections[sid] and "\n" not in rep:
            sections[sid] = sections[sid].replace(find, rep, 1)
            applied += 1
    return applied


def _chart_data(chapters):
    """Fetch the data behind each requested chart; drop charts whose data cannot be fetched.
    Returns {chapter index: facts text}."""
    from .catalog import is_valid_key
    from .charts import facts_text, fetch

    facts = {}
    for i, c in enumerate(chapters):
        chart = c.get("chart")
        if not isinstance(chart, dict) or not is_valid_key(str(chart.get("series", ""))):
            c["chart"] = None
            continue
        try:
            data = fetch(chart["series"])
            if chart.get("from"):
                keep = [k for k, d in enumerate(data["dates"]) if d.year >= int(chart["from"])]
                if len(keep) >= 8:
                    data = {"dates": [data["dates"][k] for k in keep],
                            "values": [data["values"][k] for k in keep], "meta": data["meta"]}
            facts[i] = facts_text(chart["series"], data)
        except Exception as exc:
            print(f"    chart '{chart.get('series')}' dropped: {exc}")
            c["chart"] = None
    return facts


def write_script(topic, cfg):
    from .catalog import catalog_for_prompt

    ch, minutes = cfg["channel"], cfg["video"]["target_minutes"]
    n_chapters = max(5, round(minutes / 6.5))
    lang = LANG_NAMES[ch["language"]]

    print("  outline")
    outline = ask_json(
        fill("outline.md", CHANNEL=ch["name"], LANGUAGE=lang, TOPIC=topic,
             MINUTES=minutes, CHAPTERS=n_chapters, CATALOG=catalog_for_prompt()),
        lambda d: isinstance(d, dict) and d.get("title") and len(d.get("chapters", [])) >= 3)
    chapters = outline["chapters"]
    for c in chapters:
        c.setdefault("video_queries", [])
        c.setdefault("image_queries", [])
    facts = _chart_data(chapters)
    print(f"  data charts: {len(facts)}")
    words = int(minutes * cfg["voice"]["wpm"] / len(chapters))
    plan = json.dumps({"title": outline["title"],
                       "chapters": [{"title": c["title"], "beats": c["beats"]} for c in chapters]},
                      ensure_ascii=False)

    previous, openings = "(this is the first chapter, right after the opening title)", []
    for i, c in enumerate(chapters, 1):
        last = i == len(chapters)
        ending = ("This is the final chapter: close the journey with a slow, peaceful reflection "
                  "on what money really is, and a soft goodnight. Do not ask for likes or subscriptions."
                  if last else
                  "Do not wrap up or summarize the episode; flow naturally toward the next chapter.")
        text = clean(ask_claude(fill(
            "chapter.md", CHANNEL=ch["name"], LANGUAGE=lang, OUTLINE=plan, N=i,
            TOTAL=len(chapters), CHAPTER_TITLE=c["title"], BEATS="; ".join(c["beats"]),
            WORDS=words, PREVIOUS=previous, ENDING_RULE=ending,
            OPENINGS="; ".join(openings) or "(none yet)",
            DATA=("Exact data figures for this chapter (an animated chart of this series appears on screen; "
                  "mention one or two of these figures naturally, spelled out):\n" + facts[i - 1])
            if (i - 1) in facts else "")), c["title"])
        c["text"] = text
        previous = text.split("\n\n")[-1][-500:]
        openings.append(f'"{_first_words(text)}..."')
        print(f"  chapter {i}/{len(chapters)}: {len(text.split())} words")

    print("  cold open")
    outline["cold_open"] = clean(ask_claude(fill(
        "cold_open.md", CHANNEL=ch["name"], LANGUAGE=lang, TITLE=outline["title"],
        PROMISE=outline.get("hook_promise", ""), CHAPTERS="; ".join(c["title"] for c in chapters),
        FIRST=_first_words(chapters[0]["text"], 30))))

    print("  science & TTS review")
    sections = {"cold_open": outline["cold_open"]}
    sections.update({f"chapter_{i}": c["text"] for i, c in enumerate(chapters, 1)})
    full = "\n\n".join(f"[{k}]\n{v}" for k, v in sections.items())
    try:
        fixes = extract_json(ask_claude(fill("review.md", CHANNEL=ch["name"], SCRIPT=full,
                                             DATA="\n\n".join(facts.values()) or "(none)")))
        n = apply_fixes(sections, fixes)
        outline["review"] = {"suggested": len(fixes) if isinstance(fixes, list) else 0, "applied": n,
                             "fixes": fixes if isinstance(fixes, list) else []}
        print(f"    applied {n} fixes")
    except Exception as exc:
        print(f"    review skipped: {exc}")
    outline["cold_open"] = sections["cold_open"]
    for i, c in enumerate(chapters, 1):
        c["text"] = sections[f"chapter_{i}"]

    outline["topic"] = topic
    return outline


def write_shorts(script, cfg, count=2):
    ch = cfg["channel"]
    text = "\n\n".join(c["text"] for c in script["chapters"])
    try:
        shorts = ask_json(
            fill("shorts.md", CHANNEL=ch["name"], LANGUAGE=LANG_NAMES[ch["language"]],
                 TITLE=script["title"], SCRIPT=text[:60000], COUNT=count),
            lambda d: isinstance(d, list) and d and all(s.get("narration") for s in d))
    except Exception as exc:
        print(f"  shorts skipped: {exc}")
        return []
    for s in shorts:
        s["narration"] = clean(s["narration"])
    return shorts[:count]
