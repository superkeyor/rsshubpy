"""
One way to load a page:

    from fetch import fetch
    page = fetch(url, via='requests')   # plain HTTP
    page = fetch(url, via='browser')    # a real Chrome window (browser.window): open, wait, read
    page.soup, page.html, page.url, page.title

`via` is required (no default), so every spider states how it fetches; main.py lists them on the index page.
For multi-step browser work (clicks, waits, screenshots, WebDriver) use browser.window() directly.
Only one spider per site runs at a time (feeds.site_lock), whichever `via` it uses.
"""
import logging
import re
import subprocess
import threading
from dataclasses import dataclass
from functools import cached_property
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from browser import window

log = logging.getLogger(__name__)

VIAS = ('requests', 'browser')
TIMEOUT = 900   # seconds; the original code had none, this only guards against a connection that hangs forever


def chromium_user_agent(version_output: str) -> str:
    """
    The user agent the installed Chromium sends (reduced UA format: only the major version, Linux x86_64 even
    on arm64), from `chromium --version` output such as "Chromium 156.0.8078.47 built on Debian ...".
    """
    major = re.search(r'(\d+)\.\d+\.\d+\.\d+', version_output).group(1)
    return f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36'


def _detect_user_agent() -> str:
    try:
        out = subprocess.run(['chromium', '--version'], capture_output=True, text=True, timeout=30).stdout
        return chromium_user_agent(out)
    except Exception as e:   # outside the image (e.g. unit tests on a laptop)
        log.warning('fetch: could not read the Chromium version (%r); using a generic Chrome user agent', e)
        return chromium_user_agent('Chromium 156.0.0.0')


USER_AGENT = _detect_user_agent()

_sessions: dict[str, requests.Session] = {}   # one per host, kept for the process (keep-alive, cookies)
_sessions_guard = threading.Lock()


def _session(url: str) -> requests.Session:
    host = urlparse(url).hostname or ''
    with _sessions_guard:
        session = _sessions.get(host)
        if session is None:
            session = _sessions[host] = requests.Session()
            session.headers['User-Agent'] = USER_AGENT
        return session


@dataclass
class Fetched:
    """A loaded page: html (text), url (final, after redirects), title; soup is parsed on first use."""
    html: str
    url: str
    title: str
    parser: str = 'lxml'

    @cached_property
    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html, self.parser)


def fetch(url: str, *, via: str, wait: float = 3, parser: str = 'lxml') -> Fetched:
    """
    Load url via 'requests' (plain HTTP: one session per host, the real Chromium user agent, raises on
    HTTP errors) or 'browser' (a new Chrome window: open, wait `wait` seconds, read; bot checks and warm-up
    included). Same result either way.
    """
    if via == 'requests':
        res = _session(url).get(url, timeout=TIMEOUT)
        res.raise_for_status()
        # decode like BeautifulSoup does on bytes (meta charset / detection), so text equals what soup parses
        soup = BeautifulSoup(res.content, parser)
        html = res.content.decode(soup.original_encoding or 'utf-8', errors='replace')
        page = Fetched(html, res.url, soup.title.get_text(strip=True) if soup.title else '', parser)
        page.soup = soup   # already parsed (cached_property)
        return page
    if via == 'browser':
        with window(url) as page:
            page.open(url)
            page.sleep(wait)
            return Fetched(page.html(), page.url, page.title, parser)
    raise ValueError(f"fetch: via must be one of {VIAS}, not {via!r}")
