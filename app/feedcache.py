"""
Last-copy cache for rendered feeds, refreshed by cron.

- A reader's request is answered from the saved copy of that exact URL (path + query) when there is one.
  The spider runs live only for the first request of a new URL, or when the same URL is requested again
  within RECHECK_SECONDS (open it twice to force the latest version).
- Every URL that was served once is remembered (never dropped automatically). Cron (crontab: minutes
  15 and 45) POSTs /refresh, which re-runs all remembered URLs in the background, REFRESH_WORKERS at a time,
  and replaces each copy on success. A failed rebuild keeps the previous copy (the error is logged and shown
  on the index page).
- A spider may return ctx['fingerprint'] (e.g. fidelity/market: the on-screen text of its screenshots). If a
  rebuild's fingerprint equals the saved one, the saved copy is kept as is: the content is semantically the
  same, and new screenshot bytes alone must not look like an update to the reader.

Files: cache/feeds/index.json (the remembered URLs) + one .xml per URL. cache/ is bind-mounted in
production, so copies survive container restarts.
"""
import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / 'cache' / 'feeds'
INDEX_FILE = CACHE_DIR / 'index.json'
RECHECK_SECONDS = 30       # a second reader request within this many seconds rebuilds the feed live
REFRESH_WORKERS = 4        # feeds refreshed at once (browser feeds still queue per site / MAX_WINDOWS)
REFRESH_HEADER = 'X-Feed-Refresh'   # request header that makes a feed view rebuild instead of serving the copy

_lock = threading.Lock()        # guards _index and its file
_refreshing = threading.Event()
_index: dict[str, dict] = {}    # uri -> {"file", "updated", "requested", "error"}


def _file_for(uri: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9]+', '_', uri).strip('_')[:60] or 'root'
    return f"{slug}-{hashlib.sha1(uri.encode()).hexdigest()[:10]}.xml"


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def _save_index() -> None:
    """Call with _lock held."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _write(INDEX_FILE, json.dumps(_index, indent=1, sort_keys=True))


def _load_index() -> None:
    try:
        data = json.loads(INDEX_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            _index.update(data)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        log.warning('feed cache: could not read %s (starting empty): %s', INDEX_FILE, e)


def get(uri: str) -> str | None:
    """
    The saved copy of uri for a reader, or None when the feed must be built live: no copy yet, or the
    previous reader request was less than RECHECK_SECONDS ago. Marks uri as requested.
    """
    with _lock:
        entry = _index.get(uri)
        if not entry:
            return None
        now = time.time()
        recheck = now - entry.get('requested', 0) < RECHECK_SECONDS
        entry['requested'] = now
        _save_index()
        if recheck:
            log.info('feed cache: %s requested twice within %ds, rebuilding', uri, RECHECK_SECONDS)
            return None
        try:
            return (CACHE_DIR / entry['file']).read_text(encoding='utf-8')
        except OSError:
            return None


def put(uri: str, xml: str, fingerprint: str | None = None, seconds: float | None = None) -> str:
    """
    Save a freshly rendered copy of uri and return the copy to serve. With a fingerprint equal to the saved
    one, the saved copy is kept and returned instead. (The request time is only set by get / first request.)
    seconds: how long the build took; it and the entry count are shown on the index page.
    """
    with _lock:
        entry = _index.setdefault(uri, {'file': _file_for(uri), 'requested': time.time()})
        path = CACHE_DIR / entry['file']
        entry.update(checked=time.time(), error=None, build_s=seconds, entries=xml.count('<entry>'))
        if fingerprint is not None and entry.get('fingerprint') == fingerprint and path.exists():
            _save_index()
            log.info('feed cache: %s unchanged (same fingerprint), keeping the saved copy', uri)
            return path.read_text(encoding='utf-8')
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _write(path, xml)
        entry.update(updated=time.time(), fingerprint=fingerprint)
        _save_index()
        return xml


def note_error(uri: str, error: str) -> None:
    """A refresh failed: keep the old copy, remember the error."""
    with _lock:
        if uri in _index:
            _index[uri]['error'] = error[:300]
            _save_index()


def entries() -> list[tuple[str, dict]]:
    with _lock:
        return sorted((uri, dict(entry)) for uri, entry in _index.items())


def refresh_all(fetch) -> bool:
    """
    Start refreshing every remembered URL in a background thread; fetch(uri) rebuilds one (returns True on
    success). Returns False if a refresh is still running.
    """
    if _refreshing.is_set():
        return False
    _refreshing.set()

    def run():
        try:
            uris = [uri for uri, _ in entries()]
            start = time.monotonic()
            log.info('refresh: %d feed(s)', len(uris))
            with ThreadPoolExecutor(REFRESH_WORKERS) as pool:
                ok = sum(pool.map(fetch, uris))
            log.info('refresh: %d/%d ok in %.0fs', ok, len(uris), time.monotonic() - start)
        except Exception:
            log.exception('refresh failed')
        finally:
            _refreshing.clear()

    threading.Thread(target=run, name='refresh', daemon=True).start()
    return True


os.makedirs(CACHE_DIR, exist_ok=True)
_load_index()
