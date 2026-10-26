"""
Feed registry. A spider declares its URL rule(s) next to its code:

    from feeds import feed

    @feed('/xueqiu/user/<id>', '/xueqiu/user/<id>/<category>')
    def ctx(id='', category='10'):
        '''First docstring line is shown on the index page.'''
        return {'title': ..., 'link': ..., 'description': ..., 'author': ..., 'items': [...]}

URL variables become keyword arguments; Python defaults cover the shorter rules.
main.py imports every module under spiders/ and turns each registered rule into a route.
"""
import ast
import inspect
import re
import sys
import threading
from dataclasses import dataclass
from functools import cache
from datetime import UTC, datetime
from typing import Callable

from flask import Response, render_template, request


@dataclass(frozen=True)
class Feed:
    rule: str
    func: Callable

    @property
    def module(self):
        return self.func.__module__.removeprefix('spiders.')

    @property
    def site(self):
        """The site = the spider's folder (spiders/<site>/...), e.g. 'fidelity' for both fidelity spiders."""
        return self.module.split('.')[0]

    @property
    def fetches(self):
        """How this feed's spider module loads pages (from its source code, see fetch_usage)."""
        return fetch_usage(self.func.__module__)

    @property
    def doc(self):
        lines = (self.func.__doc__ or '').strip().splitlines()
        return lines[0] if lines else ''


FEEDS: list[Feed] = []

# At most one spider per site runs at any time (any feed of that site, browser or plain HTTP, any trigger:
# reader, double request, cron refresh); the others wait for it.
_site_locks: dict[str, threading.Lock] = {}
_site_locks_guard = threading.Lock()


def site_lock(site: str) -> threading.Lock:
    with _site_locks_guard:
        return _site_locks.setdefault(site, threading.Lock())


def feed(*rules):
    """Register func under each URL rule. A rule may be used by one spider only."""
    def register(func):
        for rule in rules:
            if any(f.rule == rule for f in FEEDS):
                raise ValueError(f'feed rule {rule!r} is registered twice ({func.__module__})')
            FEEDS.append(Feed(rule, func))
        return func
    return register


FETCH_CALLS = ('fetch', 'collect_pages')   # calls that take via='requests' | 'browser'


def _calls(module_name):
    """(name, keywords) of every fetch/collect_pages/window call in a module's source code."""
    tree = ast.parse(inspect.getsource(sys.modules[module_name]))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', None)
            if name in FETCH_CALLS + ('window',):
                yield name, {k.arg: k.value for k in node.keywords}


@cache
def fetch_usage(module_name):
    """
    Summary of how a spider module loads pages: "requests", "browser" (fetch), "browser (pages)" (also
    threadcache.collect_pages), "window (cdp)", "window (uc)".
    Generated from the source, so the index page is always current.
    """
    by_via, windows = {}, []
    for name, kw in _calls(module_name):
        if name == 'window':
            uc = kw.get('uc')
            label = 'window (uc)' if isinstance(uc, ast.Constant) and uc.value else 'window (cdp)'
            if label not in windows:
                windows.append(label)
        else:
            via = kw.get('via')
            kinds = by_via.setdefault(via.value if isinstance(via, ast.Constant) else '?', [])
            kind = 'pages' if name == 'collect_pages' else 'fetch'
            if kind not in kinds:
                kinds.append(kind)
    parts = [f"{via} (pages)" if 'pages' in kinds else via for via, kinds in by_via.items()] + windows
    return ', '.join(parts) or 'none'


def apply_query_filters(ctx, args):
    """
    Filter ctx['items'] by query parameters (each a regex; "a|b" matches either):
    include_title, include_description, exclude_title, exclude_description, limit.
    """
    def keywords(name):
        value = args.get(name)
        return value.split('|') if value else None

    def matches(text, words):
        return any(re.search(word, text) for word in words)

    items = ctx['items'].copy()
    if words := keywords('include_title'):
        items = [item for item in items if matches(item['title'], words)]
    if words := keywords('include_description'):
        items = [item for item in items if matches(item['description'], words)]
    if words := keywords('exclude_title'):
        items = [item for item in items if not matches(item['title'], words)]
    if words := keywords('exclude_description'):
        items = [item for item in items if not matches(item['description'], words)]
    if limit := args.get('limit', type=int):
        items = items[:limit]
    return {**ctx, 'items': items}


def render_feed(ctx):
    """Render a spider's ctx as Atom, after the query-parameter filters."""
    # naive UTC; its str() format is part of fallback entry ids in atom.xml, keep it stable
    now = datetime.now(UTC).replace(tzinfo=None)
    xml = render_template('atom.xml', now=now, **apply_query_filters(ctx, request.args))
    return Response(xml, mimetype='application/xml')
