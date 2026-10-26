"""
One container-lifetime Chromium, shared by all Flask threads.

Launch: SeleniumBase UC mode (undetected flags) + activate_cdp_mode, headed on the base image's single
Xvfb (DISPLAY=:99). After launch every job uses the async cdp_driver objects that CDP mode leaves behind
(sb.cdp loop + sb.driver.cdp_base); the sync sb.* / sb.cdp.* API is not used, because its "current tab"
is process-wide and cannot be shared by concurrent jobs.

A daemon thread owns Chrome and runs its asyncio loop forever; callers submit coroutines with
run_coroutine_threadsafe. All locking is asyncio-level inside that loop:
  - one window per site at a time (per-site asyncio.Lock, key = host without "www."),
  - at most MAX_WINDOWS windows overall (asyncio.Semaphore), the rest wait FIFO,
  - each job gets its own new window (a tab hidden behind another renders nothing), closed afterwards.
Warm-up (visit the site root, get through Cloudflare/DataDome, scroll a little) runs inside the site's own
window when the per-host memory says so. If Chrome dies, it is relaunched and the next call works.

Public API: window (yields a Page), BrowserError. Simple page loads: fetch.fetch(url, via='browser').
Design notes and gotchas: AGENTS.md.
"""
import asyncio
import atexit
import ipaddress
import json
import logging
import os
import random
import re
import shutil
import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import mycdp
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Config (env-overridable; defaults in the Dockerfile)
# ---------------------------------------------------------------------------
CHROME_USER_DATA_DIR = os.getenv('CHROME_USER_DATA_DIR') or str(HERE / 'chromiumprofile')
CHROMIUM = '/usr/bin/chromium'
MAX_WINDOWS = int(os.getenv('MAX_WINDOWS', '3'))
# Trim the profile's cache folders at start when the profile is bigger than this many MB (0 = never)
PROFILE_MAX_MB = float(os.getenv('PROFILE_MAX_MB') or 0)
# Window size = the Xvfb screen from the base image (SCREEN_GEOMETRY=WxHxDepth)
WINDOW_W, WINDOW_H = (int(v) for v in os.getenv('SCREEN_GEOMETRY', '1920x1080x24').split('x')[:2])
NAV_TIMEOUT = 60           # seconds for one page load (tab.get has no timeout of its own)
LAUNCH_TIMEOUT = 120       # seconds a caller waits for Chrome to (re)start
WARMUP_TIMEOUT = 30        # warm-up navigation + bot-check wait (seconds)
WARMUP_COOLDOWN = 300      # skip a needed warm-up if the host was warmed this many seconds ago
WARMUP_ALWAYS_AFTER = 2    # this many failed visits ...
WARMUP_ALWAYS_DAYS = 90    # ... within this many days = warm up before every visit
# Per-host memory, kept in the (persistent, bind-mounted) profile folder
HOSTS_FILE = os.path.join(CHROME_USER_DATA_DIR, 'rsshub-hosts.json')
USERSCRIPT_DIR = HERE / 'userscripts'


class BrowserError(RuntimeError):
    """Chrome is unavailable, restarting, or a browser job timed out."""


# ---------------------------------------------------------------------------
# Profile trim (ported from sbfetcher/server.py); runs once, before Chrome starts
# ---------------------------------------------------------------------------

# Re-creatable cache folders inside the profile (relative paths). Deliberately not listed: Cookies,
# Local Storage, IndexedDB, Service Worker/Database, Preferences, Extensions, rsshub-hosts.json.
_PROFILE_CACHE_DIRS = (
    "Default/Cache", "Default/Code Cache", "Default/GPUCache", "Default/DawnWebGPUCache",
    "Default/DawnGraphiteCache", "Default/Media Cache", "Default/Service Worker/CacheStorage",
    "Default/Service Worker/ScriptCache", "GPUCache", "ShaderCache", "GrShaderCache", "component_crx_cache",
)


