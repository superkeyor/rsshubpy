"""Shared helpers for spiders: HTML snippets, parse_each, blocklist. (Fetching: fetch.py, browser.py.)"""
import json
import logging
import os
import re
from pathlib import Path

import bs4
import requests

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent

def to_html(element):
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


def parse_each(parse, posts):
    """
    [parse(post) for post in posts], except that a post whose parse fails is logged and left out,
    so one broken or blocked page does not fail the whole feed.
    """
    items = []
    for post in posts:
        try:
            items.append(parse(post))
        except Exception:
            log.exception('%s: skipping %s', getattr(parse, '__module__', ''), getattr(post, 'get', lambda _: None)('href') or post)
    return items


def remove_tags(soup, *args, **kwargs):
    """
    Decompose every soup.find_all(*args, **kwargs) match.
    returns the same (modified) soup
    """
    for e in soup.find_all(*args, **kwargs):
        e.decompose()
    return soup


class Blocklist:
    """
    Regex rules per site and field, from blocker.json:
        {"xueqiu": {"author": [...], "title": [...], "content": [...]}, ...}
    Production loads the file fresh from GitHub on every call (edit it there, no rebuild needed) and falls
    back to the bundled copy if GitHub fails. Development uses the bundled copy.
    """
    URL = 'https://raw.githubusercontent.com/superkeyor/rsshubpy/refs/heads/master/app/blocker.json'
    LOCAL = HERE / 'blocker.json'

    def rules(self):
        if os.getenv('APP_ENV') != 'development':
            try:
                response = requests.get(self.URL, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                log.warning('blocklist: %s failed (%s), using the bundled copy', self.URL, e)
        return json.loads(self.LOCAL.read_text(encoding='utf-8'))

    def matcher(self, site):
        """Return is_blocked(author=, title=, content=) for one site, loading the rules once."""
        site_rules = self.rules().get(site, {})

        def is_blocked(**fields):
            return any(
                re.search(rule, text)
                for field, text in fields.items()
                for rule in site_rules.get(field, [])
            )
        return is_blocked


blocklist = Blocklist()
