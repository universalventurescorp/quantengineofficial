"""Render the same paragraph at several voice speeds, with the channel's music underneath,
so the speed can be chosen by ear.   python scripts/voice_samples.py 0.75 0.8 0.9"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import soundfile as sf  # noqa: E402

from pipeline.common import load_config, run  # noqa: E402
from pipeline.mix import mix  # noqa: E402
from pipeline.music import make_ambient  # noqa: E402
from pipeline.voice import SR, Track, Voice  # noqa: E402

TEXT = """In the spring of sixteen thirty seven, a single tulip bulb in Amsterdam could cost more than a house on a quiet canal. Merchants met in the back rooms of taverns, trading promises for flowers that were still asleep under the soil.

Nobody in the room had ever seen most of these flowers bloom. They were buying a feeling, the quiet certainty that tomorrow someone would pay a little more. And for a few strange months, someone always did.

Then, one cold morning in February, a buyer simply did not appear. The price of a bulb, which had seemed to rise forever, began to fall. Within days it was almost nothing at all."""

out = pathlib.Path(__file__).resolve().parents[1] / "samples"
out.mkdir(exist_ok=True)
cfg = load_config()
v = cfg["voice"]
music = out / "music.wav"
make_ambient(music, seed=7, seconds=120)
for sp in [float(x) for x in (sys.argv[1:] or ["0.75", "0.8", "0.9"])]:
    voice = Voice(v["id"], sp)
    tr = Track()
    tr.silence(1.0)
    tr.text(voice, TEXT, v["pause_sentence"], v["pause_paragraph"])
    tr.silence(2.0)
    wav = out / f"voice_{sp}.wav"
    sf.write(wav, tr.audio(), SR)
    mixed = out / f"mix_{sp}.wav"
    mix(wav, music, mixed, tr.t, music_volume=cfg["mix"]["music_volume"], lufs=cfg["mix"]["lufs"], fade_out=2.0)
    words = len(TEXT.split())
    print(f"speed {sp}: {tr.t:.1f} s, {words / (tr.t / 60):.0f} words per minute")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", mixed, "-c:a", "libmp3lame", "-b:a", "160k",
         out / f"quiet_ledger_voice_speed_{sp}.mp3"])
    wav.unlink()
    mixed.unlink()
music.unlink()
