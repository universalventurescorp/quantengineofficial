"""Narration + exact subtitle timings.

Since 31-oct-2026 the narrator is a British male voice (Qwen3-TTS, Apache-2.0) cloned sentence by sentence on
Kaggle's free GPU (pipeline/gpu.py, kaggle/voice.py). Kokoro (CPU) stays as the fallback.

Episode layout:
  [lead] cold open  [opening title card + music]  chapter 1 ... chapter N  [end card]
"""
import re

import numpy as np

SR = 24000
SENTENCE = re.compile(r"(?<=[.!?…])\s+")
LEAD = 1.2          # silence before the first word
TITLE_GAP = 8.0     # opening title card (no narration)
CHAPTER_LEAD = 1.4  # chapter card fades in before the voice starts
OUTRO = 12.0        # end card + music tail


class Voice:
    def __init__(self, voice_id, speed):
        from kokoro import KPipeline
        self.pipe = KPipeline(lang_code=voice_id[0])   # Kokoro voice prefix = language code
        self.voice, self.speed = voice_id, speed

    def say(self, text, speed=None):
        chunks = []
        for result in self.pipe(text, voice=self.voice, speed=speed or self.speed, split_pattern=None):
            audio = getattr(result, "audio", None)
            if audio is None:
                _, _, audio = result
            if audio is not None:
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        audio = np.concatenate(chunks) if chunks else np.zeros(int(SR * 0.1), np.float32)
        return _trim(audio)


