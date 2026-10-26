import json
import re

domain = 'https://xueqiu.com'


def avg_text_len_between_br(content):
    """
    Calculate average visible text length between <br> tags.
    For easier reading: if average text segment between <br> tags is long enough, double all single <br>.
    """
    segments = re.split(r'<br\s*/?\s*>', content)
    if len(segments) > 1:
        visible_lengths = [len(re.sub(r'<[^>]+>', '', seg)) for seg in segments]
        return sum(visible_lengths) / len(visible_lengths)
    return 0


# Body text of a JSON response page (Chrome shows it in a <pre>)
_BODY_TEXT_JS = "(() => { const pre = document.querySelector('pre'); return (pre || document.body || {}).innerText || ''; })()"


def load_json(page, url, cookie_url):
    """
    Open a xueqiu JSON API url in page (a browser window) and return the parsed data. Xueqiu answers with an
    "error_code" JSON until its session cookie is set; then visit cookie_url (sets it), wait, and try again
    (longer each time).
    """
    error = None
    for pause in (0, 5, 20):
        if pause:
            page.open(cookie_url)
            page.sleep(pause)
        page.open(url)
        try:
            data = json.loads(page.js(_BODY_TEXT_JS))
        except ValueError as e:
            error = e
            continue
        if 'error_code' not in data:
            return data
        error = data
    raise RuntimeError(f'xueqiu: no data from {url}: {error}')
