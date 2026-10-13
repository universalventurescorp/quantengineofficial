"""Archive imagery and footage, all free and openly licensed:

  The Metropolitan Museum of Art Open Access   (CC0: coins, art, objects)       no key
  Art Institute of Chicago                      (CC0 public-domain artworks)     no key
  Wikimedia Commons                             (public domain / CC0 only)       no key

Stills that are not 16:9 (coins, portraits, paintings) are composed onto a 16:9 canvas over a
blurred, darkened copy of themselves, so they always fill the frame without awkward crops.
Bright, flat images (white-paper documents, catalogue shots on white) are rejected: the channel
is watched at night.
"""
import io
import json
import re
import subprocess

import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from .common import slugify

Image.MAX_IMAGE_PIXELS = None
MAX_IMG_BYTES = 60 * 1024 * 1024
MAX_VID_BYTES = 400 * 1024 * 1024
UA = {"User-Agent": "TheQuietLedger/1.0 (YouTube documentary pipeline; contact via channel)"}
CANVAS = (2880, 1620)

BLOCK = (
    "nude", "naked", "venus", "bather", "erotic", "crucifixion", "execution", "massacre", "corpse",
    "skull", "torture", "battle", "war", "wounded", "blood", "martyrdom", "beheading", "hanging",
    "logo", "diagram", "chart", "screenshot", "map of", "letter to", "page from", "text",
)
FALLBACK_QUERIES = ["gold coin", "silver coin ancient", "merchant painting", "still life candle",
                    "harbor ships painting", "old city at night painting", "gold", "money changer"]


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 30), **kw)
    r.raise_for_status()
    return r


_BLOCK_RE = re.compile(r"\b(?:" + "|".join(re.escape(b) for b in BLOCK) + r")\b")


def _blocked(text):
    return bool(_BLOCK_RE.search(text.lower()))


# ------------------------------------------------------------------ candidate search per archive
def _met(query, n=25):
    ids = (_get("https://collectionapi.metmuseum.org/public/collection/v1/search",
                params={"q": query, "hasImages": "true"}).json().get("objectIDs") or [])[:n]
    for oid in ids:
        try:
            o = _get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}").json()
        except Exception:
            continue
        if o.get("isPublicDomain") and o.get("primaryImage"):
            yield {"id": f"met:{oid}", "url": o["primaryImage"],
                   "title": f"{o.get('title', '')}, {o.get('objectDate', '')}".strip(", "),
                   "source": "The Metropolitan Museum of Art (CC0)",
                   "text": " ".join([o.get("title", ""), o.get("classification", ""), o.get("tags") and
                                     " ".join(t.get("term", "") for t in o["tags"]) or ""])}


def _aic(query, n=20):
    r = _get("https://api.artic.edu/api/v1/artworks/search",
             params={"q": query, "query[term][is_public_domain]": "true", "limit": n,
                     "fields": "id,title,image_id,date_display,artist_title,classification_title"}).json()
    for a in r.get("data", []):
        if a.get("image_id"):
            yield {"id": f"aic:{a['id']}",
                   "url": f"https://www.artic.edu/iiif/2/{a['image_id']}/full/1686,/0/default.jpg",
                   "title": f"{a.get('title', '')}, {a.get('artist_title') or ''} {a.get('date_display') or ''}".strip(", "),
                   "source": "Art Institute of Chicago (CC0)",
                   "text": " ".join(str(a.get(k) or "") for k in ("title", "classification_title"))}


def _commons_license_ok(meta):
    lic = (meta.get("License", {}).get("value") or "").lower()
    short = (meta.get("LicenseShortName", {}).get("value") or "").lower()
    return lic.startswith("pd") or lic == "cc0" or "public domain" in short or short == "cc0"


