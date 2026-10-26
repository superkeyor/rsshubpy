import os, sys
exec("try:HERE=os.path.dirname(os.path.abspath(__file__));_=sys.path.remove(HERE) if HERE in sys.path else 0;sys.path.insert(0,HERE)\nexcept:HERE=os.getcwd()") # HERE for interactive run
DEBUG=os.getenv('APP_ENV')=='development'

import importlib
import logging
import pkgutil
import time

from flask import Flask, Response, render_template, request

import feedcache
import threadcache
import spiders
import feeds
from feeds import FEEDS, render_feed

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('rsshubpy')
# SeleniumBase's CDP tables predate some events Chrome sends after Page.enable; it logs each as a traceback
logging.getLogger('uc.connection').setLevel(logging.WARNING)


def load_spiders():
    """Import every module under spiders/ so their @feed rules register. A broken spider stops startup."""
    for module in pkgutil.walk_packages(spiders.__path__, 'spiders.'):
        importlib.import_module(module.name)


def make_view(f):
    """
    Serve the saved copy of this exact URL (feedcache); run the spider for a URL seen for the first time,
    a second request within feedcache.RECHECK_SECONDS, or cron's refresh (REFRESH_HEADER).
    A failed rebuild keeps the old copy.
    """
    def view(**kwargs):
        uri = request.full_path.removesuffix('?')
        refresh = request.headers.get(feedcache.REFRESH_HEADER) == '1'
        if not refresh and (xml := feedcache.get(uri)) is not None:
            return Response(xml, mimetype='application/xml')
        lock = feeds.site_lock(f.site)
        if not lock.acquire(blocking=False):
            log.info('feed %s waits: another %s spider is running', uri, f.site)
            lock.acquire()
        start = time.monotonic()
        try:
            ctx = f.func(**kwargs)
            resp = render_feed(ctx)
        except Exception as e:
            log.exception('feed %s (%s) failed', uri, f.module)
            feedcache.note_error(uri, repr(e))
            return Response(f'feed {uri} ({f.module}) failed: {e!r}\n', status=502, mimetype='text/plain')
        finally:
            lock.release()
        seconds = time.monotonic() - start
        log.info('feed %s built in %.0fs', uri, seconds)
        xml = feedcache.put(uri, resp.get_data(as_text=True), ctx.get('fingerprint'), seconds)
        return Response(xml, mimetype='application/xml')
    return view


def refresh_one(uri):
    """Rebuild one cached feed in-process (used by the cron-triggered refresh)."""
    resp = app.test_client().get(uri, headers={feedcache.REFRESH_HEADER: '1'})
    return resp.status_code == 200


def ago(seconds):
    """Compact age for the index page: 45s, 12m, 3h, 2d ('-' when unknown)."""
    if not isinstance(seconds, (int, float)):
        return '-'
    for unit, size in (('d', 86400), ('h', 3600), ('m', 60)):
        if seconds >= size:
            return f'{int(seconds // size)}{unit}'
    return f'{int(seconds)}s'


def create_app():
    app = Flask(__name__)
    app.jinja_env.filters['ago'] = ago
    load_spiders()
    for f in FEEDS:
        app.add_url_rule(f.rule, endpoint=f'{f.module}:{f.rule}', view_func=make_view(f))

    @app.route('/')
    def index():
        # grouped by how they fetch (browser, requests, window ...), then by route
        html = render_template('index.html', feeds=sorted(FEEDS, key=lambda f: (f.fetches, f.rule)),
                               cached=feedcache.entries(), threads=threadcache.summaries(), now=time.time())
        return Response(html, headers={'Cache-Control': 'no-store'})   # live status: never a stale copy

    @app.post('/refresh')
    def refresh():
        """Cron (crontab) calls this at minutes 15 and 45; only from inside the container."""
        if request.remote_addr not in ('127.0.0.1', '::1'):
            return Response('forbidden\n', status=403, mimetype='text/plain')
        started = feedcache.refresh_all(refresh_one)
        return Response('refresh started\n' if started else 'refresh already running\n',
                        status=202 if started else 409, mimetype='text/plain')

    return app


app = create_app()

if __name__ == "__main__":
    # default port 5000; not use 80, otherwise browser switches to https
    # for production, this would not run (gunicorn imports app)
    app.run(host="0.0.0.0", port=5000, debug=DEBUG, threaded=True)
