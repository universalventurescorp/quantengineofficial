"""Polite HTTP for public archives and data APIs: identifies the bot (Wikimedia policy), spaces out
requests per host, retries with backoff on rate limits (429), bot blocks (403/410) and server errors."""
import time
import urllib.parse

import requests

UA = {"User-Agent": "TheQuietLedgerBot/1.0 (https://github.com/universalventurescorp/quantengineofficial; "
                    "universalventures.corp@gmail.com) python-requests"}
MIN_GAP = {"commons.wikimedia.org": 1.2, "upload.wikimedia.org": 0.6, "collectionapi.metmuseum.org": 0.4,
           "images.metmuseum.org": 0.3, "api.artic.edu": 0.4, "www.artic.edu": 0.3}
RETRY = {429, 403, 410, 500, 502, 503, 504}
_last = {}
_blocked_until = {}
session = requests.Session()
session.headers.update(UA)


def get(url, retries=4, timeout=40, **kw):
    host = urllib.parse.urlparse(url).netloc
    if _blocked_until.get(host, 0) > time.time():
        raise requests.HTTPError(f"{host} is rate-limiting us; skipping for now")
    last = None
    for attempt in range(retries):
        wait = MIN_GAP.get(host, 0.2) - (time.time() - _last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            r = session.get(url, timeout=timeout, **kw)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code not in RETRY:
            r.raise_for_status()
            return r
        last = requests.HTTPError(f"{r.status_code} for {url[:120]}")
        retry_after = r.headers.get("Retry-After", "")
        pause = int(retry_after) if retry_after.isdigit() else 20 * (attempt + 1)
        time.sleep(min(pause, 120))
    _blocked_until[host] = time.time() + 300           # give that archive a 5-minute rest
    raise last
