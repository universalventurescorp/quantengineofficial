"""Full episode, end to end:
topic -> script (+fact review, real data) -> voice -> archive imagery, data charts, studio footage
-> score -> mix -> render -> thumbnails -> Shorts (scheduled one per day) -> QA -> YouTube

Resumable: if a run dies, rerun with the same --topic and finished steps are skipped.
"""
import argparse
import datetime as dt
import math
import os
import zlib

from .common import (DATA, LANG_NAMES, ROOT, load_config, read_json, slugify,
                     timestamp, write_json)

def build_credits(media):
    sources = sorted({x.get("source", "") for m in media for x in m["images"] + m["clips"]} - {"", "studio"})
    has_studio = any(x.get("source") == "studio" for m in media for x in m["clips"])
    lines = ["Imagery: public-domain and CC0 works from " + (", ".join(sources) or "public archives") +
             ". Museums and archives do not endorse this channel."]
    if has_studio:
        lines.append("Original footage filmed for this channel.")
    if any(c.get("chart") for m in media for c in m["clips"]):
        lines.append("Data: Federal Reserve Economic Data (FRED, Federal Reserve Bank of St. Louis) and the World Bank.")
    lines.append("Narration: AI voice. Script researched, written and fact-checked for this channel. "
                 "Music: original ambient score. Educational content, not financial advice.")
    return "\n".join(lines)


def build_description(script, timing, media):
    lines = ["00:00 Intro"] + [f"{timestamp(c['start'])} {c['title']}" for c in timing["chapters"]]
    return f"{script['description']}\n\nChapters\n" + "\n".join(lines) + f"\n\n{build_credits(media)}"


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def episode_publish_at(cfg, now):
    """Schedule today's episode for the evening slot if we are early enough; else publish now."""
    hour = cfg["upload"].get("publish_hour_utc")
    if hour is None:
        return None
    slot = now.replace(hour=int(hour), minute=0, second=0, microsecond=0)
    return _iso(slot) if slot - now > dt.timedelta(minutes=20) else None


def short_slots(cfg, count, now):
    """One Short per day after the episode, at a fixed hour; a second daily slot only if the queue is full."""
    booked = set(read_json(DATA / "shorts_schedule.json", []))
    hour = int(cfg["shorts"].get("publish_hour_utc", 16))
    slots = []
    day = (now + dt.timedelta(days=1)).date()
    while len(slots) < count:
        for extra in (0, 6):
            t = dt.datetime(day.year, day.month, day.day, hour + extra, tzinfo=dt.timezone.utc)
            iso = _iso(t)
            if iso in booked or (extra and (day - now.date()).days <= 4):
                continue
            slots.append(iso)
            booked.add(iso)
            break
        day += dt.timedelta(days=1)
    keep = sorted(b for b in booked if b >= _iso(now - dt.timedelta(days=2)))
    write_json(DATA / "shorts_schedule.json", keep)
    return slots


