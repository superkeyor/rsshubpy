# rsshubpy: guide for coding agents

User-facing docs (routes, running, settings, adding a feed) are in [README.md](README.md). This file holds
design notes and rules for changing the code.

## Rules

- **Feed URLs and Atom entry ids are a contract**: FreshRSS is subscribed to the routes. Never rename a
  route, and never change how a spider builds `link`, `id` or `pubDate` (the fallback id in
  `app/templates/atom.xml` is `link#pubDate`). Keep `atom.xml` output byte-compatible.
- Do not change spider parsing behavior, pubDates or polite `sleep`s unless asked.
- Do not run `./upload` unless asked (it commits, pushes and publishes the image).
- Dependencies: direct ones only, pinned in `environment.yml`, versions taken from the user's tested set.

## Layout

- `app/main.py`: Flask app. Imports every module under `app/spiders/` (`pkgutil.walk_packages`), adds a URL
  rule per `@feed`, serves `/` as the generated index. A failing spider returns a plain-text 502 and logs
  the traceback; a spider that fails to import stops startup.
- `app/feedcache.py`: last-copy cache per request URI (path + query) in `app/cache/feeds/`. Feed views
  serve the copy; the spider runs on a URI's first request or when the request carries
  `X-Feed-Refresh: 1`. A spider may return `ctx['fingerprint']`; an unchanged fingerprint keeps the saved
  copy (fidelity/market: on-screen text of its screenshots). `POST /refresh` (localhost only; `crontab` at minutes 15 and 45 via wget) rebuilds all
  remembered URIs in a background thread (`REFRESH_WORKERS` at once, in-process `app.test_client()`
  requests). A second reader request for a URI within `RECHECK_SECONDS` rebuilds it live. A failed rebuild
  keeps the copy and records the error. URIs are never dropped automatically. Cron must go through HTTP:
  only the server process may own Chrome.
- `app/feeds.py`: `@feed(*rules)` registry (duplicate rule = error), query filters, Atom rendering,
  `site_lock`: **at most one spider per site at any time** (site = the folder under `spiders/`), for every
  feed and every trigger (reader, double request, cron refresh). `main.make_view` holds it while the spider
  runs; others of that site wait. Keep one folder per site so the rule holds.
- `app/fetch.py`: `fetch(url, via='requests'|'browser')` (required `via`): one requests session per host with
  the real Chromium user agent (from `chromium --version`), or a browser window; same `Fetched` result.
  The session lives for the whole process (keep-alive, cookies persist across runs and cron refreshes) and
  is shared by every `via='requests'` fetch of that host: listing, topic pages and `collect_pages` alike. It
  is not thread-safe in general; the per-site spider lock guarantees one user per host at a time.
  `collect_pages` has no fetch method of its own: it passes the spider's `via` to `fetch()` (v2ex and
  newmitbbs: requests session; acres: a browser window, no session). Saved thread pages are read from disk.
  `utils.Blocklist` (GitHub `blocker.json`) is the one place that uses a plain `requests.get`.
