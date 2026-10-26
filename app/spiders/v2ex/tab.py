from feeds import feed
from fetch import fetch
from threadcache import collect_pages, forget_except
from utils import parse_each
import logging
from datetime import datetime
import re
from urllib.parse import urlparse, urlunparse

log = logging.getLogger(__name__)

domain = 'https://www.v2ex.com'

def get_base_url(url):
    parsed_url = urlparse(url)
    base_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
    return base_url

def next_url(soup, url):
    """The next page of a topic (the "下一页" button), or None on the last page."""
    next_button = soup.find("td", attrs={'title': '下一页'})
    if not next_button:
        return None
    return next_button.get("onclick").replace("location.href='", get_base_url(url)).replace("';", "")

def reply_count(href):
    """Listing links end in "#reply<count>": the thread's signature (None without replies)."""
    match = re.search(r'#reply(\d+)', href)
    return match.group(1) if match else None

def parse(post):
    link, replies = post
    # pages are downloaded only when the reply count changed since the last run (threadcache)
    soups = collect_pages('v2ex', link, replies, next_url, via='requests', pages='all',
                          pause=(5, 10), topic_pause=1)   # sleeps: between pages / between topics, as before
    
    try:
        title=soups[0].select_one('.header h1').text
        author=soups[0].select_one('div.header > small > a').text
        pubDate=datetime.fromisoformat( soups[0].select_one('div.header > small > span').get('title') )
    except:
        return {'title': 'null',
                'link': link,
                'id': link,
                'author': 'null',
                'pubDate': datetime.now(),
                'description': ''}
    
    reply_list = []
    for soup in soups:
        reply_list.extend(soup.select('[id^="r_"]'))
    reply_content = ""
    for reply in reply_list:
        content = reply.select_one('.reply_content').decode_contents()
        author1 = reply.select_one('.dark').text
        if reply.select_one('.badge.op'):
            op = "(op)"
        else:
            op = "&nbsp;&nbsp;&nbsp;&nbsp;"
        no = reply.select_one('.no').text
        if reply.select_one('.small.fade'):
            heart = f"❤️{reply.select_one('.small.fade').text.strip()}"
        else:
            heart = ''
        reply_content += f"<p><div>#{no}: <i>{author1} {op}</i>&nbsp;&nbsp;&nbsp;&nbsp;{heart}</div><div>{content}</div></p>"

    content='<br><div>附言</div>'.join([d.decode_contents() for d in soups[0].select('div.topic_content')])  # topic body: first page
    content=f"#0: <i>{author} (op)</i><br>{content}<div>{reply_content}</div>"
    content+=f'<div align="right"><a href="{link}" target="_blank">阅读原文</a></div>'

    item = {}
    item['title']=title
    item['link']=link
    item['author']=author
    item['pubDate']=pubDate
    item['description']=content
    
    return item

@feed('/v2ex/tab/<category>')
def ctx(category=''):
    """V2EX tab (e.g. hot, tech), topics with all replies."""
    url = f"{domain}/?tab={category}"
    soup = fetch(url, via='requests').soup
    posts = soup.select('span.item_title > a')
    posts = [(f"{domain}{re.sub(r'#.*$', '', post.get('href'))}", reply_count(post.get('href'))) for post in posts]
    items = parse_each(parse, posts)
    forget_except('v2ex', [link for link, _ in posts])

    return {
        'title': 'V2EX',
        'link': domain,
        'description': '',
        'author': 'Jerry',
        'items': items
    }
