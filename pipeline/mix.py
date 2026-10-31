"""Final audio: polished voice + ambient score that gently ducks under speech, loudness-normalized."""
from .common import run


def mix(narration, music, out, total, music_volume=0.16, lufs=-16, fade_out=6.0, duck=True,
        soft_spans=None, soft_db=-4.0):
    """soft_spans: [(start, end)] where the narrator speaks softer (companion moments), lowered by soft_db AFTER
    the compressor so it does not just bring them back up (same as Estrato Nocturno)."""
    voice = ("aresample=48000,highpass=f=75,"
             "equalizer=f=220:t=q:w=1.2:g=-1.5,equalizer=f=3200:t=q:w=1.5:g=1.5,"
             "acompressor=threshold=-22dB:ratio=2.5:attack=15:release=250:makeup=2")
    if soft_spans:
        cond = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in soft_spans)
        voice += f",volume='if({cond},{10 ** (soft_db / 20):.3f},1)':eval=frame"
    voice += ",aformat=channel_layouts=stereo"
    if duck:
        graph = (f"[0:a]{voice},asplit=2[v][sc];"
                 f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_volume},afade=t=in:d=5[m];"
                 f"[m][sc]sidechaincompress=threshold=0.04:ratio=3:attack=400:release=2500:makeup=1[md];"
                 f"[v][md]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                 f"afade=t=out:st={max(0, total - fade_out):.3f}:d={fade_out},"
                 f"loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000[a]")
    else:
        graph = (f"[0:a]{voice}[v];"
                 f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_volume},afade=t=in:d=1[m];"
                 f"[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                 f"afade=t=out:st={max(0, total - fade_out):.3f}:d={fade_out},"
                 f"loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000[a]")
    run(["ffmpeg", "-y", "-loglevel", "error",
         "-i", narration, "-stream_loop", "-1", "-i", music,
         "-filter_complex", graph, "-map", "[a]", "-t", f"{total:.3f}",
         "-c:a", "pcm_s16le", out])
    return out