def _dir_mb(path: str) -> float:
    """Disk usage of a directory tree in MB (counts allocated blocks, like du)."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_blocks * 512
            except OSError:
                pass
    return total / 1048576


def _trim_profile() -> None:
    """
    If the profile exceeds PROFILE_MAX_MB, delete its cache folders (Chrome re-creates them).
    Must run while Chrome is not running. Never raises.
    """
    if PROFILE_MAX_MB <= 0 or not os.path.isdir(CHROME_USER_DATA_DIR):
        return
    try:
        before = _dir_mb(CHROME_USER_DATA_DIR)
        if before <= PROFILE_MAX_MB:
            log.info("profile: %.0f MB (limit %.0f MB), no trim needed", before, PROFILE_MAX_MB)
            return
        for rel in _PROFILE_CACHE_DIRS:
            path = os.path.join(CHROME_USER_DATA_DIR, rel)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
        after = _dir_mb(CHROME_USER_DATA_DIR)
        log.info("profile: trimmed caches, %.0f MB -> %.0f MB (limit %.0f MB)", before, after, PROFILE_MAX_MB)
        if after > PROFILE_MAX_MB:
            log.warning("profile: still above the limit; the rest is site data (cookies, storage), which is never deleted")
    except Exception:
        log.exception("profile: trim failed (non-fatal)")


# ---------------------------------------------------------------------------
# Userscripts: userscripts/*.user.js injected into matching windows before navigation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Userscript:
    name: str
    patterns: tuple[re.Pattern, ...]
    source: str

    def matches(self, url: str) -> bool:
        return any(p.fullmatch(url) for p in self.patterns)


def _glob_to_regex(pattern: str) -> re.Pattern:
    """@match / @include glob -> regex. "*." right after the scheme also matches the bare domain."""
    regex = re.escape(pattern).replace(r'://\*\.', '://(?:[^/]*\\.)?').replace(r'\*', '.*')
    return re.compile(regex)


def parse_userscript(name: str, text: str) -> Userscript | None:
    """
    Return the script, or None (with a warning) if it needs a userscript manager: any @grant other than
    "none" (GM_* APIs, unsafeWindow, ...) or @require/@resource. Raw injection would break those part-way.
    """
    header = re.search(r'//\s*==UserScript==(.*?)//\s*==/UserScript==', text, re.S)
    meta = re.findall(r'^\s*//\s*@(\S+)\s*(.*?)\s*$', header.group(1), re.M) if header else []
    grants = [v for k, v in meta if k == 'grant' and v != 'none']
    extras = [k for k, _ in meta if k in ('require', 'resource')]
    if grants or extras:
        log.warning("userscript %s skipped: needs %s (install a userscript manager via noVNC instead)",
                    name, ', '.join([f'@grant {g}' for g in grants] + [f'@{k}' for k in extras]))
        return None
    patterns = tuple(_glob_to_regex(v) for k, v in meta if k in ('match', 'include'))
    if not patterns:
        log.warning("userscript %s skipped: no @match/@include", name)
        return None
    run_at = next((v for k, v in meta if k == 'run-at'), 'document-idle')
    if run_at != 'document-start':
        text = f"document.addEventListener('DOMContentLoaded', () => {{\n{text}\n}});"
    return Userscript(name, patterns, text)


def _load_userscripts() -> list[Userscript]:
    scripts = [parse_userscript(p.name, p.read_text(encoding='utf-8')) for p in sorted(USERSCRIPT_DIR.glob('*.user.js'))]
    return [s for s in scripts if s]


USERSCRIPTS = _load_userscripts()


# ---------------------------------------------------------------------------
# Bot checks and warm-up (ported from sbfetcher/server.py)
# ---------------------------------------------------------------------------

def _classify_page(title: str, html: str) -> str:
    """Return "blocked", "challenge" or "ok" for a loaded page (Cloudflare or DataDome)."""
    if (
        "Sorry, you have been blocked" in html
        or ("cf-error-details" in html and "_cf_chl_opt" not in html)
        or "'t':'bv'" in html  # DataDome hard block
    ):
        return "blocked"
    if (
        title.startswith("Just a moment")
        or "_cf_chl_opt" in html
        or 'id="challenge-' in html
        or "captcha-delivery.com" in html  # DataDome device check / captcha
    ):
        return "challenge"
    return "ok"


async def _solve_challenge(tab) -> bool:
    """Click a CAPTCHA with SeleniumBase's native async solver (CDP mouse events)."""
    try:
        return bool(await tab.solve_captcha())
    except Exception as exc:
        log.debug("solve_captcha failed: %s", exc)
        return False


