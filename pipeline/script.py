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

from .common import DATA, ROOT, LANG_NAMES, extract_json

PROMPTS = ROOT / "prompts"
INSTRUCTION = ("Follow the instructions in the input exactly. Reply with only the requested output, "
               "without any preamble or commentary.")


LIMIT_RE = re.compile(r"hit your .{0,20}limit|usage limit|weekly limit|session limit|limit reached|"
                      r"out of (?:usage|credits)|resets \w+ \d", re.I)
_claude_out = False            # once Claude hits its limit in a run, skip straight to the fallback


class ClaudeLimitReached(RuntimeError):
    """The Claude plan's usage limit is spent. Retrying only wastes time."""


def _claude_cfg():
    from .common import load_config
    c = (load_config().get("claude") or {})
    return (os.environ.get("CLAUDE_MODEL") or c.get("model") or "sonnet",
            (c.get("on_limit") or "gemini").lower())
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
_gemini_model = os.environ.get("GEMINI_MODEL")


_gemini_spent = set()        # models whose free daily quota is used up in this run


def _gemini_candidates(key):
    """Available text models, best first: newest full 'flash', then 'flash-lite', then the rest.
    Each model has its own free daily quota, so working down the list keeps the channel running."""
    try:
        r = requests.get(f"{GEMINI_API}/models", params={"key": key, "pageSize": 200}, timeout=30)
        names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:
        names = []
    bad = ("image", "tts", "audio", "live", "embedding", "robotics", "computer-use", "nano", "gemma")
    names = [n for n in names if not any(b in n for b in bad)]

    def version(n):
        nums = re.findall(r"\d+(?:\.\d+)?", n)
        return float(nums[0]) if nums else 0.0

    def rank(n):
        tier = 0 if ("flash" in n and "lite" not in n) else 1 if "lite" in n else 2 if "pro" in n else 3
        unstable = any(x in n for x in ("exp", "preview", "thinking"))
        return (tier, unstable, -version(n))
    return sorted(names, key=rank)


def _pick_gemini_model(key, hint=None):
    """Newest available 'flash' model that supports generateContent (Google retires names often)."""
    if hint:
        return hint
    for n in _gemini_candidates(key):
        if n not in _gemini_spent:
            return n
    return "gemini-flash-latest"


def ask_gemini(prompt, timeout=600, retries=8):
    global _gemini_model
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no GEMINI_API_KEY for fallback")
    if not _gemini_model:
        _gemini_model = _pick_gemini_model(key)
        print(f"    Gemini model: {_gemini_model}")
    body = {"systemInstruction": {"parts": [{"text": INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 16384}}
    last = ""
    for attempt in range(retries):
        url = f"{GEMINI_API}/models/{_gemini_model}:generateContent"
        try:
            r = requests.post(url, params={"key": key}, json=body, timeout=timeout)
            if r.status_code == 200:
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
            last = r.text[-800:]
            if r.status_code == 404:                      # model retired: follow Google's suggestion
                m = re.search(r"models/([\w.\-]+) for the latest", r.text)
                _gemini_model = _pick_gemini_model(key, m.group(1) if m else None)
                print(f"    Gemini model switched to {_gemini_model}")
                continue
            if r.status_code == 429:
                daily = "PerDay" in r.text or re.search(r'"retryDelay": "(\d{4,})s"', r.text)
                if daily:                                 # this model's free quota is spent for today
                    _gemini_spent.add(_gemini_model)
                    nxt = _pick_gemini_model(key)
                    if nxt in _gemini_spent or nxt == _gemini_model:
                        break
                    print(f"    Gemini {_gemini_model} daily quota used; switching to {nxt}")
                    _gemini_model = nxt
                    continue
                time.sleep(60 * (attempt + 1))            # per-minute limit: wait it out
                continue
        except Exception as exc:
            last = str(exc)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Gemini failed: {last}")


USAGE_LOG = DATA / "usage" / "claude.jsonl"   # one line per call: lets us see how much of the plan each video uses


def _log_usage(model, info, prompt_chars, ok):
    """Append this call's token usage (from `--output-format json`) to data/usage/claude.jsonl."""
    try:
        u = info.get("usage") or {}
        row = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "run": os.environ.get("GITHUB_RUN_ID", "local"),
               "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
               "channel": os.environ.get("CHANNEL", ""), "model": model, "ok": ok,
               "in": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
               "cache_read": u.get("cache_read_input_tokens", 0), "out": u.get("output_tokens", 0),
               "usd_equiv": info.get("total_cost_usd"), "turns": info.get("num_turns"),
               "secs": round((info.get("duration_ms") or 0) / 1000), "prompt_chars": prompt_chars}
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as exc:            # measuring must never break an episode
        print(f"    (usage log skipped: {exc})")


def _claude_call(model, prompt, timeout):
    """Run `claude -p` once. Returns (returncode, text, stderr) with text = the reply only."""
    r = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", INSTRUCTION],
                       input=prompt, capture_output=True, text=True, timeout=timeout)
    out = r.stdout.strip()
    try:
        info = json.loads(out)
    except (ValueError, json.JSONDecodeError):
        return r.returncode, out, r.stderr            # older CLI / plain text: behave as before
    if not isinstance(info, dict):
        return r.returncode, out, r.stderr
    text = str(info.get("result") or "").strip()
    bad = bool(info.get("is_error")) or info.get("subtype", "success") != "success"
    _log_usage(model, info, len(prompt), not bad and r.returncode == 0)
    return (1 if bad else r.returncode), text, r.stderr


