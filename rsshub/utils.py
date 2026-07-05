import re
from flask import Response
import requests
from parsel import Selector
import bs4
from bs4 import BeautifulSoup 

# https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
DEFAULT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'}

class XMLResponse(Response):
    def __init__(self, response, **kwargs):
        if 'mimetype' not in kwargs and 'contenttype' not in kwargs:
            if response.startswith('<?xml'):
                kwargs['mimetype'] = 'application/xml'
        return super().__init__(response, **kwargs)

def fetch(url: str, headers: dict=DEFAULT_HEADERS, proxies: dict=None):
    try:
        res = requests.get(url, headers=headers, proxies=proxies)
        res.raise_for_status()
    except Exception as e:
        print(f'[Err] {e}')
    else:
        html = res.text
        tree = Selector(text=html)
        return tree

def fetch_by_requests(url: str, headers: dict=DEFAULT_HEADERS, proxies: dict=None):
    try:
        res = requests.get(url, headers=headers, proxies=proxies)
        res.raise_for_status()
    except Exception as e:
        print(f'[Err] {e}')
    else:
        soup = BeautifulSoup(res.content, "lxml")
        return soup

# # manually setup chromium profile  
# https://github.com/seleniumbase/SeleniumBase/blob/master/seleniumbase/plugins/driver_manager.py#L66
# 
# from seleniumbase import Driver
# driver = Driver(headless=False, headed=True, undetectable=True, uc_cdp_events=True, driver_version="keep", incognito=False, mobile=False, disable_csp=True, ad_block=True, user_data_dir="/home/parallels/Desktop/chromiumprofile")
# driver.open("https://bot.sannysoft.com")  # https://nowsecure.nl/#relax   https://bot.sannysoft.com
# 
# https://chromewebstore.google.com/detail/scriptcat/ndcooeababalnlpkfedmmbbbgkljhpjf?hl=en-US
# https://greasyfork.org/en/scripts/514737-bloomberg-paywall-bypass
# https://www.bloomberg.com/latest/markets-wrap
        # # outdated: https://chromewebstore.google.com/detail/violentmonkey/jinjaccalgkegednnccohejagnlnfdag

