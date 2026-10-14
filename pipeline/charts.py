"""Real economic data, drawn slowly.

  fetch(key)            -> {"dates": [...], "values": [...], "meta": {...}}   (FRED / World Bank, free)
  facts_text(key, data) -> exact figures the script may cite (so the narration never invents numbers)
  render_chart_clip()   -> a calm animated chart (the line draws itself, a warm glow follows its tip)

FRED works without a key (public CSV endpoint). If FRED_API_KEY is set, the official API is used.
"""
import datetime as dt
import io
import math
import os
import subprocess

import numpy as np
import requests

from .catalog import COUNTRIES, FRED, RECESSIONS_FRED, WB_INDICATORS
from .common import ROOT

from . import http
_cache = {}

INK = "#0b0d10"
GOLD = "#d9b26f"
PAPER = "#e9e1cf"
MUTED = "#8a8273"


# ------------------------------------------------------------------ data
def _fred_raw(series_id):
    key = os.environ.get("FRED_API_KEY")
    if key:
        r = http.get("https://api.stlouisfed.org/fred/series/observations", timeout=90,
                     params={"series_id": series_id, "api_key": key, "file_type": "json"})
        rows = [(o["date"], o["value"]) for o in r.json()["observations"]]
    else:
        r = http.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id},
                     timeout=120)
        lines = r.text.strip().splitlines()[1:]
        rows = [tuple(l.split(",")[:2]) for l in lines]
    out = []
    for d, v in rows:
        try:
            out.append((dt.date.fromisoformat(d), float(v)))
        except ValueError:
            continue                                  # "." = missing
    return out


def _monthly(rows):
    """Average to one value per month (daily/weekly series), keeping monthly/quarterly/annual as is."""
    buckets = {}
    for d, v in rows:
        buckets.setdefault((d.year, d.month), []).append(v)
    return sorted((dt.date(y, m, 1), sum(vs) / len(vs)) for (y, m), vs in buckets.items())


def fetch(key):
    if key in _cache:
        return _cache[key]
    if key in FRED:
        sid, title, unit, transform, source, first = FRED[key]
        rows = _monthly(_fred_raw(sid))
        if transform == "yoy":
            by = {(d.year, d.month): v for d, v in rows}
            rows = [(d, (v / by[(d.year - 1, d.month)] - 1) * 100) for d, v in rows
                    if by.get((d.year - 1, d.month))]
        elif transform == "div1000":
            rows = [(d, v / 1000) for d, v in rows]
        rows = [(d, v) for d, v in rows if d.year >= first]
        meta = {"title": title, "unit": unit, "source": f"{source}, via FRED", "key": key}
    elif ":" in key:
        ind, iso = key.split(":", 1)
        wid, title, unit = WB_INDICATORS[ind]
        r = http.get(f"https://api.worldbank.org/v2/country/{iso}/indicator/{wid}",
                     params={"format": "json", "per_page": 200}, timeout=90)
        js = r.json()
        rows = sorted((dt.date(int(o["date"]), 1, 1), float(o["value"]))
                      for o in (js[1] if len(js) > 1 and js[1] else []) if o.get("value") is not None)
        meta = {"title": f"{COUNTRIES[iso]}: {title}", "unit": unit, "source": "World Bank", "key": key}
    else:
        raise KeyError(key)
    if len(rows) < 8:
        raise ValueError(f"not enough data for {key}")
    data = {"dates": [d for d, _ in rows], "values": [v for _, v in rows], "meta": meta}
    _cache[key] = data
    return data


def recessions():
    try:
        rows = _monthly(_fred_raw(RECESSIONS_FRED))
    except Exception:
        return []
    spans, start = [], None
    for d, v in rows:
        if v >= 0.5 and start is None:
            start = d
        elif v < 0.5 and start is not None:
            spans.append((start, d))
            start = None
    return spans


# ------------------------------------------------------------------ facts
def fmt(value, unit, spoken=False):
    """'4.2%' / '$412,300' / '$21.6 trillion'. spoken=True gives TTS-friendly words."""
    a = abs(value)
    sign = "minus " if (spoken and value < 0) else ("-" if value < 0 else "")
    if unit in ("pct", "pp"):
        word = " percentage points" if unit == "pp" else " percent"
        return f"{sign}{a:.1f}{word if spoken else ('pp' if unit == 'pp' else '%')}"
    if unit in ("usd_bn", "usd_mn"):
        a = a * (1e9 if unit == "usd_bn" else 1e6)
        unit = "usd"
    if unit == "usd":
        if a >= 1e12:
            s = f"{a / 1e12:.1f} trillion"
        elif a >= 1e9:
            s = f"{a / 1e9:.1f} billion"
        elif a >= 1e6:
            s = f"{a / 1e6:.1f} million"
        elif a >= 100:
            s = f"{a:,.0f}"
        else:
            s = f"{a:.2f}"
        return f"{sign}{s} dollars" if spoken else f"{sign}${s}"
    if unit == "thousands":
        a *= 1000
    if unit == "usd_per_eur":
        return f"{a:.2f} dollars per euro" if spoken else f"${a:.2f}"
    if a >= 1e9:
        return f"{sign}{a / 1e9:.1f} billion"
    if a >= 1e6:
        return f"{sign}{a / 1e6:.1f} million"
    return f"{sign}{a:,.0f}" if a >= 100 else f"{sign}{a:.1f}"


def _when(d, annual):
    return str(d.year) if annual else d.strftime("%B %Y")