async def _wait_for_cloudflare(tab, timeout_s: float) -> str:
    """
    Poll the current page until Cloudflare/DataDome lets it through.
    Waits passively for the first few seconds (managed challenges and device
    checks often clear on their own), then clicks the CAPTCHA every few seconds.
    Returns the final page state from _classify_page().
    """
    start = time.monotonic()
    last_click: float | None = None
    seen_challenge = False
    ok_streak = 0
    while True:
        elapsed = time.monotonic() - start
        try:
            title = await tab.get_title() or ""
            html = await tab.get_page_source() or ""
            state = _classify_page(title, html)
        except Exception as exc:
            # Page is mid-navigation (e.g. the challenge just redirected)
            log.debug("_wait_for_cloudflare: page not readable yet: %s", exc)
            state = "challenge"
        if state == "challenge" and not seen_challenge:
            seen_challenge = True
            log.info("challenge detected on %s — waiting", await tab.get_current_url())
        ok_streak = ok_streak + 1 if state == "ok" else 0
        # After a challenge, the reload can briefly show an empty document: confirm "ok" twice
        if state == "ok" and seen_challenge and ok_streak < 2 and elapsed < timeout_s:
            await tab.sleep(1)
            continue
        if state != "challenge" or elapsed >= timeout_s:
            if seen_challenge:
                log.info("challenge ended as %r after %.1fs", state, elapsed)
            return state
        if elapsed >= 6 and (last_click is None or time.monotonic() - last_click >= 8):
            last_click = time.monotonic()
            await _solve_challenge(tab)
        await tab.sleep(1)


async def _browse_like_a_human(tab) -> None:
    """Dwell and scroll a little, with trusted (gesture) scroll events."""
    async def _scroll() -> None:
        await tab.bring_to_front()
        await tab.sleep(random.uniform(0.8, 1.8))
        for _ in range(random.randint(2, 3)):
            await tab.scroll_down(random.randint(15, 40))
            await tab.sleep(random.uniform(0.6, 1.6))
        await tab.scroll_up(random.randint(10, 25))
        await tab.sleep(random.uniform(0.4, 1.0))

    try:
        await asyncio.wait_for(_scroll(), timeout=15)
    except Exception as exc:
        log.warning("warm-up: scrolling failed (non-fatal): %r", exc)


async def _warm_url(tab, url: str) -> str:
    """
    Visit url, get through any bot check, then scroll around a little.
    Takes about WARMUP_TIMEOUT seconds at most plus a few seconds of scrolling.
    Returns the final _classify_page() state.
    """
    start = time.monotonic()
    await asyncio.wait_for(tab.get(url), timeout=WARMUP_TIMEOUT)
    remaining = max(WARMUP_TIMEOUT - (time.monotonic() - start), 5)
    state = await _wait_for_cloudflare(tab, remaining)
    if state == "ok":
        log.info("warm-up: %s ok (%.1fs)", await tab.get_current_url(), time.monotonic() - start)
        await _browse_like_a_human(tab)
    else:
        log.warning("warm-up: %s still %s after %.0fs", url, state, time.monotonic() - start)
    return state