def ask_claude(prompt, timeout=1500, retries=3):
    """One call to Claude Code headless (`claude -p --model <config claude.model>`).
    On the plan's usage limit: never retry. Fall back to Gemini if claude.on_limit is 'gemini' and
    GEMINI_API_KEY is set; otherwise stop the run with a clear message."""
    global _claude_out
    model, on_limit = _claude_cfg()
    use_gemini = on_limit == "gemini" and bool(os.environ.get("GEMINI_API_KEY"))
    last, limited = "", False
    if not _claude_out:
        for attempt in range(retries):
            try:
                code, text, err = _claude_call(model, prompt, timeout)
                if code == 0 and text and not LIMIT_RE.search(text[:300]):
                    return text
                last = (err + "\n" + text).strip()[-1500:]
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                last = str(exc) or "timeout"
            if LIMIT_RE.search(last):
                limited = True
                break                                     # plan limit: retrying cannot help
            time.sleep(45 * (attempt + 1))
        if limited and not use_gemini:
            raise ClaudeLimitReached(
                f"Claude plan usage limit reached ({last.strip()[:200]}). Stopping without retrying; "
                f"the episode will be produced on the next scheduled day.")
        if use_gemini:
            _claude_out = True
            print(f"    Claude unavailable ({last.strip()[:160]}); using Gemini for the rest of this run")
    if use_gemini:
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


TITLE_LABEL = "Calm History for Sleep: "


def branded_title(title):
    """1-nov-2026: every title starts with what the video is for (the thumbnail says SLEEP), then the topic."""
    t = re.sub(r"\s*[|:–-]\s*(calm|relaxing|sleep|history for|documentary)[^|]*$", "", title.strip(), flags=re.I)
    t = re.sub(r"^(calm history for sleep|history for sleep|sleep)\s*[:|-]\s*", "", t, flags=re.I).strip()
    return (TITLE_LABEL + t)[:100]


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
    outline["title"] = branded_title(outline["title"])
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
    group = max(1, int(cfg.get("script", {}).get("chapters_per_call", 3)))
    for start in range(0, len(chapters), group):
        batch = list(enumerate(chapters[start:start + group], start + 1))
        texts = _write_batch(batch, chapters, ch, lang, plan, words, previous, openings, facts) if group > 1 else None
        if not texts:
            texts = {}
            for i, c in batch:
                texts[i] = _write_one(i, c, chapters, ch, lang, plan, words, previous, openings, facts)
                previous = texts[i].split("\n\n")[-1][-500:]
                openings.append(f'"{_first_words(texts[i])}..."')
        for i, c in batch:
            c["text"] = texts[i]
            print(f"  chapter {i}/{len(chapters)}: {len(c['text'].split())} words")
        previous = chapters[batch[-1][0] - 1]["text"].split("\n\n")[-1][-500:]
        openings = [f'"{_first_words(c["text"])}..."' for c in chapters[:batch[-1][0]]]

    _after_chapters(outline, chapters, ch, lang, facts)
    add_companion(outline, cfg)
    outline["topic"] = topic
    return outline


