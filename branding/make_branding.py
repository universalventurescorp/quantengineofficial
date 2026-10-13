"""Render The Quiet Ledger channel identity as upload-ready PNGs.

    python branding/make_branding.py          # writes branding/out/*.png

  profile_800.png       profile picture, 800x800 (shown as a circle)
  banner_2560x1440.png  banner; all text sits inside the 1546x423 safe area
  watermark_150.png     video watermark, transparent PNG

The mark is an old coin seen in candlelight: a beaded rim (like ancient silver), a serif Q,
and a single ledger rule beneath it.
Fonts: Cormorant Garamond and Jost (SIL Open Font License), in branding/fonts/.
"""
import math
import pathlib
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"

INK = (13, 12, 11)          # warm black, like a dark study at night
COIN = (30, 26, 21)         # unlit coin face
STAR = (236, 228, 212)      # parchment (main text)
SOFT = (196, 186, 166)      # secondary text
ACCENT = (205, 166, 96)     # old gold


def font(name, size, weight):
    f = ImageFont.truetype(str(HERE / "fonts" / name), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _layer(size):
    return Image.new("RGBA", size, (0, 0, 0, 0))


def tracked(draw, xy, text, f, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking
    return x - tracking


def tracked_width(text, f, tracking):
    return sum(f.getlength(c) for c in text) + tracking * (len(text) - 1)


def draw_mark(base, cx, cy, size, accent=ACCENT, bg_disc=None):
    """Beaded coin + serif Q + ledger rule, in an 800-unit box centred on (cx, cy)."""
    k = size / 800
    W, H = base.size
    lay = _layer((W, H))
    d = ImageDraw.Draw(lay)
    if bg_disc is not None:
        r = 392 * k
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=bg_disc)
    r = 300 * k
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COIN + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=accent + (255,), width=max(1, round(9 * k)))
    rb = 262 * k                                         # beaded inner rim
    for i in range(72):
        a = 2 * math.pi * i / 72
        bx, by = cx + rb * math.cos(a), cy + rb * math.sin(a)
        br = 5.2 * k
        d.ellipse((bx - br, by - br, bx + br, by + br), fill=accent + (210,))
    q = font("CormorantGaramond.ttf", max(8, round(330 * k)), 500)
    bb = q.getbbox("Q")
    d.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2 - 22 * k), "Q", font=q, fill=STAR + (255,))
    d.line([(cx - 92 * k, cy + 150 * k), (cx + 92 * k, cy + 150 * k)], fill=accent + (255,),
           width=max(1, round(6 * k)))
    # candlelight: soft warm sheen on the upper-left of the rim
    sheen = _layer((W, H))
    sd = ImageDraw.Draw(sheen)
    sd.arc((cx - r, cy - r, cx + r, cy + r), 190, 260, fill=(255, 230, 180, 150), width=max(1, round(14 * k)))
    sheen = sheen.filter(ImageFilter.GaussianBlur(max(1, 8 * k)))
    base.alpha_composite(lay)
    base.alpha_composite(sheen)


def candle_dust(img, n, seed, avoid=None, scale=1.0):
    rnd = random.Random(seed)
    lay = _layer(img.size)
    d = ImageDraw.Draw(lay)
    W, H = img.size
    for _ in range(n):
        x, y = rnd.random() * W, rnd.random() * H
        if avoid and avoid(x, y):
            continue
        r = (0.8 + rnd.random() * rnd.random() * 3.0) * scale
        a = 0.10 + rnd.random() * 0.45
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 214, 160, int(255 * a)))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(1.2 * scale)))


def warm_glow(img, cx, cy, radius, strength=60):
    W, H = img.size
    g = Image.new("L", (W, H), 0)
    ImageDraw.Draw(g).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=strength)
    g = g.filter(ImageFilter.GaussianBlur(radius * 0.45))
    lay = Image.new("RGBA", (W, H), (120, 78, 36, 255))
    lay.putalpha(g)
    img.alpha_composite(lay)


def profile(ss=4):
    S = 800 * ss
    img = Image.new("RGBA", (S, S), INK + (255,))
    warm_glow(img, S * 0.42, S * 0.40, S * 0.55, 70)
    candle_dust(img, 60, 7, avoid=lambda x, y: math.hypot(x - S / 2, y - S / 2) < 320 * ss, scale=ss * 1.4)
    draw_mark(img, S / 2, S / 2, S * 1.12)
    return img.resize((800, 800), Image.LANCZOS).convert("RGB")


def watermark(ss=8):
    S = 150 * ss
    img = _layer((S, S))
    draw_mark(img, S / 2, S / 2, S, bg_disc=INK + (200,))
    return img.resize((150, 150), Image.LANCZOS)


def banner(ss=2):
    W, H = 2560 * ss, 1440 * ss
    img = Image.new("RGBA", (W, H), INK + (255,))
    safe = (507 * ss, 508 * ss, 2053 * ss, 932 * ss)
    warm_glow(img, W * 0.5, H * 0.52, 900 * ss, 55)
    candle_dust(img, 420, 11, scale=ss,
                avoid=lambda x, y: safe[0] + 100 * ss < x < safe[2] - 40 * ss and safe[1] + 40 * ss < y < safe[3] - 40 * ss)
    title_f = font("CormorantGaramond.ttf", 92 * ss, 400)
    tag_f = font("Jost.ttf", 31 * ss, 300)
    sched_f = font("Jost.ttf", 27 * ss, 400)
    title, tag = "THE QUIET LEDGER", "The history of money, slowly told. For calm nights and sleep."
    sched = "NEW DOCUMENTARIES EVERY WEEK"
    t_track, s_track = 92 * ss * 0.10, 27 * ss * 0.32
    tw = max(tracked_width(title, title_f, t_track), tag_f.getlength(tag), tracked_width(sched, sched_f, s_track))
    mark, gap = 230 * ss, 40 * ss
    total = mark + gap + tw
    x0 = (safe[0] + safe[2]) / 2 - total / 2
    cy = (safe[1] + safe[3]) / 2
    draw_mark(img, x0 + mark / 2, cy, mark * 1.25)
    d = ImageDraw.Draw(img)
    tx = x0 + mark + gap
    cap_h = title_f.getbbox("Q")[3] - title_f.getbbox("Q")[1]
    block_h = cap_h + 34 * ss + 38 * ss + 30 * ss + 27 * ss
    top = cy - block_h / 2
    tracked(d, (tx, top - title_f.getbbox("Q")[1]), title, title_f, STAR, t_track)
    y = top + cap_h + 34 * ss
    d.text((tx, y - tag_f.getbbox("S")[1]), tag, font=tag_f, fill=SOFT)
    y += 38 * ss + 30 * ss
    tracked(d, (tx, y - sched_f.getbbox("N")[1]), sched, sched_f, ACCENT, s_track)
    assert x0 >= safe[0] and x0 + total <= safe[2], "lockup overflows the safe area"
    return img.resize((2560, 1440), Image.LANCZOS).convert("RGB")


def main():
    OUT.mkdir(exist_ok=True)
    profile().save(OUT / "profile_800.png", optimize=True)
    watermark().save(OUT / "watermark_150.png", optimize=True)
    banner().save(OUT / "banner_2560x1440.png", optimize=True)
    for p in sorted(OUT.glob("*.png")):
        print(f"{p.name}: {p.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
