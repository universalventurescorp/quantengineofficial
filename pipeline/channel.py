"""One-time channel housekeeping, run automatically before each production (idempotent, a few API units per run):

  1. branding: banner, description, keywords, language (and the name, if the API allows it)
  2. legacy:   old QuantEngine videos published before `legacy.make_private_before` -> private
               (reversible in YouTube Studio; nothing is deleted)
"""
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .common import DATA, ROOT, load_config, read_json, write_json
from .upload import _client, has_credentials

STATE = DATA / "channel_state.json"
DESCRIPTION = """The Quiet Ledger tells the history of money, slowly. Calm, cinematic documentaries about coins and empires, bankers and bubbles, gold, inflation and the ideas that built the modern economy, narrated gently over museum treasures, archive imagery and real economic data.

Put one on to learn something real, to unwind, or to fall asleep.

New documentaries every week.

Imagery from public-domain and CC0 museum and archive collections. Data from FRED and the World Bank. Educational content, not financial advice."""
KEYWORDS = ('"history of money" "sleep documentary" "economic history" "calm documentary" "history for sleep" '
            '"relaxing history" "financial history" "gold standard" "inflation explained" "fall asleep"')


def setup_branding(yt, cfg, state):
    if state.get("branding"):
        return
    me = yt.channels().list(part="brandingSettings", mine=True).execute()["items"][0]
    bs = me.get("brandingSettings", {})
    banner = ROOT / "branding" / "out" / "banner_2560x1440.png"
    try:
        url = yt.channelBanners().insert(media_body=MediaFileUpload(str(banner), mimetype="image/png")).execute()["url"]
        bs.setdefault("image", {})["bannerExternalUrl"] = url
    except HttpError as exc:
        print(f"  banner not set: {exc}")
    ch = bs.setdefault("channel", {})
    ch.update(description=DESCRIPTION, keywords=KEYWORDS, defaultLanguage="en")
    body = {"id": me["id"], "brandingSettings": bs}
    try:
        ch["title"] = cfg["channel"]["name"]
        yt.channels().update(part="brandingSettings", body=body).execute()
    except HttpError:
        ch.pop("title", None)                     # the name can only be changed in YouTube Studio
        yt.channels().update(part="brandingSettings", body=body).execute()
    state["branding"] = True
    print("  channel banner, description and keywords set")


def make_legacy_private(yt, cfg, state):
    cutoff = (cfg.get("legacy") or {}).get("make_private_before")
    if not cutoff:
        return
    ours = {d.get("video_id") for d in read_json(DATA / "done.json", [])} | \
           {s for d in read_json(DATA / "done.json", []) for s in d.get("shorts", [])}
    uploads = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0][
        "contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50,
                                    pageToken=token).execute()
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        token = r.get("nextPageToken")
        if not token:
            break
    changed = 0
    for k in range(0, len(ids), 50):
        for v in yt.videos().list(part="snippet,status", id=",".join(ids[k:k + 50])).execute().get("items", []):
            st = v["status"]
            if v["id"] in ours or st.get("privacyStatus") != "public":
                continue
            if v["snippet"]["publishedAt"][:10] >= cutoff:
                continue
            new = {k2: st[k2] for k2 in ("embeddable", "license", "publicStatsViewable",
                                         "selfDeclaredMadeForKids") if k2 in st}
            new["privacyStatus"] = "private"
            yt.videos().update(part="status", body={"id": v["id"], "status": new}).execute()
            changed += 1
    if changed:
        print(f"  {changed} old videos set to private")


def main():
    if not has_credentials():
        print("channel housekeeping skipped (no YouTube credentials)")
        return
    cfg, state = load_config(), read_json(STATE, {})
    yt = _client()
    for task in (setup_branding, make_legacy_private):
        try:
            task(yt, cfg, state)
        except Exception as exc:                      # never block production on housekeeping
            print(f"  {task.__name__} failed: {exc}")
    write_json(STATE, state)


if __name__ == "__main__":
    main()
