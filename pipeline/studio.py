"""Optional: the studio's own footage, read from a private Google Drive folder.

File names are the tags: "gold-coins-macro-slowmo.mp4", "candle-ledger-ink-pen.mov".
The pipeline matches each chapter's searches against those words and uses the best clips.
Studio clips may repeat across episodes (never twice in the same episode).
Needs the Drive read-only scope in the YouTube token (scripts/get_youtube_token.py asks for it).
"""
import re

from .assets import conform_clip
from .common import slugify
from .upload import _client_creds, has_credentials

_listing = None


def _service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_client_creds(), cache_discovery=False)


def _files(folder_id):
    global _listing
    if _listing is None:
        _listing = []
        svc, token = _service(), None
        while True:
            r = svc.files().list(q=f"'{folder_id}' in parents and mimeType contains 'video/' and trashed=false",
                                 fields="nextPageToken, files(id, name, size)", pageSize=500,
                                 pageToken=token).execute()
            _listing += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                break
    return _listing


def _words(text):
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2}


def fetch_studio_clips(cfg, queries, want, out_dir, taken, seconds=12, W=1920, H=1080, fps=24):
    folder = (cfg.get("studio_footage") or {}).get("drive_folder_id")
    if not folder or not has_credentials() or want <= 0:
        return []
    try:
        files = _files(folder)
    except Exception as exc:
        print(f"    studio footage unavailable: {exc}")
        return []
    want_words = set().union(*[_words(q) for q in queries]) if queries else set()
    scored = sorted(((len(_words(f["name"]) & want_words), f) for f in files if f["id"] not in taken),
                    key=lambda x: -x[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    from googleapiclient.http import MediaIoBaseDownload
    svc = _service()
    for score, f in scored:
        if len(got) >= want or score == 0:
            break
        raw, dst = out_dir / f"{slugify(f['id'])}.raw", out_dir / f"studio-{slugify(f['id'])}.mp4"
        try:
            with open(raw, "wb") as fh:
                dl = MediaIoBaseDownload(fh, svc.files().get_media(fileId=f["id"]), chunksize=64 << 20)
                done = False
                while not done:
                    _, done = dl.next_chunk()
            dur = conform_clip(raw, dst, seconds, W, H, fps, slow=1.0, min_width=1280)
        except Exception as exc:
            print(f"    studio clip {f['name']} failed: {exc}")
            dur = None
        raw.unlink(missing_ok=True)
        if dur:
            taken.add(f["id"])
            got.append({"path": str(dst), "id": f"studio:{f['id']}", "title": f["name"],
                        "source": "studio", "duration": dur})
    return got
