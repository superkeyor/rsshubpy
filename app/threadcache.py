"""
Incremental forum-thread scraping, shared by the forum spiders (v2ex, newmitbbs, acres).

    soups = collect_pages(site, thread_url, signature, next_url, via='requests', pages='all', pause=(5, 10))
    ...
    forget_except(site, current_thread_urls)   # once per run: prune + log a summary

- signature: something from the listing that changes when the thread gets a reply (reply count, last post
  id, ...); None if the listing has nothing usable.
- next_url(soup, page_url): the next page's URL, or None on the last page (the spider's own pagination logic).
- pages: 0 (none) | N (the first N pages) | 'all'.

The thread's pages are saved (HTML) in cache/threads/<site>/. On the next run:
  1. same signature, last full download < FULL_REFRESH_HOURS ago: the saved pages, nothing downloaded;
  2. changed (or no signature), same age limit: full saved pages are kept, downloading resumes at the saved
     last page (new replies land at the end); with the `pages` cap already filled by full pages, nothing
     is downloaded (those pages do not change);
  3. nothing saved, or older: full download (also picks up edits, deletions, changed like counts).
The spider parses the returned soups exactly as before (fresh soups from the saved HTML).
"""
import hashlib
import json
import logging
import random
import time
from pathlib import Path

from bs4 import BeautifulSoup

from fetch import fetch

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / 'cache' / 'threads'
FULL_REFRESH_HOURS = 24

_stats: dict[str, dict[str, int]] = {}   # per site, since the last forget_except (one spider per site at a time)


def _path(site: str, url: str) -> Path:
    return CACHE_DIR / site / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.json"


def _load(site: str, url: str) -> dict | None:
    try:
        return json.loads(_path(site, url).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning('thread cache: unreadable entry for %s (%s), downloading again', url, e)
        return None


def _save(site: str, url: str, entry: dict) -> None:
    path = _path(site, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def collect_pages(site, url, signature, next_url, *, via, pages='all', pause=(5, 10), topic_pause=0):
    """Return the thread's page soups (see the module docstring); downloads only what may have changed."""
    if pages == 0:
        return []
    cap = None if pages == 'all' else int(pages)
    stats = _stats.setdefault(site, {'unchanged': 0, 'resumed': 0, 'full': 0, 'pages': 0})
    entry = _load(site, url)
    fresh = entry is not None and time.time() - entry.get('full_at', 0) < FULL_REFRESH_HOURS * 3600
    saved = entry['pages'][:cap] if fresh else []
    cap_full = bool(cap and len(saved) >= cap and saved[-1]['has_next'])

    if fresh and ((signature is not None and signature == entry.get('signature')) or cap_full):
        stats['unchanged'] += 1
        kept, start = saved, None
    elif fresh and saved:
        stats['resumed'] += 1
        kept, start = saved[:-1], saved[-1]['url']   # the last saved page may have grown
    else:
        stats['full'] += 1
        kept, start = [], url

    collected = list(kept)
    page_url, downloaded = start, 0
    try:
        while page_url and (cap is None or len(collected) < cap):
            if downloaded:
                time.sleep(random.uniform(*pause))   # between pages of the same thread
            page = fetch(page_url, via=via)
            downloaded += 1
            nxt = next_url(page.soup, page_url)
            collected.append({'url': page_url, 'html': page.html, 'has_next': nxt is not None})
            page_url = nxt
    except Exception as e:
        # like the original loops: stop at a failed page and use what we have; keep the old cache entry
        log.warning('thread %s: page %s failed (%r); using %d page(s)', url, page_url, e, len(collected))
        stats['pages'] += downloaded
        return [BeautifulSoup(p['html'], 'lxml') for p in collected]

    stats['pages'] += downloaded
    if downloaded:
        if topic_pause:
            time.sleep(topic_pause)   # between threads
        _save(site, url, {
            'signature': signature,
            'full_at': time.time() if start == url else entry['full_at'],
            'pages': collected,
        })
    elif entry is not None and entry.get('signature') != signature:
        entry['signature'] = signature   # e.g. cap already full: remember the new signature
        _save(site, url, entry)
    return [BeautifulSoup(p['html'], 'lxml') for p in collected]


SUMMARY_FILE = 'summary.json'   # in CACHE_DIR: each site's last run, for the index page


def summaries() -> dict[str, dict]:
    """Each forum site's last run: threads, unchanged, resumed, full, pages (downloaded), forgotten, at."""
    try:
        return json.loads((CACHE_DIR / SUMMARY_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _save_summary(site: str, summary: dict) -> None:
    data = summaries()
    data[site] = summary
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_DIR / (SUMMARY_FILE + '.tmp')
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding='utf-8')
    tmp.replace(CACHE_DIR / SUMMARY_FILE)


def forget_except(site: str, urls) -> None:
    """Delete saved threads of site that are not in urls (gone from the listing); log this run's summary."""
    keep = {_path(site, u).name for u in urls}
    folder = CACHE_DIR / site
    removed = 0
    if folder.is_dir():
        for path in folder.glob('*.json'):
            if path.name not in keep:
                path.unlink(missing_ok=True)
                removed += 1
    s = _stats.pop(site, {'unchanged': 0, 'resumed': 0, 'full': 0, 'pages': 0})
    _save_summary(site, {**s, 'threads': s['unchanged'] + s['resumed'] + s['full'], 'forgotten': removed,
                         'at': time.time()})
    log.info('%s: %d threads, %d unchanged, %d resumed, %d full; %d page(s) downloaded; %d forgotten',
             site, s['unchanged'] + s['resumed'] + s['full'], s['unchanged'], s['resumed'], s['full'],
             s['pages'], removed)