def fetch_by_browser(url, user_data_dir = None, HEADED = None, DEBUG = None, wait = 3):
    # https://github.com/seleniumbase/SeleniumBase/discussions/2118
    # run uc mode to manually set up profile; profile folder should be nonexistent
    # then it will be created by uc and not be deleted even after closing the browser
    # https://nowsecure.nl/#relax   https://bot.sannysoft.com
    # to update profile, run the following in ipython, then overwrite the profile folder:
    #   ipython
    #   from rsshub.utils import fetch_by_browser; fetch_by_browser(url)
    import os, time

    def is_ipython_interactive():
        try:
            from IPython import get_ipython
            ipython = get_ipython()
            if ipython is None:
                return False
            # TerminalInteractiveShell = interactive IPython
            # ZMQInteractiveShell = Jupyter notebook
            return ipython.__class__.__name__ in ['TerminalInteractiveShell', 'ZMQInteractiveShell']
        except (ImportError, AttributeError):
            return False
    # assume in dev mode if in ipython interactive shell
    if is_ipython_interactive(): os.environ['FLASK_ENV'] = 'development'

    # print(list(os.environ.items()))
    # vmd
    if os.getenv('FLASK_ENV') == "development" and 'XDG_CURRENT_DESKTOP' in os.environ:
        home = os.path.expanduser("~")
        if user_data_dir is None: user_data_dir = f"{home}/Desktop/chromiumprofile"
        os.system(f"rm -rf {user_data_dir}")
        os.system(f"cp -r {home}/Desktop/rsshub_python/rsshub/chromiumprofile {user_data_dir}")
        if HEADED is None: HEADED = True
        if DEBUG is None: DEBUG = True
    # vmo
    elif os.getenv('FLASK_ENV') == "development" and 'XDG_CURRENT_DESKTOP' not in os.environ:
        home = os.path.expanduser("~")
        if user_data_dir is None: user_data_dir = f"{home}/chromiumprofile"
        os.system(f"rm -rf {user_data_dir}")
        os.system(f"cp -r {home}/rsshub_python/rsshub/chromiumprofile {user_data_dir}")
        if HEADED is None: HEADED = False
        if DEBUG is None: DEBUG = False
    else:
        if user_data_dir is None: user_data_dir = "/app/rsshub/chromiumprofile"
        if HEADED is None: HEADED = False
        if DEBUG is None: DEBUG = False

    # https://github.com/seleniumbase/SeleniumBase/blob/master/seleniumbase/plugins/sb_manager.py
    # https://seleniumbase.io/examples/cdp_mode/ReadMe/#cdp-mode-usage
    from seleniumbase import SB
    # Force-kills any lingering Chrome or Chromedriver processes.
    import subprocess
    try:
        # pkill -f searches the entire command line for 'chrome' and 'chromedriver'
        subprocess.run(["pkill", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "chromedriver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        # It's perfectly fine if pkill fails (e.g., if no zombies exist)
        pass
    with SB(headless=True, headed=HEADED, maximize=True,
            undetectable=True, uc_cdp_events=True, driver_version="keep", 
            incognito=False, mobile=False, disable_csp=True, ad_block=True, 
            user_data_dir=user_data_dir) as sb:
        soups, sources, urls, titles = [], [], [], []
        url = [url] if type(url) is not list else url
        for i, u in enumerate(url):
            if i == 0:
                sb.activate_cdp_mode(u)
            else:
                sb.cdp.open_new_tab(u)
                sb.cdp.switch_to_newest_tab()
            # wait for page to load?
            time.sleep(wait)
            source = sb.get_page_source()
            sources.append(source)
            soups.append(BeautifulSoup(source, "lxml"))
            urls.append(sb.get_current_url())
            titles.append(sb.get_page_title())
        # n(next), s(step), c(continue), q(quit)
        if DEBUG: import pdb; pdb.set_trace()
        if len(url)==1:
            return soups[0], sources[0], urls[0], titles[0]
        else:
            return soups, sources, urls, titles

def fetch_by_browser2(url, user_data_dir=None, HEADED=None, DEBUG=None, wait=3):
    # Pure CDP Mode (no WebDriver/chromedriver) with Xvfb virtual display.
    # Chrome always runs headed on Xvfb (:99); HEADED param is kept for API
    # compatibility with fetch_by_browser but does not change this behaviour.
    import os, time, asyncio, subprocess

    # Stub tkinter so mouseinfo (pulled in by seleniumbase/pyautogui)
    # doesn't call sys.exit() when the system package is absent.
    import sys, types, importlib
    for _mod in ('tkinter', 'tkinter.font', 'tkinter.ttk', 'tkinter.constants'):
        if _mod not in sys.modules:
            try:
                importlib.import_module(_mod)
            except ImportError:
                sys.modules[_mod] = types.ModuleType(_mod)

    WINDOW_W, WINDOW_H = 1920, 1080

    _STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});