def _commons(query, kind="bitmap", n=30):
    r = _get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:{kind}", "gsrlimit": n, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 3840}).json()
    pages = sorted((r.get("query", {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        if not _commons_license_ok(meta):
            continue
        desc = re.sub(r"<[^>]+>", " ", meta.get("ImageDescription", {}).get("value", ""))[:400]
        url = info.get("url") if kind == "video" else (info.get("thumburl") or info.get("url"))
        yield {"id": f"commons:{p.get('pageid')}", "url": url, "title": p.get("title", "").replace("File:", ""),
               "source": "Wikimedia Commons (public domain)", "text": f"{p.get('title', '')} {desc}",
               "width": info.get("width", 0), "duration": info.get("duration", 0)}


SOURCES = (_met, _aic, _commons)


# ------------------------------------------------------------------ stills
def _interest(im):
    small = im.copy()
    small.thumbnail((256, 256))
    gray = ImageStat.Stat(small.convert("L"))
    hsv = ImageStat.Stat(small.convert("HSV"))
    std, mean, sat = gray.stddev[0], gray.mean[0], hsv.mean[1]
    if std < 16 or mean > 195 or (mean > 165 and sat < 45):
        return None                                   # flat, or bright paper / white background
    return std + sat * 0.45 - max(0.0, mean - 125) * 0.9


def compose_16x9(im, size=CANVAS):
    """Cover-fit wide images; centre narrow ones over a blurred, darkened copy of themselves."""
    W, H = size
    ratio = im.width / im.height
    if ratio >= 1.55:
        return ImageOps.fit(im, size, Image.LANCZOS)
    bg = ImageOps.fit(im, (W // 4, H // 4), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))
    bg = ImageEnhance.Brightness(bg.resize(size, Image.BICUBIC)).enhance(0.38)
    fg = im.copy()
    fg.thumbnail((int(W * 0.86), int(H * 0.88)), Image.LANCZOS)
    mask = Image.new("L", fg.size, 255)
    edge = max(4, fg.width // 80)
    mask = ImageOps.expand(ImageOps.crop(mask, edge), edge, 0).filter(ImageFilter.GaussianBlur(edge))
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2), mask)
    return bg


def _download_image(url, path):
    with requests.get(url, stream=True, headers=UA, timeout=60) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        for chunk in r.iter_content(1 << 20):
            buf.write(chunk)
            if buf.tell() > MAX_IMG_BYTES:
                return None
    im = Image.open(buf).convert("RGB")
    if max(im.size) < 1100 or im.width / im.height < 0.55:
        return None
    score = _interest(im)
    if score is None:
        return None
    compose_16x9(im).save(path, "JPEG", quality=92)
    return score


def fetch_images(queries, want, out_dir, used, per_query=3):
    out_dir.mkdir(parents=True, exist_ok=True)
    got, seen = [], set()
    for allow_used in (False, True):
        for query in list(queries) + FALLBACK_QUERIES:
            if len(got) >= want:
                break
            taken = 0
            for source in SOURCES:
                if taken >= per_query or len(got) >= want:
                    break
                try:
                    for cand in source(query):
                        if taken >= per_query or len(got) >= want:
                            break
                        cid = cand["id"]
                        if cid in seen or (cid in used and not allow_used) or _blocked(cand["text"]):
                            continue
                        seen.add(cid)
                        path = out_dir / f"{slugify(cid)}.jpg"
                        try:
                            score = _download_image(cand["url"], path)
                        except Exception:
                            score = None
                        if score is not None:
                            used.add(cid)
                            got.append({"path": str(path), "id": cid, "title": cand["title"],
                                        "source": cand["source"], "score": score})
                            taken += 1
                except Exception as exc:
                    print(f"    {source.__name__.strip('_')} search failed '{query}': {exc}")
        if len(got) >= want * 0.5:
            break
    return got


# ------------------------------------------------------------------ clips
def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True)
    info = json.loads(out.stdout or "{}")
    st = (info.get("streams") or [{}])[0]
    return st.get("width", 0), st.get("height", 0), float(info.get("format", {}).get("duration", 0) or 0)


def _download_file(url, path, limit):
    with requests.get(url, stream=True, headers=UA, timeout=120) as r:
        r.raise_for_status()
        n = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                n += len(chunk)
                if n > limit:
                    return False
    return True


def conform_clip(src, dst, seconds, W=1920, H=1080, fps=24, slow=1.3, min_width=640, grade_old=False):
    """Calm middle segment, slowed slightly, conformed to WxH@fps. Old/low-res film is framed
    with a soft dark surround instead of being blown up to fill the screen."""
    w, h, dur = _probe(src)
    if w < min_width or dur < 5:
        return None
    usable = dur - 4
    need = seconds / slow
    if usable < need:
        slow = max(1.0, seconds / max(usable, 1))
        need = seconds / slow
        if slow > 2.2:
            return None
    start = 2 + max(0.0, (usable - need) / 2)
    if w >= 1600:
        frame = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    else:                                              # archive film: inset at 78% height
        ih = int(H * 0.78) // 2 * 2
        frame = (f"scale=-2:{ih},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0b0d10")
    tone = ",eq=saturation=0.85:contrast=1.05" if grade_old else ""
    vf = f"setpts={slow:.3f}*PTS,framerate=fps={fps},{frame}{tone},format=yuv420p"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{need:.2f}",
                        "-i", str(src), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "18", "-r", str(fps), str(dst)])
    if r.returncode != 0:
        return None
    return _probe(dst)[2]


def fetch_clips(queries, want, out_dir, used, seconds=12, W=1920, H=1080, fps=24):
    """Public-domain archive film from Wikimedia Commons (one clip per query, for variety)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for query in queries:
        if len(got) >= want:
            break
        try:
            cands = list(_commons(query, "video", 15))
        except Exception as exc:
            print(f"    video search failed '{query}': {exc}")
            continue
        for cand in cands:
            if cand["id"] in used or _blocked(cand["text"]) or (cand.get("duration") or 0) < 8:
                continue
            raw = out_dir / f"{slugify(cand['id'])}.raw"
            dst = out_dir / f"{slugify(cand['id'])}.mp4"
            try:
                ok = _download_file(cand["url"], raw, MAX_VID_BYTES)
                dur = ok and conform_clip(raw, dst, seconds, W, H, fps, grade_old=True)
            except Exception:
                dur = None
            raw.unlink(missing_ok=True)
            if dur and dur >= seconds * 0.6:
                used.add(cand["id"])
                got.append({"path": str(dst), "id": cand["id"], "title": cand["title"],
                            "source": cand["source"], "duration": dur})
                break
    return got


def frame_stats(path):
    im = Image.open(path).convert("L")
    im.thumbnail((128, 128))
    return float(np.asarray(im).mean())