def step(n, total, text):
    print(f"[{n}/{total}] {text}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--no-shorts", action="store_true")
    ap.add_argument("--force", action="store_true", help="produce even if today is not an episode day")
    args = ap.parse_args()

    cfg = load_config()
    today = dt.datetime.now(dt.timezone.utc)
    days = cfg.get("schedule", {}).get("episode_days")
    forced = args.force or args.topic or os.environ.get("TOPIC") or os.environ.get("FORCE", "").lower() == "true"
    if days and today.strftime("%a") not in days and not forced:
        print(f"{today:%A}: not an episode day ({', '.join(days)}). Nothing to do.")
        return
    if not forced and any(d.get("date") == today.date().isoformat() and d.get("video_id")
                          for d in read_json(DATA / "done.json", [])):
        print("An episode was already published today. Nothing to do.")
        return
    v = cfg["video"]
    lang = cfg["channel"]["language"]
    assert lang in LANG_NAMES, f"unsupported language {lang}"
    from .topics import next_topic
    topic = args.topic or os.environ.get("TOPIC") or next_topic(cfg)
    do_upload = not args.no_upload and os.environ.get("UPLOAD", "").lower() != "false"
    do_shorts = not args.no_shorts and cfg.get("shorts", {}).get("count", 0) > 0
    out = ROOT / "outputs" / slugify(topic)
    out.mkdir(parents=True, exist_ok=True)
    N = 10
    print(f"== {topic}\n   -> {out}")

    # 1. script
    script = read_json(out / "script.json", None)
    if not script:
        from .script import write_script, write_shorts
        step(1, N, "writing script with Claude")
        script = write_script(topic, cfg)
        script["shorts"] = write_shorts(script, cfg, cfg.get("shorts", {}).get("count", 2)) if do_shorts else []
        write_json(out / "script.json", script)

    # 2. narration + captions
    timing = read_json(out / "timing.json", None)
    if not timing or not (out / "narration.wav").exists():
        from .voice import synthesize
        step(2, N, "narrating")
        timing = synthesize(script, cfg, out)
        write_json(out / "timing.json", timing)
    print(f"   narration: {timing['duration'] / 60:.1f} min")

    # 3. footage per chapter; never reuses media already used on the channel
    used = set(read_json(DATA / "used_assets.json", []))
    media = read_json(out / "media.json", None)
    if not media:
        from .assets import fetch_clips, fetch_images
        from .charts import render_chart_clip
        from .studio import fetch_studio_clips
        step(3, N, "fetching archive imagery, studio footage and drawing data charts")
        spi, media, studio_taken = v["seconds_per_image"], [], set()
        for i, (ch, mark) in enumerate(zip(script["chapters"], timing["chapters"])):
            seconds = mark["end"] - mark["start"]
            want = max(4, math.ceil(seconds / spi * 0.65))
            imgs = fetch_images(ch.get("image_queries", []), want, out / "images", used)
            clips = []
            chart = ch.get("chart")
            if chart:
                try:
                    (out / "charts").mkdir(parents=True, exist_ok=True)
                    c = render_chart_clip(chart["series"], out / "charts" / f"chart_{i + 1}.mp4",
                                          seconds=15, W=v["width"], H=v["height"], fps=v["fps"],
                                          start_year=chart.get("from"), caption=chart.get("caption"))
                    c["chart"] = True
                    clips.append(c)
                except Exception as exc:
                    print(f"   chart for chapter {i + 1} failed: {exc}")
            clips += fetch_studio_clips(cfg, ch.get("image_queries", []) + ch.get("video_queries", []),
                                        v.get("clips_per_chapter", 2), out / "studio", studio_taken,
                                        seconds=13, W=v["width"], H=v["height"], fps=v["fps"])
            if len(clips) < v.get("clips_per_chapter", 2) + bool(chart):
                clips += fetch_clips(ch.get("video_queries", []), 1, out / "clips", used, seconds=12,
                                     W=v["width"], H=v["height"], fps=v["fps"])
            if len(imgs) < 3:                       # archives slow or out of matches: reuse earlier ones
                pool = [im for m in media for im in m["images"] if im not in imgs]
                imgs += pool[-max(6, want // 2):]
                if imgs:
                    print(f"   chapter {i + 1}: reusing {len(imgs)} images from earlier chapters")
            media.append({"images": imgs, "clips": clips})
            print(f"   chapter {i + 1}: {len(imgs)} images, {len(clips)} clips")
        write_json(out / "media.json", media)
        write_json(DATA / "used_assets.json", sorted(used))

    # 4. score
    music = out / "music.wav"
    if not music.exists():
        from .music import make_ambient
        step(4, N, "composing ambient score")
        make_ambient(music, seed=zlib.crc32(topic.encode()))

    # 5. final audio
    audio = out / "audio.wav"
    if not audio.exists():
        from .mix import mix
        step(5, N, "mixing voice and score")
        mix(out / "narration.wav", music, audio, timing["duration"],
            music_volume=cfg["mix"]["music_volume"], lufs=cfg["mix"]["lufs"])

    # 6. picture
    video = out / "video.mp4"
    from .render import build_episode
    shots, _ = build_episode(timing, script, media, cfg)
    write_json(out / "shots.json", shots)
    if not video.exists():
        from .render import render_episode
        step(6, N, "rendering video")
        tmp = out / "video.partial.mp4"
        render_episode(timing, script, media, audio, tmp, cfg)
        tmp.rename(video)

    # 7. thumbnails + metadata
    from .thumbnail import make_thumbnails
    step(7, N, "thumbnails + metadata")
    # thumbnails: the most striking archive image of the whole episode (ranked inside make_thumbnails)
    all_imgs = [i["path"] for m in media for i in m["images"]]
    texts = script.get("thumbnail_texts") or [script.get("thumbnail_text", script["title"])]
    thumbs = make_thumbnails(all_imgs, texts, out)
    meta = {"title": script["title"], "tags": script.get("tags", []),
            "description": build_description(script, timing, media),
            "publish_at": episode_publish_at(cfg, today)}
    write_json(out / "metadata.json", meta)

    # 8. Shorts
    shorts = read_json(out / "shorts.json", None)
    if shorts is None:
        shorts = []
        if do_shorts and script.get("shorts"):
            from .shorts import produce_short
            step(8, N, f"producing {len(script['shorts'])} Shorts")
            fallback = [i for m in media for i in m["images"]]
            for k, s in enumerate(script["shorts"], 1):
                try:
                    r = produce_short(s, k, cfg, out / "shorts", used, music, fallback)
                    if r:
                        shorts.append(r)
                except Exception as exc:
                    print(f"   short {k} failed: {exc}")
            write_json(DATA / "used_assets.json", sorted(used))
        write_json(out / "shorts.json", shorts)

    # 9. QA gate
    from .qa import check_episode
    step(9, N, "quality check")
    report = check_episode(out, script, timing, media, shots, video)
    print(f"   QA {'PASSED' if report['ok'] else 'FAILED'}: {report['minutes']} min, "
          f"{report['lufs']} LUFS, {report['clips']} clips")
    for f in report["fails"]:
        print(f"   FAIL: {f}")
    for w in report["warnings"]:
        print(f"   warn: {w}")

    # 10. upload
    video_id, short_ids = None, []
    from .upload import has_credentials, upload
    if do_upload and has_credentials() and report["ok"]:
        step(10, N, "uploading to YouTube")
        video_id = upload(video, meta, cfg, thumbnail=thumbs[0] if thumbs else None,
                          captions=out / "captions.srt")
        print(f"   https://youtu.be/{video_id}")
        slots = short_slots(cfg, len(shorts), today)
        for s, slot in zip(shorts, slots):
            smeta = {"title": s["title"], "tags": script.get("tags", [])[:8], "publish_at": slot,
                     "description": f"{s['narration'][:300]}\n\nFull documentary: https://youtu.be/{video_id}"
                                    f"\n\n#Shorts #history #money"}
            try:
                sid = upload(s["path"], smeta, cfg)
                short_ids.append(sid)
                print(f"   short: https://youtu.be/{sid} (public {slot})")
            except Exception as exc:
                print(f"   short upload failed: {exc}")
    else:
        why = ("QA failed" if not report["ok"] else "no credentials" if not has_credentials()
               else "upload disabled")
        step(10, N, f"upload skipped ({why})")

    done = read_json(DATA / "done.json", [])
    done.append({"topic": topic, "title": script["title"], "video_id": video_id, "shorts": short_ids,
                 "minutes": round(timing["duration"] / 60, 1), "qa_ok": report["ok"],
                 "date": dt.date.today().isoformat()})
    write_json(DATA / "done.json", done)
    if not report["ok"]:
        raise SystemExit("QA failed: see outputs/*/qa.json")
    print("done.")


if __name__ == "__main__":
    from .script import ClaudeLimitReached
    try:
        main()
    except ClaudeLimitReached as exc:
        print(f"\nSTOPPED: {exc}")
        raise SystemExit(1)