if (!window.chrome) { window.chrome = {}; }
if (!window.chrome.runtime) { window.chrome.runtime = {}; }
const __origPermQuery__ = window.navigator.permissions.query.bind(navigator.permissions);
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : __origPermQuery__(p);
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en'], configurable: true});
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
        get: () => { const p = [1,2,3]; p.refresh=()=>{}; return p; },
        configurable: true,
    });
}
"""

    def is_ipython_interactive():
        try:
            from IPython import get_ipython
            ipython = get_ipython()
            if ipython is None:
                return False
            return ipython.__class__.__name__ in ['TerminalInteractiveShell', 'ZMQInteractiveShell']
        except (ImportError, AttributeError):
            return False

    if is_ipython_interactive():
        os.environ['FLASK_ENV'] = 'development'

    # vmd
    if os.getenv('FLASK_ENV') == "development" and 'XDG_CURRENT_DESKTOP' in os.environ:
        home = os.path.expanduser("~")
        if user_data_dir is None: user_data_dir = f"{home}/Desktop/chromiumprofile"
        os.system(f"rm -rf {user_data_dir}")
        os.system(f"cp -r {home}/Desktop/rsshub_python/rsshub/chromiumprofile {user_data_dir}")
        if DEBUG is None: DEBUG = True
    # vmo
    elif os.getenv('FLASK_ENV') == "development" and 'XDG_CURRENT_DESKTOP' not in os.environ:
        home = os.path.expanduser("~")
        if user_data_dir is None: user_data_dir = f"{home}/chromiumprofile"
        os.system(f"rm -rf {user_data_dir}")
        os.system(f"cp -r {home}/rsshub_python/rsshub/chromiumprofile {user_data_dir}")
        if DEBUG is None: DEBUG = False
    else:
        if user_data_dir is None: user_data_dir = "/app/rsshub/chromiumprofile"
        if DEBUG is None: DEBUG = False

    # Kill any lingering Chrome/chromedriver processes
    try:
        subprocess.run(["pkill", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "chromedriver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # Always start Xvfb virtual display; Chrome runs headed on it
    xvfb_proc = None
    try:
        xvfb_proc = subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", f"{WINDOW_W}x{WINDOW_H}x24", "-ac"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = ":99"
        time.sleep(0.5)  # give Xvfb time to initialise
    except Exception as e:
        print(f"[Warn] Xvfb start failed (falling back to headless): {e}")
        xvfb_proc = None

    async def _run():
        import mycdp.page
        from seleniumbase import cdp_driver

        driver = await cdp_driver.start_async(
            headless=False,  # always headed on Xvfb virtual display
            no_sandbox=True,
            agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
            lang="en-US",
            user_data_dir=user_data_dir,
        )
        try:
            tab = await driver.get("about:blank")
            await tab.set_window_size(0, 0, WINDOW_W, WINDOW_H)
            # Inject stealth patches before any page script runs
            try:
                await tab._send_oneshot(
                    mycdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH_JS)
                )
            except Exception as e:
                print(f"[Warn] Stealth JS injection failed (non-fatal): {e}")

            soups, sources, result_urls, titles = [], [], [], []
            urls_list = [url] if not isinstance(url, list) else url
            for u in urls_list:
                await tab.get(u)
                await tab.sleep(wait)
                # Attempt to click any bot-detection widget (CF Turnstile,
                # reCAPTCHA, hCaptcha, FriendlyCaptcha).
                await _solve_captcha_if_present(tab)
                # Poll until the challenge page clears (title set + source markers).
                for _ in range(15):
                    if not await _is_challenge_page(tab):
                        break
                    await _solve_captcha_if_present(tab)
                    await tab.sleep(2)
                # Let the page's CDP events settle before capturing —
                # same mechanism tab.get() uses internally (connection.wait).
                await tab.wait()
                source = await tab.get_content()
                current_url = tab.target.url
                title = await tab.evaluate("document.title")
                sources.append(source)
                soups.append(BeautifulSoup(source, "lxml"))
                result_urls.append(current_url)
                titles.append(title)

            if len(urls_list) == 1:
                return soups[0], sources[0], result_urls[0], titles[0]
            else:
                return soups, sources, result_urls, titles
        finally:
            try:
                driver.stop()  # synchronous: terminates Chrome process
            except Exception:
                pass
            # Wait for Chrome to actually exit so SIGCHLD is handled
            # while the event loop is still open.
            if hasattr(driver, '_process') and driver._process is not None:
                try:
                    await asyncio.wait_for(driver._process.wait(), timeout=5.0)
                except Exception:
                    pass

    # Always create a fresh event loop to avoid "loop is closed" errors on
    # repeated calls or when running inside Flask / IPython.
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        result = _loop.run_until_complete(_run())
        if DEBUG:
            import pdb; pdb.set_trace()
        return result
    finally:
        # Cancel pending tasks, detach child watcher, then close —
        # matches what asyncio.run() does internally.
        try:
            _pending = asyncio.all_tasks(_loop)
            if _pending:
                for _t in _pending:
                    _t.cancel()
                _loop.run_until_complete(
                    asyncio.gather(*_pending, return_exceptions=True)
                )
            _loop.run_until_complete(_loop.shutdown_asyncgens())
        except Exception:
            pass
        finally:
            asyncio.set_event_loop(None)  # detaches child watcher from loop
            _loop.close()
        if xvfb_proc is not None:
            xvfb_proc.terminate()
            try:
                xvfb_proc.wait(timeout=3)
            except Exception:
                xvfb_proc.kill()

async def _is_challenge_page(tab):
    """
    Return True if the current page is a bot-detection challenge.
    Checks both a broad set of known challenge titles and the same source
    markers used by server.py / _solve_captcha_if_present.
    Title check is tried first (cheap); source check is the fallback.
    """
    _CHALLENGE_TITLES = {
        "Just a moment...",                       # CF managed challenge
        "Please Wait...",                         # CF (older)
        "Attention Required! | Cloudflare",       # CF WAF block
        "One more step",                          # CF (older)
        "DDoS protection by Cloudflare",
        "Access denied | Cloudflare",
        "Security | Cloudflare",
    }
    try:
        title = await tab.evaluate("document.title")
        if title in _CHALLENGE_TITLES:
            return True
        source = await tab.get_content()
        return (
            "cf-turnstile-" in source
            or "/challenge-platform/h/b/" in source
            or 'id="challenge-widget-' in source
            or "challenges.cloudf" in source
        )
    except Exception:
        return False


async def _solve_captcha_if_present(tab):
    """
    Detect and click common bot-detection challenges (CF Turnstile, reCAPTCHA,
    hCaptcha, FriendlyCaptcha).  Non-fatal — all errors are swallowed.
    Returns True if a challenge was found and a click was attempted.
    Adapted from server.py's _solve_captcha_if_present.
    """
    import mycdp.input_

    async def _is_present(sel):
        try:
            return (await tab.select(sel, timeout=0.1)) is not None
        except Exception:
            return False

    async def _is_visible(sel):
        try:
            el = await tab.select(sel, timeout=0.1)
            if el is None:
                return False
            pos = await el.get_position_async()
            return pos.width != 0 or pos.height != 0
        except Exception:
            return False

    async def _click_offset(sel, x_off, y_off):
        """Select element and click at center + (x_off, y_off)."""
        try:
            el = await tab.select(sel, timeout=5)
            if el is None:
                return False
            await el.scroll_into_view_async()
            await tab.bring_to_front()
            await tab.sleep(0.056)
            pos = await el.get_position_async()
            x = pos.center[0] + x_off
            y = pos.center[1] + y_off
            for etype in ("mousePressed", "mouseReleased"):
                await tab.send(
                    mycdp.input_.dispatch_mouse_event(
                        etype, x=x, y=y,
                        button=mycdp.input_.MouseButton("left"),
                        buttons=1, click_count=1,
                    )
                )
            await tab.sleep(0.2)
            return True
        except Exception as e:
            print(f"[Warn] _click_offset({sel!r}, {x_off}, {y_off}): {e}")
            return False

    await tab.sleep(0.1)
    try:
        source = await tab.get_content()
    except Exception:
        return False

    # ── Cloudflare Turnstile detection ──────────────────────────────────────
    is_cf = (
        "cf-turnstile-" in source
        or "/challenge-platform/h/b/" in source
        or 'id="challenge-widget-' in source
        or "challenges.cloudf" in source
        or (
            'data-callback="onCaptchaSuccess"' in source
            and 'title="reCAPTCHA"' not in source
            and 'id="recaptcha-token"' not in source
        )
    )

    if not is_cf:
        # ── reCAPTCHA detection ─────────────────────────────────────────────
        await tab.sleep(0.4)
        source = await tab.get_content()
        recaptcha_in_source = (
            'id="recaptcha-token"' in source or 'title="reCAPTCHA"' in source
        )
        is_recaptcha = recaptcha_in_source and await _is_visible('iframe[title="reCAPTCHA"]')
        if not is_recaptcha and "com/recaptcha/api.js" in source:
            await tab.sleep(1.2)
            is_recaptcha = await _is_visible('iframe[title="reCAPTCHA"]')
        if is_recaptcha:
            print("[Info] reCAPTCHA detected — attempting click")
            await tab.sleep(0.5)
            # Skip invisible reCAPTCHA widget in the bottom-right corner
            try:
                el = await tab.select('iframe[title="reCAPTCHA"]', timeout=0.5)
                pos = await el.get_position_async()
                win_w = await tab.evaluate("window.innerWidth")
                win_h = await tab.evaluate("window.innerHeight")
                if (pos.x > 1040 and pos.y > 640
                        and abs(win_w - pos.x) < 110
                        and abs(win_h - pos.y) < 110):
                    return False
            except Exception:
                pass
            return await _click_offset('iframe[title="reCAPTCHA"]', 26, 35)

        # ── hCaptcha detection ──────────────────────────────────────────────
        await tab.sleep(0.1)
        is_hcaptcha = (
            await _is_visible('iframe[src*="_Incapsula_Resource?"]')
            or await _is_visible("iframe[data-hcaptcha-widget-id]")
        )
        if is_hcaptcha:
            print("[Info] hCaptcha detected — attempting click")
            await tab.sleep(0.2)
            if await _is_visible('iframe[src*="_Incapsula_Resource?"]'):
                try:
                    outer = await tab.select('iframe[src*="_Incapsula_Resource?"]', timeout=0.5)
                    inner = await outer.query_selector_async("iframe[data-hcaptcha-widget-id]")
                    if not inner:
                        return False
                    await tab.bring_to_front()
                    await tab.sleep(0.056)
                    pos = await inner.get_position_async()
                    x, y = pos.center[0] + 30, pos.center[1] + 36
                    for etype in ("mousePressed", "mouseReleased"):
                        await tab.send(
                            mycdp.input_.dispatch_mouse_event(
                                etype, x=x, y=y,
                                button=mycdp.input_.MouseButton("left"),
                                buttons=1, click_count=1,
                            )
                        )
                    await tab.sleep(0.75)
                    return True
                except Exception as e:
                    print(f"[Warn] nested hCaptcha click failed: {e}")
                    return False
            else:
                return await _click_offset("iframe[data-hcaptcha-widget-id]", 30, 36)

        # ── FriendlyCaptcha detection ───────────────────────────────────────
        await tab.sleep(0.05)
        if await _is_visible("iframe[data--frc-frame-id]"):
            print("[Info] FriendlyCaptcha detected — attempting click")
            await tab.sleep(0.2)
            try:
                el = await tab.select("iframe[data--frc-frame-id]", timeout=0.5)
                if not el:
                    return False
                pos = await el.get_position_async()
                win_w = await tab.evaluate("window.innerWidth")
                win_h = await tab.evaluate("window.innerHeight")
                if (pos.x > 1040 and pos.y > 640
                        and abs(win_w - pos.x) < 110
                        and abs(win_h - pos.y) < 110):
                    return False
                await tab.bring_to_front()
                await tab.sleep(0.06)
                await el.mouse_move_async()
                await tab.sleep(0.08)
                result = await _click_offset("iframe[data--frc-frame-id]", 27, 34)
                await tab.sleep(0.25)
                return result
            except Exception as e:
                print(f"[Warn] FriendlyCaptcha click failed: {e}")
                return False

        return False  # nothing detected

    # ── Cloudflare Turnstile click ───────────────────────────────────────────
    print("[Info] CF Turnstile detected — attempting click")
    _CF_CANDIDATES = [
        '[class="cf-turnstile"]',
        "#challenge-form div > div",
        '[style="display: grid;"] div div',
        '[class*=spacer] + div div',
        ".spacer div:not([class])",
        '[data-testid*="challenge-"] div',
        "div#turnstile-widget div:not([class])",
        "ngx-turnstile div:not([class])",
        'form div:not([class]):has(input[name*="cf-turn"])',
        "body > div#check > div:not([class])",
        ".cf-turnstile-wrapper",
        '[id*="turnstile"] div:not([class])',
        '[class*="turnstile"] div:not([class])',
        "iframe[data-hcaptcha-widget-id]",
        '[data-callback="onCaptchaSuccess"]',
        '[class*="captcha"] div:not([class])',
        "form div:not(:has(*))",
        "div:not([class]):not([id]):not([aria-label]) > div:not([class]):not([id]):not([aria-label])",
    ]

    # Apply alignment fixes once before any click attempt
    try:
        if (await _is_present('form[class*="center"]') or await _is_present('form[class*="right"]')
                or await _is_present('form div[class*="center"]') or await _is_present('form div[class*="right"]')):
            await tab.evaluate(
                "var $e=document.querySelectorAll('form[class], form div[class]');"
                "for(var i=0;i<$e.length;i++){var c=$e[i].getAttribute('class');"
                "c=c.replaceAll('center','left').replaceAll('right','left');"
                "$e[i].setAttribute('class',c);}"
            )
            await tab.sleep(0.1)
        elif (await _is_present('form div[style*="center"]') or await _is_present('form div[style*="right"]')):
            await tab.evaluate(
                "var $e=document.querySelectorAll('form[style], form div[style]');"
                "for(var i=0;i<$e.length;i++){var s=$e[i].getAttribute('style');"
                "s=s.replaceAll('center','left').replaceAll('right','left');"
                "$e[i].setAttribute('style',s);}"
            )
            await tab.sleep(0.1)
        elif (await _is_present('form [id*="turnstile"] div:not([class])')
              or await _is_present('form [class*="turnstile"] div:not([class])')):
            await tab.evaluate(
                "var $e=document.querySelectorAll('form [id*=\"turnstile\"]');"
                "for(var i=0;i<$e.length;i++){$e[i].setAttribute('align','left');}"
                "var $e=document.querySelectorAll('form [class*=\"turnstile\"]');"
                "for(var i=0;i<$e.length;i++){$e[i].setAttribute('align','left');}"
            )
            await tab.sleep(0.1)
        elif await _is_present('[style*="text-align: center;"] div:not([class])'):
            await tab.evaluate(
                "var $e=document.querySelectorAll('[style*=\"text-align: center;\"]');"
                "for(var i=0;i<$e.length;i++){var s=$e[i].getAttribute('style');"
                "s=s.replaceAll('center','left');$e[i].setAttribute('style',s);}"
            )
            await tab.sleep(0.1)
    except Exception as e:
        print(f"[Warn] CF alignment fix failed: {e}")

    # Iterate through all present candidates; skip to next if click times out
    for candidate in _CF_CANDIDATES:
        if not await _is_present(candidate):
            continue
        if candidate == '[style="display: grid;"] div div':
            try:
                await tab.evaluate(
                    "var $e=document.querySelectorAll('[style=\"display: grid;\"] div div');"
                    "for(var i=0;i<$e.length;i++){$e[i].setAttribute('style','text-align:left;');}"
                )
                await tab.sleep(0.025)
            except Exception:
                pass
        await tab.sleep(0.08)
        result = await _click_offset(candidate, 25, 32)
        if result:
            await tab.sleep(5)  # wait for CF challenge to resolve after click
            print(f"[Info] CF Turnstile clicked ({candidate!r})")
            return True
        print(f"[Info] CF candidate {candidate!r} failed, trying next")

    print("[Warn] CF Turnstile: no candidate could be clicked")
    return False

async def fetch_by_puppeteer(url):
    try:
        from pyppeteer import launch
    except Exception as e:
        print(f'[Err] {e}')
    else:
        browser = await launch(  # 启动浏览器
            {'args': ['--no-sandbox']},
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False
        )
        page = await browser.newPage()  # 创建新页面
        await page.goto(url)  # 访问网址
        html = await page.content()  # 获取页面内容
        await browser.close()  # 关闭浏览器
        return Selector(text=html)

def extract_html(element):
    """
    element: a soup find object, or find_all object
    """
    if element is None:
        return ""
    else:
        if type(element) in [bs4.element.ResultSet, list]:
            return ''.join([str(e) for e in element])
        else:
            return str(element)

def escape_html(html_content):
    """
    Escape unescaped HTML tags while preserving already escaped characters.
    """
    import html
    html_content = str(html_content)
    # Regex to match unescaped HTML tags
    pattern = re.compile(r"(?<!&lt;)(<[^>]+>)(?!&gt;)")
    # Replace unescaped tags with their escaped versions
    escaped_content = pattern.sub(lambda match: html.escape(match.group(0)), html_content)
    return escaped_content

def decompose_element(soup, *args, **kwargs):
    """
    all parameters go to soup.find_all()
    returns new soup
    """
    elements=soup.find_all(*args, **kwargs)
    if len(elements)>0: 
        for e in elements:
            e.decompose()
    return soup

def filter_content(items):
    content = []
    p1 = re.compile(r'(.*)(to|will|date|schedule) (.*)results', re.IGNORECASE)
    p2 = re.compile(r'(.*)(schedule|schedules|announce|to) (.*)call', re.IGNORECASE)
    p3 = re.compile(r'(.*)release (.*)date', re.IGNORECASE)

    for item in items:
        title = item['title']
        if p1.match(title) or p2.match(title) or p3.match(title):
            content.append(item)
    return content

import os
import json
import re
import requests
class ContentBlocker:
    def __init__(self):
        """Loads the filtering rules on initialization."""
        if os.getenv('FLASK_ENV') == "development": 
            with open('rsshub/blocker.json', 'r') as file:
                self.rules = json.load(file)
        else:
            url = "https://raw.githubusercontent.com/superkeyor/rsshub_python/refs/heads/master/rsshub/blocker.json"
            response = requests.get(url, timeout=10) 
            response.raise_for_status() 
            self.rules = response.json()

    def match(self, text, specific_rules=None):
        """Returns True if the text hits any blocked regex rule in the provided list.
        e.g., blocker.match(post['author'], blocker.rules['xueqiu']['author'])
        """
        # Use the specific rules passed in, otherwise default to self.rules
        rules_to_check = specific_rules if specific_rules is not None else self.rules

        if not rules_to_check:
            return False 

        for rule in rules_to_check:
            if re.search(rule, text):
                return True
                
        return False