class PrecomputedVoice:
    """Sentences already voiced on the GPU: say(text) returns that sentence's audio at SR."""

    def __init__(self, folder, items, fallback=None):
        self.folder, self.fallback = folder, fallback
        self.index = {text: idx for idx, text in items}
        self.missing = []

    def say(self, text, speed=None):
        import soundfile as sf
        idx = self.index.get(" ".join(text.split()))
        p = None if idx is None else self.folder / f"{idx:05d}.wav"
        if p is None or not p.exists():
            self.missing.append(text)
            if self.fallback is None:
                raise RuntimeError(f"no narration for: {text[:80]}")
            return self.fallback.say(text, speed)
        a, sr = sf.read(p, dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        if sr != SR:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(sr, SR)
            a = resample_poly(a, SR // g, sr // g).astype(np.float32)
        return _trim(a)


GPU_VOICE = None        # set by run.py once Kaggle has voiced the episode (PrecomputedVoice)


def make_voice(cfg, speed=None):
    v = cfg["voice"]
    return GPU_VOICE if GPU_VOICE is not None else Voice(v["id"], speed or v["speed"])


def narration_items(script):
    """Every sentence the episode and its Shorts will speak, each once, numbered (for the GPU narrator)."""
    blocks = [script.get("cold_open", "")] + [c["text"] for c in script["chapters"]]
    blocks += [s.get("narration", "") for s in script.get("shorts", [])]
    texts, seen = [], set()
    for b in blocks:
        for p in paragraphs(b or ""):
            for s in split_sentences(p):
                t = " ".join(s.split())
                if t not in seen:
                    seen.add(t)
                    texts.append(t)
    return list(enumerate(texts))


def _trim(a, thresh=0.004):
    """Remove leading/trailing near-silence so our own pauses are exact. Keeps 50 ms before the first sound and
    150 ms after the last (soft consonants, natural decay), with short fades so a join never clicks."""
    idx = np.where(np.abs(a) > thresh)[0]
    if len(idx) == 0:
        return a
    s, e = max(0, idx[0] - int(0.05 * SR)), min(len(a), idx[-1] + int(0.15 * SR))
    a = a[s:e].astype(np.float32).copy()
    fi, fo = min(len(a) // 4, int(0.01 * SR)), min(len(a) // 4, int(0.06 * SR))
    if fi:
        a[:fi] *= np.sin(np.linspace(0, np.pi / 2, fi)) ** 2
    if fo:
        a[-fo:] *= np.cos(np.linspace(0, np.pi / 2, fo)) ** 2
    return a


def split_sentences(paragraph):
    return [s.strip() for s in SENTENCE.split(" ".join(paragraph.split())) if s.strip()]


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk_words(sentence, max_chars):
    words, chunks, cur = sentence.split(), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def timed_chunks(start, end, sentence, max_chars):
    """Split a sentence into caption chunks, timed proportionally to their length."""
    chunks = chunk_words(sentence, max_chars)
    total = sum(len(c) + 1 for c in chunks)
    t, out = start, []
    for c in chunks:
        d = (end - start) * (len(c) + 1) / total
        out.append((t, t + d, c))
        t += d
    return out


class Track:
    def __init__(self):
        self.parts, self.n, self.cues = [], 0, []
        self.marks = {}      # normalized paragraph -> "companion" | "subscribe"
        self.events = []     # [{"kind", "start", "end"}] where those paragraphs were said
        self.soft_pause = 0.0

    @property
    def t(self):
        return self.n / SR

    def silence(self, seconds):
        a = np.zeros(int(SR * seconds), np.float32)
        self.parts.append(a)
        self.n += len(a)

    def speech(self, audio, sentence, max_chars=84):
        start = self.t
        self.parts.append(audio)
        self.n += len(audio)
        self.cues += timed_chunks(start, self.t, sentence, max_chars)

    def text(self, voice, text, pause_sentence, pause_paragraph, max_chars=84):
        paras = paragraphs(text)
        for pi, p in enumerate(paras):
            kind = self.marks.get(" ".join(p.split()))
            if kind == "companion" and self.soft_pause:
                self.silence(self.soft_pause)       # the narrator turns from the story to the listener
            p_start = self.t
            sents = split_sentences(p)
            for si, s in enumerate(sents):
                self.speech(voice.say(s), s, max_chars)
                last_s = si == len(sents) - 1
                if last_s and kind:
                    self.events.append({"kind": kind, "start": round(p_start, 3), "end": round(self.t, 3)})
                    if kind == "companion" and self.soft_pause:
                        self.silence(self.soft_pause)
                if not (last_s and pi == len(paras) - 1):
                    self.silence(pause_paragraph if last_s else pause_sentence)

    def audio(self, peak=0.89, quiet_breaths=False):
        a = np.concatenate(self.parts) if self.parts else np.zeros(1, np.float32)
        if quiet_breaths:
            a = quiet_pauses(a)
        return a / max(1e-6, np.abs(a).max()) * peak


def quiet_pauses(x, below=24, min_ms=120, atten_db=-24, hold_ms=160, pre_ms=70, close_ms=140, open_ms=40):
    """Breaths and noise INSIDE pauses turned down without chopping a word (same as Estrato Nocturno):
    the last syllable's decay is kept for hold_ms then faded over close_ms; the gain is back pre_ms before
    the next word."""
    hop = int(SR * 0.01)
    n = len(x) // hop
    if n < 10:
        return x
    e = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    q = e < np.percentile(e, 90) - below
    speech = ~q
    i = 0
    while i < n:
        if q[i]:
            j = i
            while j < n and q[j]:
                j += 1
            if (j - i) * 10 < min_ms:
                speech[i:j] = True
            i = j
        else:
            i += 1
    keep = speech.copy()
    hold, pre = hold_ms // 10, pre_ms // 10
    for k in np.where(speech)[0]:
        keep[k:k + hold + 1] = True
        keep[max(0, k - pre):k] = True
    target = np.where(keep, 0.0, float(atten_db))
    down, up = -atten_db / max(1, close_ms // 10), -atten_db / max(1, open_ms // 10)
    g, cur = np.zeros(n), 0.0
    for k in range(n):
        cur = max(target[k], cur - down) if target[k] < cur else min(target[k], cur + up)
        g[k] = cur
    centers = (np.arange(n) + 0.5) * hop
    gs = 10 ** (np.interp(np.arange(len(x)), centers, g) / 20)
    return (x * gs).astype(np.float32)


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n")


def synthesize(script, cfg, out_dir):
    import soundfile as sf

    v = cfg["voice"]
    voice = make_voice(cfg)
    tr = Track()
    timing = {"chapters": []}
    comp = cfg.get("companion") or {}
    tr.soft_pause = comp.get("pause", 0.8) if comp.get("enabled") else 0.0
    for ch in script["chapters"]:
        for p in ch.get("companion", []):
            tr.marks[" ".join(p.split())] = "companion"
    sub = (cfg["channel"].get("subscribe_line") or "").strip()
    if sub:
        tr.marks[" ".join(sub.split())] = "subscribe"

    tr.silence(LEAD)
    if script.get("cold_open"):
        s = tr.t
        tr.text(voice, script["cold_open"], v["pause_sentence"] * 0.8, v["pause_paragraph"] * 0.8)
        timing["cold_open"] = {"start": s, "end": tr.t}
        print(f"  voiced cold open ({tr.t:.0f} s)")
    s = tr.t + 0.6
    tr.silence(TITLE_GAP)
    timing["title_card"] = {"start": s, "end": tr.t}

    for ci, ch in enumerate(script["chapters"]):
        start = tr.t
        tr.silence(CHAPTER_LEAD)
        tr.text(voice, ch["text"], v["pause_sentence"], v["pause_paragraph"])
        if ci < len(script["chapters"]) - 1:
            tr.silence(v["pause_chapter"])
        timing["chapters"].append({"title": ch["title"], "start": start, "end": tr.t})
        print(f"  voiced chapter {ci + 1}/{len(script['chapters'])} -> {tr.t / 60:.1f} min")

    s = tr.t
    tr.silence(OUTRO)
    timing["outro"] = {"start": s, "end": tr.t}
    timing["duration"] = tr.t
    timing["events"] = tr.events
    timing["voice"] = "qwen" if GPU_VOICE is not None else f"kokoro {v['id']}"
    sf.write(out_dir / "narration.wav", tr.audio(quiet_breaths=GPU_VOICE is not None), SR)
    write_srt(tr.cues, out_dir / "captions.srt")
    return timing


def synthesize_short(text, cfg, out_wav, speed=1.0):
    """Shorts voice: normal pace, tight pauses. Returns (duration, caption cues)."""
    import soundfile as sf

    voice = make_voice(cfg, speed)
    tr = Track()
    tr.silence(0.25)
    tr.text(voice, text, 0.22, 0.35, max_chars=22)
    tr.silence(0.9)
    sf.write(out_wav, tr.audio(), SR)
    if GPU_VOICE is not None:
        # the GPU narrator has one natural pace: Shorts are sped up with atempo (pitch kept), cues rescaled
        tempo = cfg.get("shorts", {}).get("gpu_voice_tempo", 1.08) * speed
        if abs(tempo - 1) > 0.01:
            import pathlib
            import subprocess
            tmp = pathlib.Path(str(out_wav) + ".tmp.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out_wav), "-filter:a",
                            f"atempo={tempo:.3f}", str(tmp)], check=True)
            tmp.replace(out_wav)
            return tr.t / tempo, [(a / tempo, b / tempo, c) for a, b, c in tr.cues]
    return tr.t, tr.cues
