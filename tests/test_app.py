"""
Offline tests (no network, no Chrome). Run inside the image from the repo root:
    docker run --rm -v $PWD:/src -w /src rsshubpy:dev python -m unittest discover tests
"""
import json
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
os.environ['APP_ENV'] = 'development'

import browser  # noqa: E402
import fetch as fetchmod  # noqa: E402
import threadcache  # noqa: E402
import feedcache  # noqa: E402
import feeds  # noqa: E402
import main  # noqa: E402
import utils  # noqa: E402

# Feed URLs FreshRSS is subscribed to: must never change
LEGACY_RULES = {
    '/bloomberg/<category>': 'bloomberg.article',
    '/fidelity/<category>': 'fidelity.article',
    '/fidelity/market': 'fidelity.market',
    '/tldr/ai': 'tldr.ai',
    '/ymail/<category>': 'ymail.folder',
    '/13': 'acres.thread',
    '/newmitbbs': 'newmitbbs.home',
    '/v2ex/tab/<category>': 'v2ex.tab',
    '/xueqiu/hots': 'xueqiu.hots',
    '/xueqiu/user/<id>': 'xueqiu.user',
    '/xueqiu/user/<id>/<category>': 'xueqiu.user',
}

CTX = {
    'title': 'T', 'link': 'https://example.com/', 'description': 'D', 'author': 'A',
    'items': [
        {'title': 'apple pie', 'description': 'sweet', 'link': 'https://example.com/1',
         'pubDate': datetime(2026, 1, 2, 3, 4, 5), 'author': 'x'},
        {'title': 'banana', 'description': 'yellow', 'link': 'https://example.com/2',
         'pubDate': '2026-01-03T00:00:00', 'id': 'fixed-id', 'author': 'y'},
    ],
}


class TestRegistry(unittest.TestCase):
    def test_legacy_rules_registered(self):
        registered = {f.rule: f.module for f in feeds.FEEDS}
        self.assertEqual(registered, LEGACY_RULES)
        url_rules = {r.rule for r in main.app.url_map.iter_rules()}
        self.assertTrue(set(LEGACY_RULES) <= url_rules)

    def test_routes_resolve_to_spiders(self):
        adapter = main.app.url_map.bind('localhost')
        self.assertTrue(adapter.match('/fidelity/market')[0].startswith('fidelity.market:'))
        self.assertTrue(adapter.match('/fidelity/weekly')[0].startswith('fidelity.article:'))
        endpoint, args = adapter.match('/xueqiu/user/123')
        self.assertEqual(args, {'id': '123'})

    def test_duplicate_rule_raises(self):
        with self.assertRaises(ValueError):
            feeds.feed('/13')(lambda: None)

    def test_index_lists_all_rules(self):
        html = main.app.test_client().get('/').get_data(as_text=True)
        for rule in LEGACY_RULES:
            self.assertIn(rule.replace('<', '&lt;').replace('>', '&gt;'), html)


class TestRender(unittest.TestCase):
    def render(self, query=''):
        with main.app.test_request_context('/x' + query):
            return feeds.render_feed(CTX)

    def test_atom_and_ids(self):
        resp = self.render()
        self.assertEqual(resp.mimetype, 'application/xml')
        xml = resp.get_data(as_text=True)
        self.assertTrue(xml.startswith('<?xml'))
        # fallback id: link#pubDate with ' '->'T' and ':' removed (unchanged format)
        self.assertIn('<id>https://example.com/1#2026-01-02T030405</id>', xml)
        self.assertIn('<id>fixed-id</id>', xml)
        self.assertIn('<generator>RSSHub</generator>', xml)

    def test_query_filters(self):
        xml = self.render('?include_title=app|kiwi').get_data(as_text=True)
        self.assertIn('apple pie', xml)
        self.assertNotIn('banana', xml)
        xml = self.render('?exclude_description=sweet').get_data(as_text=True)
        self.assertNotIn('apple pie', xml)
        self.assertIn('banana', xml)
        xml = self.render('?limit=1').get_data(as_text=True)
        self.assertEqual(xml.count('<entry>'), 1)

    def test_failing_spider_is_502(self):
        def broken():
            raise ValueError('boom')
        view = main.make_view(feeds.Feed('/broken', broken))
        with main.app.test_request_context('/broken'), self.assertLogs('rsshubpy', 'ERROR'):
            resp = view()
        self.assertEqual(resp.status_code, 502)
        self.assertIn('boom', resp.get_data(as_text=True))