- `app/threadcache.py`: `collect_pages(site, url, signature, next_url, via=, pages=)` for forum threads, shared
  by v2ex/newmitbbs/acres. Saves page HTML in `cache/threads/<site>/`; same listing signature = no download;
  changed = resume at the saved last page (within the `pages` cap; cap full = nothing); full re-download after
  `FULL_REFRESH_HOURS` (24). `forget_except(site, urls)` once per run prunes and logs the summary.
  Signatures: v2ex reply count (`#replyN`), newmitbbs last post id (not the replier's name), acres reply count
  + last post time.
- Index page `/`: routes (with a generated "Fetches" column), cached feeds (changed / built / build time /
  items / last read / error; `feedcache` stores `build_s`, `entries`), thread cache (each forum's last run, from
  `threadcache.summaries()`, saved in `cache/threads/summary.json`).
- `feeds.fetch_usage`: scans spider source (ast) for fetch/collect_pages/window calls; index "Fetches" column;
  a unit test requires a literal `via` in every fetch/collect_pages call.
- `app/utils.py`: `to_html`, `remove_tags`, `parse_each` (skip a failing post
  instead of failing the feed), `blocklist`.
- `app/browser.py`: the Chrome manager (below). Public: `window` (yields a `Page`), `BrowserError`.
- `app/userscripts/`: `*.user.js` injected via `Page.addScriptToEvaluateOnNewDocument`.
- `Dockerfile` (`FROM superkeyor/chromiumkit` + Miniforge, as in sibling `dockerapp_template`), `start.sh`
  (`vnc-start`, then Flask dev server or gunicorn), `docker-compose.yml` + dev override, `upload`.
- `tests/test_app.py`: offline unittest (no network, no Chrome).

## Browser manager (`app/browser.py`)

- **One Chrome for the process lifetime.** A daemon thread launches it lazily on the first browser request:
  `SB(uc=True, headed=True, ...)` + `activate_cdp_mode("about:blank")`, then runs SeleniumBase's CDP event
  loop (`sb.cdp.get_event_loop()`) forever. Jobs use the async `cdp_driver` objects
  (`sb.driver.cdp_base.get(url, new_window=True)`, async `Tab`s), submitted from Flask threads with
  `asyncio.run_coroutine_threadsafe`. Never call the sync `sb.*`/`sb.cdp.*` API from jobs: its "current tab"
  is process-wide and its sync calls run `run_until_complete` on the already running loop.
- **One process only.** gunicorn runs `--workers 1 --threads 8`: Chrome locks its profile, so a second
  worker (or a second Python process using `browser.py` on the same profile, e.g. a `docker exec` script)
  would fail. Test scripts use their own container and `CHROME_USER_DATA_DIR`.
- **Concurrency** (asyncio primitives in the loop, no `threading.Lock`): per-site `asyncio.Lock` (key = host
  without `www.`), then `asyncio.Semaphore(MAX_WINDOWS)`; each job gets a new *window* (a tab hidden behind
  another renders nothing, so screenshots/scrolls hang), closed in `finally`.
- **Warm-up and memory** (ported from sibling `sbfetcher/server.py`): before a job, a new host or one whose
  last load ended `challenge`/`blocked` (`_classify_page`) gets its site root visited in the job's window
  (`_warm_url`: bot-check wait, native `tab.solve_captcha()`, human-like scrolling). Results are kept in
  `rsshub-hosts.json` in the profile. `page.open` records every load.
- **Dead Chrome**: before each job the caller pings Chrome (`Browser.getVersion`, 5 s). If it does not
  answer, the loop is stopped, `SB.__exit__` cleans up, and the thread relaunches; the call then proceeds.
  A job that loses Chrome mid-way fails with `BrowserError` and triggers the relaunch. No `pkill` in code;
  tini reaps zombies; the fixed compose `hostname` keeps the profile lock valid across containers.
- **Spider API** (all synchronous): `with window(url) as page:` opens a new Chrome window (never shared),
  closed when the block ends, also on errors. `page.open(url)` (load, readyState complete, bot check,
  warm-up memory), `page.wait(selector)`, `page.sleep(s)`, `page.html()`, `page.soup()`, `page.title`,
  `page.url`, `page.js(script)`, `page.screenshot(selector)` (CDP, base64). Each call runs one CDP step on
  the loop (`_Chrome.guarded_call`: a dead Chrome fails the step with `BrowserError` and triggers a relaunch).
- **`window(url, uc=True)`**: also `page.driver`, the Selenium WebDriver for the same window, so a spider
  switches freely between CDP and UC like SeleniumBase's `sb.cdp.open` / `sb.connect` / `sb.driver`.
  `page.driver` reconnects WebDriver on first use (`sb.connect()`, switch to the window); `page.open()`
  disconnects it before navigating. Exclusive (all window slots; uc windows queue FIFO), because WebDriver's
  current window is process-wide. With WebDriver use `driver.*`; `sb.open()` swaps to CDP and disconnects
  WebDriver (verified); never `sb.cdp.*` (its loop runs in another thread). fidelity/market uses it: CDP
  navigation, native `screenshot_as_base64`, element text as the feed-cache fingerprint.
- **Profile trim**: at thread start, before Chrome runs, cache folders are deleted if the profile exceeds
  `PROFILE_MAX_MB`; cookies, storage, extensions and `rsshub-hosts.json` are never deleted.

### Gotchas

- `tab.get()` has no timeout: always `asyncio.wait_for`. It can also return while the document is still
  streaming (verified: half a JSON body), so `page.open` waits for `document.readyState == "complete"`.
  Prefer `page.open` + `page.wait` over fixed sleeps.
- Userscripts only run after `Page.enable` (verified); `_open_window` sends it when a script matches.
- Never add placeholder items with a changing `pubDate` and no `id` (e.g. "timeout"): with the 30-minute
  refresh they become duplicate entries. Raise instead; `parse_each` skips the post.
- `headed=True` is required, or SeleniumBase starts its own Xvfb; check `pgrep -a Xvfb` shows only `:99`.
- arm64: SeleniumBase downloads an x86 chromedriver; the Dockerfile symlinks Debian's into its `drivers/`.
- Element screenshots: clip = element rect + `window.scrollX/scrollY` (page coordinates), with
  `capture_beyond_viewport=True`; otherwise right size, wrong place.
- `tab.evaluate("(async()=>{...})()", await_promise=True)` for promises; wrap multi-line scripts in a function.
- Chrome writes cookies lazily (~30 s): stopping right after a warm-up can lose them (atexit stops Chrome).

## Developing and testing

Use the remote docker host: `ssh orb` (Debian arm64, same files at `~/rsshubpy`).

```bash
ssh orb 'cd ~/rsshubpy && docker build -t rsshubpy:dev . && docker compose up -d'   # dev override: ./app hot reload
ssh orb 'cd ~/rsshubpy && docker run --rm -v $PWD:/src -w /src rsshubpy:dev python -m unittest discover tests'
uvx pyflakes app tests
```

Check real feeds with `curl` against `localhost:11201` and parse them with feedparser; for the browser,
watch noVNC on `:11202` and look at screenshots (hidden-window bugs only show in images).