def facts_text(key, data):
    d, v, m = data["dates"], data["values"], data["meta"]
    annual = all(x.month == 1 for x in d[-6:])
    hi, lo = int(np.argmax(v)), int(np.argmin(v))
    u = m["unit"]
    lines = [f"{m['title']} (source: {m['source']}):",
             f"- first value shown: {fmt(v[0], u, True)} in {_when(d[0], annual)}",
             f"- highest: {fmt(v[hi], u, True)} in {_when(d[hi], annual)}",
             f"- lowest: {fmt(v[lo], u, True)} in {_when(d[lo], annual)}",
             f"- latest: {fmt(v[-1], u, True)} in {_when(d[-1], annual)}"]
    for years in (10, 25, 50):
        target = d[-1].replace(year=d[-1].year - years)
        i = min(range(len(d)), key=lambda k: abs((d[k] - target).days))
        if abs((d[i] - target).days) < 200 and i != len(d) - 1:
            lines.append(f"- {years} years before the latest: {fmt(v[i], u, True)} in {_when(d[i], annual)}")
    return "\n".join(lines)


# ------------------------------------------------------------------ rendering
def _fonts():
    import logging
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    from matplotlib import font_manager
    for f in ("CormorantGaramond.ttf", "Jost.ttf"):
        p = ROOT / "branding" / "fonts" / f
        if p.exists():
            font_manager.fontManager.addfont(str(p))
    return "Cormorant Garamond", "Jost"


def _ease(x):
    x = min(1.0, max(0.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def render_chart_clip(key, out_path, seconds=14.0, W=1920, H=1080, fps=24, start_year=None,
                      caption=None, shade=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    data = fetch(key)
    dates, values, meta = data["dates"], np.array(data["values"]), data["meta"]
    if start_year:
        keep = [i for i, x in enumerate(dates) if x.year >= int(start_year)]
        if len(keep) >= 8:
            dates, values = [dates[i] for i in keep], values[keep]
    serif, sans = _fonts()
    x = mdates.date2num(dates)
    unit = meta["unit"]
    vertical = H > W
    s = min(W, H) / 1080

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=INK)
    if vertical:
        ax = fig.add_axes([0.12, 0.30, 0.80, 0.38])
    else:
        ax = fig.add_axes([0.08, 0.16, 0.84, 0.60])
    ax.set_facecolor(INK)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.spines["bottom"].set_alpha(0.5)
    ax.tick_params(colors=MUTED, labelsize=20 * s, length=0, pad=10 * s)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_fontfamily(sans)
    ax.grid(axis="y", color=PAPER, alpha=0.07, linewidth=1)
    pad = (values.max() - values.min()) * 0.12 or 1
    ax.set_xlim(x[0], x[-1] + (x[-1] - x[0]) * 0.04)
    ax.set_ylim(min(values.min() - pad, 0 if values.min() >= 0 and unit != "index" else values.min() - pad),
                values.max() + pad)
    ax.yaxis.set_major_locator(plt.MaxNLocator(4))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: fmt(val, unit)))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6 if not vertical else 4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    if shade and meta["key"] in FRED:
        for a, b in recessions():
            if b >= dates[0]:
                ax.axvspan(mdates.date2num(max(a, dates[0])), mdates.date2num(b), color=PAPER,
                           alpha=0.05, linewidth=0)
    if values.min() < 0 < values.max():
        ax.axhline(0, color=PAPER, alpha=0.18, linewidth=1)

    title = caption or meta["title"]
    tx, ty = (0.08, 0.90) if not vertical else (0.08, 0.80)
    fig.text(tx, ty, title, color=PAPER, fontsize=(52 if not vertical else 46) * s, fontfamily=serif,
             va="top", wrap=True)
    fig.text(tx, (0.06 if not vertical else 0.24), f"Source: {meta['source']}", color=MUTED,
             fontsize=17 * s, fontfamily=sans)

    glow = [ax.plot([], [], color=GOLD, linewidth=lw * s, alpha=al, solid_capstyle="round")[0]
            for lw, al in ((16, 0.05), (9, 0.10))]
    line, = ax.plot([], [], color=GOLD, linewidth=3.6 * s, solid_capstyle="round")
    dot, = ax.plot([], [], "o", color="#fff3d6", markersize=9 * s)
    halo, = ax.plot([], [], "o", color=GOLD, markersize=28 * s, alpha=0.22)
    from matplotlib import patheffects
    label = ax.text(0, 0, "", color=PAPER, fontsize=26 * s, fontfamily=sans, va="bottom", ha="right",
                    path_effects=[patheffects.withStroke(linewidth=10 * s, foreground=INK)])

    n_frames = int(round(seconds * fps))
    draw_frames = int(n_frames * 0.72)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
         "-pix_fmt", "yuv420p", str(out_path)], stdin=subprocess.PIPE)
    last = None
    try:
        for f in range(n_frames):
            p = _ease(f / max(1, draw_frames)) if f < draw_frames else 1.0
            k = max(2, int(round(p * (len(x) - 1))) + 1)
            if k != last:                                    # hold frames are re-sent, not re-drawn
                for g in glow + [line]:
                    g.set_data(x[:k], values[:k])
                dot.set_data([x[k - 1]], [values[k - 1]])
                halo.set_data([x[k - 1]], [values[k - 1]])
                label.set_position((x[k - 1] - (x[-1] - x[0]) * 0.012, values[k - 1] + pad * 0.3))
                label.set_text(fmt(values[k - 1], unit))
                fig.canvas.draw()
                buf = bytes(fig.canvas.buffer_rgba())
                last = k
            proc.stdin.write(buf)
    finally:
        proc.stdin.close()
        proc.wait()
        plt.close(fig)
    if proc.returncode != 0:
        raise RuntimeError("chart encode failed")
    return {"path": str(out_path), "duration": seconds, "id": f"chart:{key}",
            "title": meta["title"], "source": meta["source"]}
