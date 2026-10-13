"""Run ONCE on your own computer to authorize the pipeline on the channel.

    pip install google-auth-oauthlib
    python scripts/get_youtube_token.py client_secret.json
    python scripts/get_youtube_token.py client_secret.json --with-drive   # only if you use studio footage

Sign in with the Google account that owns the channel and pick THE CHANNEL (QuantEngine / The Quiet Ledger).
Then copy the three printed values into GitHub > Settings > Secrets and variables > Actions.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]   # performance report (retention)
if "--with-drive" in sys.argv:
    SCOPES.append("https://www.googleapis.com/auth/drive.readonly")  # optional studio footage folder

args = [a for a in sys.argv[1:] if not a.startswith("--")]
path = args[0] if args else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
info = json.load(open(path))
info = info.get("installed") or info.get("web")
print("\nYT_CLIENT_ID     =", info["client_id"])
print("YT_CLIENT_SECRET =", info["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