def _ending(i, total):
    return ("This is the final chapter: close the journey with a slow, peaceful reflection "
            "on what money really is, and a soft goodnight. Do not ask for likes or subscriptions."
            if i == total else
            "Do not wrap up or summarize the episode; flow naturally toward the next chapter.")


def _data_note(indexes, facts):
    notes = [f"Chapter {i}:\n{facts[i - 1]}" for i in indexes if (i - 1) in facts]
    return ("Exact data figures (an animated chart of this series appears on screen during that chapter; "
            "mention one or two of these figures naturally, spelled out):\n" + "\n\n".join(notes)) if notes else ""


def _write_batch(batch, chapters, ch, lang, plan, words, previous, openings, facts):
    total = len(chapters)
    listing = "\n".join(f"Chapter {i}: \"{c['title']}\". Beats, in order: {'; '.join(c['beats'])}" for i, c in batch)
    last = batch[-1][0]
    try:
        raw = ask_claude(fill(
            "chapters.md", CHANNEL=ch["name"], LANGUAGE=lang, OUTLINE=plan, FIRST_N=batch[0][0], LAST_N=last,
            TOTAL=total, WORDS=words, CHAPTER_LIST=listing, PREVIOUS=previous,
            OPENINGS="; ".join(openings[-6:]) or "(none yet)", DATA=_data_note([i for i, _ in batch], facts),
            ENDING_RULE=(f"Chapter {last} is the final chapter of the episode: " + _ending(last, total)
                         if last == total else _ending(0, total))))
    except Exception as exc:
        print(f"    batch {batch[0][0]}-{last} failed ({exc}); writing one by one")
        return None
    parts = re.split(r"(?m)^\s*=+\s*CHAPTER\s+(\d+)\s*=+\s*$", raw)
    texts = {}
    for k in range(1, len(parts) - 1, 2):
        texts[int(parts[k])] = parts[k + 1]
    out = {}
    for i, c in batch:
        t = clean(texts.get(i, ""), c["title"])
        if len(t.split()) < words * 0.45:
            print(f"    chapter {i} came back short or missing in the batch; writing it alone")
            return None
        out[i] = t
    return out


def _write_one(i, c, chapters, ch, lang, plan, words, previous, openings, facts):
    return clean(ask_claude(fill(
        "chapter.md", CHANNEL=ch["name"], LANGUAGE=lang, OUTLINE=plan, N=i,
        TOTAL=len(chapters), CHAPTER_TITLE=c["title"], BEATS="; ".join(c["beats"]),
        WORDS=words, PREVIOUS=previous, ENDING_RULE=_ending(i, len(chapters)),
        OPENINGS="; ".join(openings) or "(none yet)", DATA=_data_note([i], facts))), c["title"])


def _after_chapters(outline, chapters, ch, lang, facts):
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
        fixes = ask_json(fill("review.md", CHANNEL=ch["name"], SCRIPT=full,
                              DATA="\n\n".join(facts.values()) or "(none)"),
                         lambda d: isinstance(d, list))
        n = apply_fixes(sections, fixes)
        outline["review"] = {"suggested": len(fixes) if isinstance(fixes, list) else 0, "applied": n,
                             "fixes": fixes if isinstance(fixes, list) else []}
        print(f"    applied {n} fixes")
    except Exception as exc:
        print(f"    review skipped: {exc}")
    outline["cold_open"] = with_subscribe_line(sections["cold_open"], ch.get("subscribe_line"))
    for i, c in enumerate(chapters, 1):
        c["text"] = sections[f"chapter_{i}"]