class TestFeedCache(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        cache_dir = Path(self.tmp.name)
        self.patches = [mock.patch.object(feedcache, 'CACHE_DIR', cache_dir),
                        mock.patch.object(feedcache, 'INDEX_FILE', cache_dir / 'index.json'),
                        mock.patch.dict(feedcache._index, clear=True)]
        for p in self.patches:
            p.start()
        self.calls = 0

        def spider():
            self.calls += 1
            if self.calls > 2:
                raise ValueError('site down')
            return {**CTX, 'title': f'build {self.calls}'}
        self.view = main.make_view(feeds.Feed('/fake', spider))

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def get(self, refresh=False, after=60):
        """Request /fake; after = seconds since the previous reader request (simulated)."""
        if (entry := feedcache._index.get('/fake?limit=5')) and not refresh:
            entry['requested'] -= after
        headers = {feedcache.REFRESH_HEADER: '1'} if refresh else {}
        with main.app.test_request_context('/fake?limit=5', headers=headers):
            return self.view()

    def test_first_request_builds_then_serves_copy(self):
        self.assertIn('build 1', self.get().get_data(as_text=True))
        self.assertIn('build 1', self.get().get_data(as_text=True))   # served from the copy
        self.assertEqual(self.calls, 1)
        self.assertEqual([u for u, _ in feedcache.entries()], ['/fake?limit=5'])

    def test_second_request_within_30s_rebuilds(self):
        self.get()
        self.get()                                                    # copy (previous request 60s ago)
        with self.assertLogs('feedcache', 'INFO'):
            self.assertIn('build 2', self.get(after=10).get_data(as_text=True))
        self.assertIn('build 2', self.get().get_data(as_text=True))   # the new copy
        self.assertEqual(self.calls, 2)

    def test_refresh_replaces_copy_and_failure_keeps_it(self):
        self.get()
        self.assertIn('build 2', self.get(refresh=True).get_data(as_text=True))
        self.assertIn('build 2', self.get().get_data(as_text=True))
        with self.assertLogs('rsshubpy', 'ERROR'):
            self.assertEqual(self.get(refresh=True).status_code, 502)
        self.assertIn('build 2', self.get().get_data(as_text=True))   # old copy kept
        self.assertIn('site down', dict(feedcache.entries())['/fake?limit=5']['error'])

    def test_same_fingerprint_keeps_copy(self):
        with self.assertLogs('feedcache', 'INFO'):
            self.assertEqual(feedcache.put('/f', 'v1', 'text A'), 'v1')
            self.assertEqual(feedcache.put('/f', 'v2', 'text A'), 'v1')   # same on-screen text: copy kept
        self.assertEqual(feedcache.put('/f', 'v3', 'text B'), 'v3')       # text changed: replaced
        self.assertEqual(feedcache.put('/f', 'v4'), 'v4')                 # no fingerprint: always replaced

    def test_one_spider_per_site_at_a_time(self):
        import threading
        import time as _time
        running = {'now': 0, 'max': 0}

        def make(name):
            def spider():
                running['now'] += 1
                running['max'] = max(running['max'], running['now'])
                _time.sleep(0.3)
                running['now'] -= 1
                return CTX
            spider.__module__ = f'spiders.samesite.{name}'   # two spiders of one site folder
            return main.make_view(feeds.Feed(f'/{name}', spider))

        def call(view, path):
            with main.app.test_request_context(path, headers={feedcache.REFRESH_HEADER: '1'}):
                view()
        threads = [threading.Thread(target=call, args=(make(n), f'/{n}')) for n in ('a', 'b')]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(running['max'], 1)

    def test_urls_never_dropped(self):
        self.get()
        feedcache._index['/fake?limit=5']['requested'] = 0               # nobody asked for ages
        self.assertEqual(feedcache.refresh_all(lambda uri: True), True)
        for _ in range(50):
            if not feedcache._refreshing.is_set():
                break
            __import__('time').sleep(0.05)
        self.assertEqual([u for u, _ in feedcache.entries()], ['/fake?limit=5'])

    def test_refresh_endpoint_only_local(self):
        client = main.app.test_client()
        self.assertEqual(client.post('/refresh', environ_base={'REMOTE_ADDR': '172.18.0.1'}).status_code, 403)
        with mock.patch.object(feedcache, 'refresh_all', return_value=True) as refresh_all:
            self.assertEqual(client.post('/refresh').status_code, 202)
        refresh_all.assert_called_once()


class TestFetch(unittest.TestCase):
    def test_via_is_required_and_checked(self):
        with self.assertRaises(TypeError):
            fetchmod.fetch('https://example.com')                      # no via
        with self.assertRaises(ValueError):
            fetchmod.fetch('https://example.com', via='curl')

    def test_requests_decodes_without_parsing(self):
        import warnings
        from types import SimpleNamespace

        def fake_session(body):
            res = SimpleNamespace(content=body, url='https://x/feed', raise_for_status=lambda: None)
            return lambda url: SimpleNamespace(get=lambda url, timeout: res)

        xml = '<?xml version="1.0" encoding="utf-8"?><rss><channel><title>市场</title></channel></rss>'
        with mock.patch.object(fetchmod, '_session', fake_session(xml.encode())), \
                warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            page = fetchmod.fetch('https://x/feed', via='requests')
            self.assertEqual(page.html, xml)                                  # text only: no HTML parser ran
        self.assertEqual([w for w in caught if 'XMLParsedAsHTML' in str(w.category)], [])

        gbk = '<html><head><meta charset="gbk"><title>中文标题</title></head><body>正文</body></html>'
        with mock.patch.object(fetchmod, '_session', fake_session(gbk.encode('gbk'))):
            page = fetchmod.fetch('https://x/page', via='requests')
        self.assertEqual((page.title, page.soup.body.get_text()), ('中文标题', '正文'))   # meta charset honoured

    def test_chromium_user_agent(self):
        ua = fetchmod.chromium_user_agent('Chromium 156.0.8078.47 built on Debian GNU/Linux 13 (trixie)')
        self.assertEqual(ua, 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                             'Chrome/156.0.0.0 Safari/537.36')

    def test_every_spider_states_via_literally(self):
        import ast
        import pkgutil
        import spiders
        checked = 0
        for m in pkgutil.walk_packages(spiders.__path__, 'spiders.'):
            for name, kw in feeds._calls(m.name):
                if name in feeds.FETCH_CALLS:
                    via = kw.get('via')
                    self.assertTrue(isinstance(via, ast.Constant) and via.value in fetchmod.VIAS,
                                    f'{m.name}: {name}() needs via=\'requests\' or \'browser\'')
                    checked += 1
        self.assertGreater(checked, 5)

    def test_fetch_usage_summary(self):
        self.assertEqual(feeds.fetch_usage('spiders.fidelity.market'), 'window (uc)')
        self.assertEqual(feeds.fetch_usage('spiders.acres.thread'), 'browser (pages)')
        self.assertEqual(feeds.fetch_usage('spiders.tldr.ai'), 'browser')
        self.assertEqual(feeds.fetch_usage('spiders.xueqiu.hots'), 'window (cdp)')
        self.assertIn('Fetches', main.app.test_client().get('/').get_data(as_text=True))


class TestThreadCache(unittest.TestCase):
    """collect_pages with a fake fetch: a thread whose pages are p1..pN (next link in each page)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(threadcache, 'CACHE_DIR', Path(self.tmp.name)),
                        mock.patch.object(threadcache, 'fetch', self.fake_fetch)]
        for p in self.patches:
            p.start()
        self.fetched = []
        threadcache._stats.clear()
        self.set_thread(3)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def set_thread(self, n, version='v1'):
        self.n, self.version = n, version

    def fake_fetch(self, url, via):
        from types import SimpleNamespace
        from bs4 import BeautifulSoup
        k = int(url.rsplit('p', 1)[1])
        nxt = f'<a id="next" href="https://t/p{k + 1}">next</a>' if k < self.n else ''
        html = f'<html><body><p>{url} {self.version}</p>{nxt}</body></html>'
        self.fetched.append(url)
        return SimpleNamespace(html=html, soup=BeautifulSoup(html, 'lxml'))

    @staticmethod
    def next_url(soup, url):
        a = soup.find('a', id='next')
        return a['href'] if a else None

    def collect(self, signature, pages='all'):
        self.fetched = []
        soups = threadcache.collect_pages('t', 'https://t/p1', signature, self.next_url, via='requests',
                                          pages=pages, pause=(0, 0))
        return [s.p.get_text() for s in soups]

    def test_full_then_unchanged(self):
        self.assertEqual(len(self.collect('3 replies')), 3)
        self.assertEqual(self.fetched, ['https://t/p1', 'https://t/p2', 'https://t/p3'])
        self.assertEqual(len(self.collect('3 replies')), 3)
        self.assertEqual(self.fetched, [])                                    # same signature: no download

    def test_changed_resumes_from_last_page(self):
        self.collect('a')
        self.set_thread(5, 'v2')
        texts = self.collect('b')
        self.assertEqual(self.fetched, ['https://t/p3', 'https://t/p4', 'https://t/p5'])
        self.assertEqual(texts[0], 'https://t/p1 v1')                         # full pages reused
        self.assertEqual(len(texts), 5)

    def test_no_signature_resumes(self):
        self.collect(None)
        self.collect(None)
        self.assertEqual(self.fetched, ['https://t/p3'])

    def test_cap_full_downloads_nothing(self):
        self.collect('a', pages=2)
        self.assertEqual(self.fetched, ['https://t/p1', 'https://t/p2'])
        self.set_thread(9)
        self.assertEqual(len(self.collect('b', pages=2)), 2)
        self.assertEqual(self.fetched, [])                                    # pages 1-2 full: nothing to do

    def test_stale_entry_full_download(self):
        self.collect('a')
        path = threadcache._path('t', 'https://t/p1')
        entry = json.loads(path.read_text())
        entry['full_at'] -= threadcache.FULL_REFRESH_HOURS * 3600 + 1
        path.write_text(json.dumps(entry))
        self.collect('a')
        self.assertEqual(len(self.fetched), 3)

    def test_summary_for_index(self):
        self.collect('a')
        with self.assertLogs('threadcache', 'INFO'):
            threadcache.forget_except('t', ['https://t/p1'])
        summary = threadcache.summaries()['t']
        self.assertEqual((summary['threads'], summary['full'], summary['pages']), (1, 1, 3))
        html = main.app.test_client().get('/').get_data(as_text=True)
        self.assertIn('Thread cache', html)

    def test_pages_zero_and_prune(self):
        self.assertEqual(self.collect('a', pages=0), [])
        self.assertEqual(self.fetched, [])
        self.collect('a')
        with self.assertLogs('threadcache', 'INFO'):
            threadcache.forget_except('t', [])
        self.assertFalse(threadcache._path('t', 'https://t/p1').exists())


class TestUserscripts(unittest.TestCase):
    def test_bundled_bloomberg_script(self):
        names = [s.name for s in browser.USERSCRIPTS]
        self.assertIn('bloomberg-paywall-bypass.user.js', names)
        script = browser.USERSCRIPTS[names.index('bloomberg-paywall-bypass.user.js')]
        self.assertTrue(script.matches('https://www.bloomberg.com/latest/markets-wrap'))
        self.assertTrue(script.matches('https://bloomberg.com/'))
        self.assertFalse(script.matches('https://example.com/bloomberg.com/'))
        self.assertNotIn('DOMContentLoaded', script.source)   # @run-at document-start: as is

    def test_unsupported_scripts_skipped(self):
        head = '// ==UserScript==\n// @match https://a.com/*\n{}// ==/UserScript==\n'
        with self.assertLogs('browser', 'WARNING'):
            self.assertIsNone(browser.parse_userscript('g', head.format('// @grant GM_xmlhttpRequest\n')))
        with self.assertLogs('browser', 'WARNING'):
            self.assertIsNone(browser.parse_userscript('r', head.format('// @require https://x/y.js\n')))
        script = browser.parse_userscript('ok', head.format('// @grant none\n'))
        self.assertIn('DOMContentLoaded', script.source)       # default run-at document-idle: wrapped
        self.assertTrue(script.matches('https://a.com/x'))


class TestHelpers(unittest.TestCase):
    def test_blocklist_local_in_development(self):
        is_blocked = utils.blocklist.matcher('newmitbbs')
        self.assertTrue(is_blocked(author='Highly', title='t', content='c'))
        self.assertFalse(is_blocked(author='someone', title='t', content='c'))

    def test_blocklist_falls_back_to_local(self):
        with mock.patch.dict(os.environ, {'APP_ENV': 'production'}), \
                mock.patch('utils.requests.get', side_effect=OSError('offline')), \
                self.assertLogs('utils', 'WARNING'):
            rules = utils.blocklist.rules()
        self.assertIn('xueqiu', rules)

    def test_ago(self):
        self.assertEqual([main.ago(s) for s in (5, 75, 7300, 200000, None)], ['5s', '1m', '2h', '2d', '-'])

    def test_driver_needs_uc_window(self):
        page = browser.Page(None, None, [], False, 0, 0, None)
        with self.assertRaisesRegex(browser.BrowserError, 'uc=True'):
            page.driver

    def test_site_key_and_classify(self):
        self.assertEqual(browser._site_key('https://www.xueqiu.com/u/1'), 'xueqiu.com')
        self.assertIsNone(browser._warm_target('http://192.168.1.2:1200/x'))
        self.assertEqual(browser._classify_page('Just a moment...', ''), 'challenge')
        self.assertEqual(browser._classify_page('Hi', '<html>ok</html>'), 'ok')


if __name__ == '__main__':
    unittest.main()
