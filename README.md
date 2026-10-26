# rsshubpy

Personal RSS feeds generated in Python (Flask), originally forked from
[RSSHub-python](https://github.com/alphardex/RSSHub-python). Sites that block plain HTTP clients are fetched
with one long-lived, headed Chromium (SeleniumBase UC + CDP mode) inside the container.

Built on [chromiumkit](https://hub.docker.com/r/superkeyor/chromiumkit) (Debian Chromium + Xvfb + noVNC)
and laid out like `dockerapp_template`. Design notes for contributors and coding agents: [AGENTS.md](AGENTS.md).

## Feeds

Open `http://<host>:11201/` for the generated list of routes. Current routes:

| Route | Source |
|---|---|
| `/13` | 1point3acres hot threads with replies |
| `/bloomberg/wrap` | Bloomberg Markets Wrap |
| `/fidelity/weekly`, `/fidelity/quarterly`, `/fidelity/ideas` | Fidelity market updates |
| `/fidelity/market` | Fidelity research screenshots |
| `/newmitbbs` | newmitbbs popular + recommended topics |
| `/tldr/ai` | TLDR AI newsletter |
| `/v2ex/tab/<tab>` | V2EX tab, e.g. `hot` |
| `/xueqiu/hots`, `/xueqiu/user/<id>[/<category>]` | Xueqiu hot posts / user timeline |
| `/ymail/<folder>` | Yahoo mail folder (via RSSHub's IMAP route) |

Readers get the **last saved copy** of each feed URL, so requests are instant. Cron rebuilds every saved
URL at minutes 15 and 45 of each hour (`crontab` → `POST /refresh`, allowed from inside the container only).
A failed rebuild keeps the previous copy. The spider runs live only for the first request of a new URL, or
when the same URL is requested **twice within 30 seconds** (open it twice to get the latest right away).
Saved URLs are never dropped automatically. The index page lists them with their age and last error.
Copies live in `app/cache/feeds/` (bind-mounted in production). At most one spider per site runs at a time
(site = folder under `app/spiders/`); a second feed of the same site waits for the first.

Every feed accepts these query parameters (regex; `a|b` matches either):
`include_title`, `include_description`, `exclude_title`, `exclude_description`, `limit`.
Example: `/xueqiu/hots?exclude_title=广告|推广&limit=5`.

Posts on newmitbbs and xueqiu are filtered by [app/blocker.json](app/blocker.json). Production reads it from
GitHub on every request, so an edit on GitHub takes effect without a rebuild.

## Add a feed

Create one file under `app/spiders/<site>/<name>.py` (one folder per site: spiders of the same folder never
run at the same time); nothing else needs registering:

```python
from feeds import feed
from fetch import fetch

@feed('/example/<category>')
def ctx(category='news'):
    """One line shown on the index page."""
    soup = fetch(f'https://example.com/{category}', via='requests').soup   # or via='browser' (real Chrome)
    return {
        'title': 'Example', 'link': 'https://example.com', 'description': '', 'author': 'Jerry',
        'items': [{'title': ..., 'link': ..., 'pubDate': ..., 'description': ..., 'author': ...}],
    }
```

`fetch(url, via=...)` returns `.soup`, `.html`, `.url`, `.title`; `via` is required: `'requests'` (plain
HTTP, the real Chromium user agent) or `'browser'` (a real Chrome window). The index page's "Fetches" column
shows what each spider uses (generated from the code).

For multi-step browser work (waits, clicks, screenshots, WebDriver) use a window directly:

```python
from browser import window

with window(url) as page:                 # its own Chrome window, closed after the block
    page.open(url)
    page.wait('article')                  # wait for an element instead of a fixed sleep
    soup = page.soup()

with window(url, uc=True) as page:        # + page.driver: Selenium WebDriver (UC) for the same window
    page.open(url)
    png = page.driver.find_element('css selector', '.chart').screenshot_as_base64
```

Forum threads (pages that grow with replies): `threadcache.collect_pages(site, url, signature, next_url,
via=..., pages=...)` returns the page soups but downloads only what changed since the last run (`signature`:
something from the listing that changes with every reply; `pages`: `0`, a number, or `'all'`). See
`spiders/v2ex/tab.py`.

URL variables become keyword arguments. An item may set `id`; otherwise the Atom entry id is built from
`link` and `pubDate`, so keep both stable or readers will see duplicates.

## Run

```bash
docker compose up -d        # with docker-compose.override.yml present: dev mode (see below)
docker logs -f rsshubpy
```

- Production (`docker-compose.yml` only): gunicorn on host port **11201**. The Chrome profile and the
  content cache are bind-mounted from `/dataguardian/nodata/rsshubpy/`.
- Development (`docker-compose.override.yml`, image `rsshubpy:dev`): Flask dev server with hot reload of
  `./app`, profile and cache in `app/chromiumprofile` / `app/cache` (gitignored), and the noVNC viewer on
  **11202**.

Build the dev image with `docker build -t rsshubpy:dev .`. `./upload` commits, pushes to GitHub, and builds and
pushes `superkeyor/rsshubpy` to Docker Hub.

### Watching or setting up Chrome (noVNC)

With `ENABLE_VNC=true`, open `http://<host>:11202/` to watch the browser windows and click or type in them,
for example to log in to a site or install an extension. Everything lands in the persistent profile. Anyone
who can reach that port controls the browser; set `VNC_PASSWORD` if it is not private.

### Settings

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `production` | `development` = Flask dev server, local `blocker.json` |
| `MAX_WINDOWS` | `3` | Chrome windows at once (one per site; more requests wait) |
| `PROFILE_MAX_MB` | `2000` | At start, delete the profile's cache folders if it is bigger (cookies are kept); `0` = never |
| `LOG_LEVEL` | `INFO` | Python log level |
| `ENABLE_VNC`, `VNC_PASSWORD`, `SCREEN_GEOMETRY` | from chromiumkit | noVNC viewer and Xvfb size |

### Userscripts

`app/userscripts/*.user.js` are injected into matching pages without a userscript manager (currently the
[Bloomberg paywall bypass](https://greasyfork.org/en/scripts/598567)). Only scripts with `@grant none` and no
`@require` are supported; others are skipped with a warning in the log, and need a userscript manager
installed in the profile via noVNC.
