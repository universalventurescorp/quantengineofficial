"""The Quiet Ledger narrator on Kaggle's free GPU (pushed by pipeline/gpu.py as the private script
`quiet-ledger-voice`). Voices every sentence of the episode with Qwen3-TTS (Apache-2.0), cloning the channel's
reference clip, split over both T4 GPUs. Output: /kaggle/working/ai/narration/<index>.wav + manifest.json.
"""
import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import traceback

JOB_B64 = "__JOB_B64__"
OUT = pathlib.Path("/kaggle/working/ai")
WORK = pathlib.Path("/kaggle/tmp/tts")
T0 = time.time()

TTS_WORKER = r"""
import json, sys, time, pathlib
import numpy as np, soundfile as sf, torch
cfg = json.load(open(sys.argv[1]))
out = pathlib.Path(cfg["out"]); out.mkdir(parents=True, exist_ok=True)
prog = pathlib.Path(cfg["progress"])
from qwen_tts import Qwen3TTSModel
model = Qwen3TTSModel.from_pretrained(cfg["model"], device_map="cuda:0", dtype=torch.float16,
                                      attn_implementation="sdpa")
prompt = model.create_voice_clone_prompt(ref_audio=cfg["ref"], ref_text=cfg["ref_text"], x_vector_only_mode=False)
lang = cfg["language"]
todo = [it for it in cfg["items"] if not (out / f"{it[0]:05d}.wav").exists()]
todo.sort(key=lambda it: len(it[1]))          # similar lengths batch together
B = cfg.get("batch", 8)
done, retried, t0 = 0, 0, time.time()

def ok(w, sr, text):
    d = len(w) / sr
    exp = len(text.split()) / 2.6
    return bool(np.isfinite(w).all() and np.abs(w).max() > 0.01 and 0.35 * exp < d < 2.2 * exp + 1.5)

def gen(texts):
    wavs, sr = model.generate_voice_clone(text=texts, language=[lang] * len(texts), voice_clone_prompt=prompt,
                                          max_new_tokens=2048)
    return [np.asarray(w, np.float32).squeeze() for w in wavs], sr

i = 0
while i < len(todo):
    chunk = todo[i:i + B]
    try:
        wavs, sr = gen([t for _, t in chunk])
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        if B == 1:
            raise
        B = max(1, B // 2)
        continue
    for (idx, text), w in zip(chunk, wavs):
        tries = 0
        while not ok(w, sr, text) and tries < 3:
            tries += 1; retried += 1
            torch.manual_seed(1000 + idx * 7 + tries)
            w = gen([text])[0][0]
        sf.write(out / f"{idx:05d}.wav", w, sr)
        done += 1
    i += len(chunk)
    prog.write_text(json.dumps({"done": done, "total": len(todo), "retried": retried, "batch": B,
                                "minutes": round((time.time() - t0) / 60, 1)}))
"""


def log(msg):
    line = f"[{(time.time() - T0) / 60:6.1f} min] {msg}"
    print(line, flush=True)
    with open(OUT / "log.txt", "a") as f:
        f.write(line + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    job = json.loads(base64.b64decode(JOB_B64))
    nar = job["narration"]
    M = {"job_id": job["job_id"], "total": len(nar["items"]), "done": 0, "errors": []}
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], capture_output=True)
        venv = WORK / "venv"
        r = subprocess.run([sys.executable, "-m", "uv", "venv", "-q", "--python", "3.12", str(venv)],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("uv venv: " + r.stderr[-600:])
        py = str(venv / "bin" / "python")
        r = subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "--python", py, "qwen-tts",
                            "soundfile"], capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise RuntimeError("pip qwen-tts: " + r.stderr[-1200:])
        ref_mp3 = WORK / "ref.mp3"
        ref_mp3.write_bytes(base64.b64decode(nar["ref_b64"]))
        ref = WORK / "ref.wav"
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg = "ffmpeg"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(ref_mp3), "-ac", "1", "-ar", "24000",
                        str(ref)], check=True)
        (WORK / "tts_worker.py").write_text(TTS_WORKER)
        import torch
        n_gpu = torch.cuda.device_count()
        items = list(nar["items"])
        log(f"{n_gpu} GPU(s), {len(items)} sentences")
        shards = [items[g::max(1, n_gpu)] for g in range(max(1, n_gpu))]   # interleaved: equal lengths per GPU
        out = OUT / "narration"
        procs = []
        for g, shard in enumerate(shards):
            if not shard:
                continue
            cfgf = WORK / f"cfg_{g}.json"
            cfgf.write_text(json.dumps({"model": nar["model"], "ref": str(ref), "ref_text": nar["ref_text"],
                                        "language": nar["language"], "items": shard, "out": str(out),
                                        "progress": str(WORK / f"progress_{g}.json"), "batch": 8},
                                       ensure_ascii=False))
            env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(g), "PYTHONUNBUFFERED": "1"}
            fo = open(OUT / f"voice_gpu{g}.log", "w")
            procs.append((g, subprocess.Popen([py, str(WORK / "tts_worker.py"), str(cfgf)], stdout=fo,
                                              stderr=subprocess.STDOUT, env=env), fo))
        while any(p.poll() is None for _, p, _ in procs):
            time.sleep(30)
            M["done"] = len(list(out.glob("*.wav"))) if out.exists() else 0
            log(f"voiced {M['done']}/{M['total']}")
        for g, p, fo in procs:
            fo.close()
            if p.returncode:
                tail = (OUT / f"voice_gpu{g}.log").read_text(errors="ignore").splitlines()[-25:]
                M["errors"].append(f"GPU {g} exit {p.returncode}: " + "\n".join(tail)[-1500:])
        M["done"] = len(list(out.glob("*.wav"))) if out.exists() else 0
    except Exception:
        M["errors"].append(traceback.format_exc()[-2500:])
    M["minutes"] = round((time.time() - T0) / 60, 1)
    log(f"narration: {M['done']}/{M['total']} sentences in {M['minutes']} min")
    (OUT / "manifest.json").write_text(json.dumps(M, indent=1))


if __name__ == "__main__":
    main()