def _warm_target(url: str) -> tuple[str, str] | None:
    """
    Return (host key, root URL) for a public http(s) URL, or None for URLs that are
    never warmed: other schemes, localhost, LAN/private IPs, dotless and *.local hosts.
    The key drops a leading "www." so www.example.com and example.com share a state.
    """
    try:
        parts = urlparse(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host or host == "localhost":
        return None
    try:
        if not ipaddress.ip_address(host).is_global:
            return None
    except ValueError:  # not an IP address: a hostname
        if "." not in host or host.endswith((".local", ".lan", ".internal", ".localdomain", ".home.arpa")):
            return None
    root = f"{parts.scheme}://{host}{f':{port}' if port else ''}/"
    return host.removeprefix("www."), root


def _site_key(url: str) -> str:
    """Lock key: the warm-up host key, or the raw host for URLs that are never warmed."""
    target = _warm_target(url)
    return target[0] if target else (urlparse(url).hostname or url)


# Per-host memory: {"needs_warmup": bool, "last_warm": epoch seconds, "fails": [epoch seconds of failed visits]}
# Only touched from the browser loop's thread.
_hosts: dict[str, dict] = {}
_last_warm: dict[str, float] = {}   # host -> time.monotonic() of its last successful warm-up (cooldown)


def _load_hosts() -> None:
    """Load the per-host memory from HOSTS_FILE (missing or unreadable = start empty)."""
    _hosts.clear()
    try:
        with open(HOSTS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _hosts.update({k: v for k, v in data.items() if isinstance(v, dict)})
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("warm-up: could not read %s (starting empty): %s", HOSTS_FILE, exc)


def _save_hosts() -> None:
    """Write the per-host memory atomically. Never raises."""
    try:
        tmp = f"{HOSTS_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_hosts, fh, indent=1, sort_keys=True)
        os.replace(tmp, HOSTS_FILE)
    except OSError as exc:
        log.warning("warm-up: could not write %s: %s", HOSTS_FILE, exc)


def _recent_fails(entry: dict) -> list[float]:
    """Failed visits still inside the WARMUP_ALWAYS_DAYS window."""
    cutoff = time.time() - WARMUP_ALWAYS_DAYS * 86400
    return [t for t in entry.get("fails", []) if t >= cutoff]


def _should_warm(host: str) -> bool:
    """New host, one that failed last time, or a frequent challenger (and not warmed very recently)."""
    if time.monotonic() - _last_warm.get(host, -1e9) < WARMUP_COOLDOWN:
        return False
    entry = _hosts.get(host)
    if entry is None:
        return True
    return bool(entry.get("needs_warmup")) or len(_recent_fails(entry)) >= WARMUP_ALWAYS_AFTER


def _record_visit(host: str, state: str) -> None:
    """Learn from a page load: a challenge/block means the next visit warms up first."""
    entry = _hosts.setdefault(host, {})
    entry["fails"] = _recent_fails(entry)
    if state == "ok":
        entry["needs_warmup"] = False
    else:
        entry["needs_warmup"] = True
        entry["fails"] = [*entry["fails"], time.time()][-50:]  # capped: a page that always fails must not grow forever
        log.warning("%s: page ended as %r (%d failure(s) on record)", host, state, len(entry["fails"]))
    _save_hosts()


async def _warmup_host(tab, host: str, root: str) -> None:
    """Visit the site root in the job's window and record the outcome."""
    try:
        state = await _warm_url(tab, root)
    except Exception as exc:
        log.warning("warm-up failed for %s: %r", host, exc)
        state = "challenge"
    entry = _hosts.setdefault(host, {})
    entry["fails"] = _recent_fails(entry)
    if state == "ok":
        entry["needs_warmup"] = False
        entry["last_warm"] = time.time()
        _last_warm[host] = time.monotonic()
    else:
        entry["needs_warmup"] = True
    _save_hosts()


# ---------------------------------------------------------------------------
# Chrome manager
# ---------------------------------------------------------------------------

class _Chrome:
    """Owns the single Chrome and its event loop in one daemon thread (see module docstring)."""

    def __init__(self):
        self.loop = None
        self.browser = None              # cdp_driver Browser (sb.driver.cdp_base)
        self.sb = None
        self._cm = None                  # the SB(...) context manager
        self._generation = 0             # bumped on every launch; stale stop requests are ignored
        self._wanted = threading.Event()   # set by the first caller: launch lazily
        self._ready = threading.Event()    # Chrome up and its loop running
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name='chrome', daemon=True)
        self._thread.start()

    # ---- browser thread ----------------------------------------------------

    def _run(self):
        self._wanted.wait()
        _trim_profile()
        _load_hosts()
        log.info("userscripts: %s", ', '.join(s.name for s in USERSCRIPTS) or 'none')
        while not self._stopping:
            try:
                self._launch()
            except Exception:
                log.exception("Chrome launch failed; retrying in 10s")
                self._teardown()
                time.sleep(10)
                continue
            self._ready.set()
            self.loop.run_forever()      # until loop.stop(): restart or shutdown
            self._ready.clear()
            self._teardown()

    def _launch(self):
        from seleniumbase import SB
        os.makedirs(CHROME_USER_DATA_DIR, exist_ok=True)
        log.info("launching Chrome (uc + CDP mode, headed on %s), profile %s", os.getenv('DISPLAY'), CHROME_USER_DATA_DIR)
        # headed=True: use the base image's Xvfb; without it SeleniumBase starts its own display on Linux
        self._cm = SB(uc=True, headed=True, binary_location=CHROMIUM, user_data_dir=CHROME_USER_DATA_DIR,
                      incognito=False, ad_block=True, uc_cdp_events=True)
        self.sb = self._cm.__enter__()
        self.sb.activate_cdp_mode("about:blank")   # disconnects WebDriver; Chrome is now driven over CDP
        self.loop = self.sb.cdp.get_event_loop()
        self.browser = self.sb.driver.cdp_base
        self._generation += 1
        # asyncio primitives are bound to this loop; fresh ones for every launch
        self._windows = asyncio.Semaphore(MAX_WINDOWS)
        self._site_locks: dict[str, asyncio.Lock] = {}
        self._uc_lock = asyncio.Lock()
        log.info("Chrome ready: %s, debug port %s", self.sb.cdp.get_endpoint_url(), self.browser.config.port)

    def _teardown(self):
        """Cancel leftover jobs and shut down what is left of SB/Chrome. Never raises."""
        loop = self.loop
        if loop is not None and not loop.is_closed():
            with suppress(Exception):
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        if self._cm is not None:
            with suppress(BaseException):
                self._cm.__exit__(None, None, None)
        self._cm = self.sb = self.browser = self.loop = None

    # ---- inside the loop ---------------------------------------------------

    async def _alive(self) -> bool:
        try:
            await asyncio.wait_for(self.browser.connection.send(mycdp.browser.get_version()), timeout=5)
            return True
        except Exception:
            return False

    async def _open_window(self, url: str):
        """New window (not tab) at about:blank, sized to the screen, with matching userscripts injected."""
        tab = await asyncio.wait_for(self.browser.get("about:blank", new_window=True), timeout=NAV_TIMEOUT)
        with suppress(Exception):
            await tab.set_window_size(0, 0, WINDOW_W, WINDOW_H)
        scripts = [s for s in USERSCRIPTS if s.matches(url)]
        if scripts:
            # without Page.enable the scripts are registered but do not run (verified)
            await tab.send(mycdp.page.enable())
        for script in scripts:
            await tab.send(mycdp.page.add_script_to_evaluate_on_new_document(source=script.source))
            log.info("userscript %s injected for %s", script.name, url)
        return tab

    async def _window_open(self, url: str, uc: bool):
        """
        Wait for this window's turn, open it and warm the site up if needed. Returns (tab, held locks).
        uc=False: the site's lock (site lock first, so same-site waiters hold no slot), then one window slot.
        uc=True: every window slot (exclusive: WebDriver can follow only one window), FIFO behind other uc users.
        """
        held = []   # release functions, released in reverse order
        try:
            if uc:
                await self._uc_lock.acquire()
                held.append(self._uc_lock.release)
                for _ in range(MAX_WINDOWS):
                    await self._windows.acquire()
                    held.append(self._windows.release)
            else:
                lock = self._site_locks.setdefault(_site_key(url), asyncio.Lock())
                await lock.acquire()
                held.append(lock.release)
                await self._windows.acquire()
                held.append(self._windows.release)
            tab = await self._open_window(url)
            try:
                target = _warm_target(url)
                if target and _should_warm(target[0]):
                    await _warmup_host(tab, *target)
            except BaseException:
                with suppress(Exception):
                    await asyncio.wait_for(tab.close(), timeout=10)
                raise
            return tab, held
        except BaseException:
            for release in reversed(held):
                release()
            raise

    async def _window_close(self, tab, held):
        try:
            with suppress(Exception):
                await asyncio.wait_for(tab.close(), timeout=10)
        finally:
            for release in reversed(held):
                release()

    # ---- caller threads ----------------------------------------------------

    def _call(self, coro_factory, timeout: float):
        """Run coro_factory() on the browser loop from a sync thread; return its result."""
        loop = self.loop
        fut = asyncio.run_coroutine_threadsafe(coro_factory(), loop)
        try:
            return fut.result(timeout)
        except TimeoutError:
            fut.cancel()
            raise BrowserError(f"browser job timed out after {timeout:.0f}s") from None

    def _ensure_ready(self):
        """Launch Chrome on first use; relaunch it if it died. Returns when it answers."""
        self._wanted.set()
        for _ in range(2):
            if not self._ready.wait(LAUNCH_TIMEOUT):
                raise BrowserError(f"Chrome did not start within {LAUNCH_TIMEOUT}s")
            generation, loop = self._generation, self.loop
            try:
                if self._call(self._alive, 15):
                    return
            except Exception:
                pass
            log.warning("Chrome is not answering; restarting it")
            self._request_restart(generation, loop)
        raise BrowserError("Chrome could not be restarted")

    def _request_restart(self, generation, loop):
        """Stop the loop of that launch (once); the browser thread then relaunches Chrome."""
        if generation == self._generation and self._ready.is_set():
            self._ready.clear()
            loop.call_soon_threadsafe(loop.stop)

    def open_window(self, url: str, uc: bool, timeout: float) -> "Page":
        self._ensure_ready()
        generation, loop = self._generation, self.loop
        tab, held = self._call(lambda: self._window_open(url, uc), timeout)
        return Page(self, tab, held, uc, time.monotonic() + timeout, generation, loop)

    def close_window(self, page: "Page"):
        page._disconnect()
        # after a Chrome restart the window and its locks belong to the old launch: nothing to release
        if page._generation == self._generation and self._ready.is_set():
            with suppress(Exception):
                self._call(lambda: self._window_close(page.tab, page._held), 30)

    def guarded_call(self, coro_factory, timeout: float, generation, loop):
        """_call for a window's step: a dead Chrome fails the step clearly and triggers a relaunch."""
        try:
            return self._call(coro_factory, timeout)
        except BrowserError:
            raise
        except Exception as exc:
            try:
                alive = self._call(self._alive, 15)
            except Exception:
                alive = False
            if not alive:
                self._request_restart(generation, loop)
                raise BrowserError(f"Chrome died during the job ({exc!r}); it is being restarted") from exc
            raise

    def stop(self):
        """Shut down Chrome (atexit), so recent cookies get written to the profile."""
        self._stopping = True
        loop = self.loop
        if self._ready.is_set() and loop is not None:
            self._ready.clear()
            loop.call_soon_threadsafe(loop.stop)
            self._thread.join(timeout=20)


class Page:
    """
    One Chrome window of a `with window(...)` block. Every method is synchronous (it runs a CDP step on
    the browser loop). With uc=True, page.driver gives WebDriver for the same window.
    """

    def __init__(self, chrome, tab, held, uc, deadline, generation, loop):
        self._chrome, self.tab, self._held, self._uc = chrome, tab, held, uc
        self._deadline, self._generation, self._loop = deadline, generation, loop
        self._connected = False

    def _run(self, coro_factory):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise BrowserError("browser window timed out")
        return self._chrome.guarded_call(coro_factory, remaining, self._generation, self._loop)

    # ---- CDP --------------------------------------------------------------

    def open(self, url: str) -> str:
        """Load url (WebDriver disconnected first), wait until complete and through any bot check.
        Returns the page state: "ok", "challenge" or "blocked"."""
        self._disconnect()
        return self._run(lambda: _open_page(self.tab, url))

    def wait(self, selector: str, timeout: float = 60) -> None:
        """Wait until selector exists and scroll it into view."""
        self._run(lambda: _wait_for_selector(self.tab, selector, timeout))

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def html(self) -> str:
        return self._run(self.tab.get_page_source)

    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html(), "lxml")

    @property
    def title(self) -> str:
        return self._run(self.tab.get_title)

    @property
    def url(self) -> str:
        return self._run(self.tab.get_current_url)

    def js(self, script: str):
        """Evaluate script (an expression; wrap statements in a function); a returned Promise is awaited."""
        return self._run(lambda: self.tab.evaluate(script, await_promise=True))

    def screenshot(self, selector: str) -> str:
        """CDP screenshot of the element matching selector, base64 PNG."""
        return self._run(lambda: _element_screenshot(self.tab, selector))

    # ---- UC / WebDriver ---------------------------------------------------

    @property
    def driver(self):
        """
        Selenium WebDriver switched to this window (connected on first use; open() disconnects it again).
        Only in window(url, uc=True). Use driver.* (find_element, screenshot_as_base64, execute_script, ...).
        """
        if not self._uc:
            raise BrowserError("page.driver needs window(url, uc=True)")
        sb = self._chrome.sb
        if not self._connected:
            sb.connect()   # reconnect WebDriver (chromedriver) to the running Chrome
            self._connected = True
            sb.driver.switch_to.window(self.tab.target.target_id)
        return sb.driver

    def _disconnect(self):
        if self._connected:
            self._connected = False
            with suppress(Exception):
                self._chrome.sb.disconnect()


