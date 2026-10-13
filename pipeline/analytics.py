"""Performance feedback: views per day and average view duration for every episode and Short.
Written to data/analytics.json; the topic generator reads it to lean toward what works."""
import datetime as dt

from .common import DATA, read_json, write_json
from .upload import _client, _client_creds, has_credentials


def main():
    if not has_credentials():
        print("analytics skipped (no YouTube credentials)")
        return
    done = read_json(DATA / "done.json", [])
    eps = {d["video_id"]: d for d in done if d.get("video_id")}
    shorts = {s for d in done for s in d.get("shorts", [])}
    ids = list(eps) + list(shorts)
    if not ids:
        print("analytics: nothing published yet")
        return
    yt = _client()
    stats = {}
    for k in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics,snippet", id=",".join(ids[k:k + 50])).execute().get("items", []):
            pub = dt.datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
            age = max(1.0, (dt.datetime.now(dt.timezone.utc) - pub).total_seconds() / 86400)
            views = int(v["statistics"].get("viewCount", 0))
            stats[v["id"]] = {"id": v["id"], "title": v["snippet"]["title"], "views": views,
                              "views_per_day": round(views / age, 1), "likes": int(v["statistics"].get("likeCount", 0)),
                              "days": round(age, 1)}
    try:                                                     # needs the yt-analytics.readonly scope
        from googleapiclient.discovery import build
        ya = build("youtubeAnalytics", "v2", credentials=_client_creds(), cache_discovery=False)
        for k in range(0, len(ids), 200):
            r = ya.reports().query(ids="channel==MINE", startDate="2026-01-01",
                                   endDate=dt.date.today().isoformat(),
                                   metrics="averageViewDuration,averageViewPercentage",
                                   dimensions="video", filters="video==" + ",".join(ids[k:k + 200])).execute()
            for vid, avd, avp in r.get("rows", []):
                if vid in stats:
                    stats[vid].update(avg_view_minutes=round(avd / 60, 1), avg_view_percent=round(avp, 1))
    except Exception as exc:
        print(f"  retention metrics unavailable: {exc}")
    report = {"updated": dt.date.today().isoformat(),
              "episodes": [stats[i] for i in eps if i in stats],
              "shorts": [stats[i] for i in shorts if i in stats]}
    write_json(DATA / "analytics.json", report)
    for e in sorted(report["episodes"], key=lambda s: -s["views_per_day"])[:5]:
        print(f"  {e['views_per_day']:7.1f}/day  {e.get('avg_view_minutes', '?')} min  {e['title'][:70]}")


if __name__ == "__main__":
    main()