def with_subscribe_line(cold_open, line):
    """Fixed, calm subscribe request placed just before the cold open's last line (the lead-in to the title card):
    asked once, in the first minute, while the listener is still awake (same as Estrato Nocturno)."""
    if not line:
        return cold_open
    paras = [p for p in cold_open.split("\n\n") if p.strip()]
    return "\n\n".join(paras[:-1] + [line.strip()] + paras[-1:]) if paras else line.strip()


def _paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _norm(p):
    return " ".join(p.split())


def companion_slots(chapters, every_min, wpm, first_min=None):
    """About every `every_min` minutes of narration, at a paragraph break inside a chapter (never right after the
    chapter card or at its very end). Returns [(chapter_index, paragraph_index_to_insert_before)]."""
    first_min = every_min if first_min is None else first_min
    marks, words = [], 0
    for ci, c in enumerate(chapters):
        ps = _paras(c["text"])
        for pi, p in enumerate(ps):
            if 2 <= pi <= len(ps) - 2:
                marks.append((words / wpm, ci, pi))
            words += len(p.split())
    slots, target, total = [], first_min, words / wpm
    while target < total - 1.5:
        cands = [m for m in marks if abs(m[0] - target) <= every_min * 0.5 and (m[1], m[2]) not in slots]
        if cands:
            best = min(cands, key=lambda m: abs(m[0] - target))
            slots.append((best[1], best[2]))
        target += every_min
    return slots


def add_companion(outline, cfg):
    """31-oct-2026, from Estrato Nocturno: short moments where the narrator speaks to the one listener awake at
    night, about every companion.every_minutes. Listed in chapter["companion"] so the voice says them softer
    and the Shorts leave them out."""
    comp, ch = cfg.get("companion") or {}, cfg["channel"]
    if not comp.get("enabled"):
        return
    chapters, wpm = outline["chapters"], cfg["voice"]["wpm"]
    starts, words = {}, 0
    for ci, c in enumerate(chapters):
        for pi, p in enumerate(_paras(c["text"])):
            starts[(ci, pi)] = words / wpm
            words += len(p.split())
    slots = companion_slots(chapters, comp.get("every_minutes", 11), wpm, comp.get("first_minute"))
    if not slots:
        return
    blocks = []
    for k, (ci, pi) in enumerate(slots, 1):
        ps = _paras(chapters[ci]["text"])
        blocks.append(f"Place {k}:\nBEFORE: {ps[pi - 1]}\nAFTER: {ps[pi]}")
    try:
        lines = ask_json(fill("companion.md", CHANNEL=ch["name"], LANGUAGE=LANG_NAMES[ch["language"]],
                              TITLE=outline["title"], COUNT=len(slots), SLOTS="\n\n".join(blocks)),
                         lambda d: isinstance(d, list) and len(d) == len(slots) and all(isinstance(x, str) for x in d))
    except Exception as exc:
        print(f"  companion skipped: {exc}")
        return
    for k in sorted(range(len(slots)), key=lambda k: slots[k], reverse=True):   # insert back to front
        ci, pi = slots[k]
        line = clean(lines[k]).replace("\n", " ").strip()
        if not line:
            continue
        ps = _paras(chapters[ci]["text"])
        chapters[ci]["text"] = "\n\n".join(ps[:pi] + [line] + ps[pi:])
        chapters[ci].setdefault("companion", []).append(line)
    times = sorted(round(starts[s], 1) for s in slots)
    outline["companion"] = {"count": len(slots), "minutes": times}
    print(f"  companion: {len(slots)} moments at ~{times} min")


def story_text(chapter):
    """A chapter's narration without the companion moments (for the Shorts)."""
    soft = {_norm(p) for p in chapter.get("companion", [])}
    return "\n\n".join(p for p in _paras(chapter["text"]) if _norm(p) not in soft)


def write_shorts(script, cfg, count=2):
    ch = cfg["channel"]
    text = "\n\n".join(story_text(c) for c in script["chapters"])
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