_chrome = _Chrome()
atexit.register(_chrome.stop)


# ---------------------------------------------------------------------------
# Public API (sync, for spiders running in Flask threads)
# ---------------------------------------------------------------------------

@contextmanager
def window(url: str, uc: bool = False, timeout: float = 300):
    """
    Open a new Chrome window for url's site (warmed up first if needed, userscripts injected; it starts at
    about:blank) and yield a Page; the window is closed when the block ends, also on errors.

        with window(url) as page:            # CDP; other sites' windows may be open at the same time
            page.open(url); page.wait('article'); soup = page.soup()
        with window(url, uc=True) as page:   # also page.driver (WebDriver); exclusive while open
            page.open(url); png = page.driver.find_element('css selector', 'h1').screenshot_as_base64

    Waits for its turn: one window per site, at most MAX_WINDOWS at once, uc=True alone (in arrival order).
    timeout: seconds for waiting for the turn, and again for the work inside the block.
    Raises BrowserError if Chrome is unavailable or dies.
    """
    page = _chrome.open_window(url, uc, timeout)
    try:
        yield page
    finally:
        _chrome.close_window(page)


async def _open_page(tab, url: str) -> str:
    """Navigate tab to url, wait out a bot check, and remember the outcome for warm-ups. Returns the state."""
    await asyncio.wait_for(tab.get(url), timeout=NAV_TIMEOUT)
    # tab.get() can return while the document is still streaming in (verified: half a JSON body)
    deadline = time.monotonic() + NAV_TIMEOUT
    while time.monotonic() < deadline:
        with suppress(Exception):
            if await tab.evaluate("document.readyState") == "complete":
                break
        await tab.sleep(0.5)
    state = _classify_page(await tab.get_title() or "", await tab.get_page_source() or "")
    if state == "challenge":
        state = await _wait_for_cloudflare(tab, WARMUP_TIMEOUT)
    target = _warm_target(url)
    if target:
        _record_visit(target[0], state)
    return state


async def _wait_for_selector(tab, selector: str, timeout: float = 60):
    """Wait until selector exists, scroll it into view and return the element."""
    element = await tab.select(selector, timeout=timeout)
    await element.scroll_into_view_async()
    return element


async def _element_screenshot(tab, selector: str) -> str:
    """
    Base64 PNG of the element matching selector. The clip needs PAGE coordinates: the element's
    position relative to the window + window.scrollX/scrollY (otherwise right size, wrong place).
    """
    rect = await tab.evaluate(
        f"(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return null;"
        f" const r = e.getBoundingClientRect();"
        f" return [r.x + window.scrollX, r.y + window.scrollY, r.width, r.height]; }})()"
    )
    if not rect:
        raise BrowserError(f"screenshot: no element matches {selector!r} on {await tab.get_current_url()}")
    x, y, width, height = rect
    clip = mycdp.page.Viewport(x=x, y=y, width=width, height=height, scale=1)
    return await tab.send(mycdp.page.capture_screenshot(format_="png", clip=clip, capture_beyond_viewport=True))
