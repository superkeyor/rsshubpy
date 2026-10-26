from feeds import feed
from fetch import fetch
from threadcache import collect_pages, forget_except
from utils import blocklist, parse_each
import logging
from urllib.parse import urljoin, urlparse
from datetime import datetime
import re

log = logging.getLogger(__name__)

domain = 'https://newmitbbs.com'

def update_iframes(tag, soup):
    for iframe in tag.find_all('iframe'):
        src = iframe.get('src', '')

        # YouTube: replace with clickable thumbnail
        # https://newmitbbs.com/viewtopic.php?p=7126239
        if 'youtube' in src:
            vid_match = re.search(r'/embed/([A-Za-z0-9_-]+)', src)
            video_id = vid_match.group(1) if vid_match else ''
            style = iframe.get('style', '')
            bg_match = re.search(r'background:\s*url\(([^)]+)\)', style)
            thumb_url = bg_match.group(1) if bg_match else f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
            watch_url = f'https://www.youtube.com/watch?v={video_id}'
            wrapper = soup.new_tag('span')
            link_tag = soup.new_tag('a', href=watch_url, target='_blank')
            link_tag.string = watch_url
            wrapper.append(link_tag)
            wrapper.append(soup.new_tag('br'))
            a_tag = soup.new_tag('a', href=watch_url, target='_blank')
            img_tag = soup.new_tag('img', src=thumb_url, width='390')
            a_tag.append(img_tag)
            wrapper.append(a_tag)
            iframe.replace_with(wrapper)
            continue

        # Twitter: replace with a plain link
        # https://newmitbbs.com/viewtopic.php?t=982181
        if 'twitter' in src:
            fragment = urlparse(src).fragment
            tweet_id = re.sub(r'\D', '', fragment)
            tweet_url = f'https://twitter.com/i/status/{tweet_id}'
            a_tag = soup.new_tag('a', href=tweet_url, target='_blank')
            a_tag.string = 'Tweet Post'
            iframe.replace_with(a_tag)
            continue

        # Other iframes: keep as-is

def next_url(soup, url):
    """The next page of a topic (rel="next"), or None on the last page."""
    next_button = soup.find("a", attrs={'rel': 'next'})
    if not next_button or not next_button.get("href"):
        return None
    next_page_url = next_button["href"]
    # Handle relative URLs (e.g., "/page/2")
    if next_page_url.startswith("/") or next_page_url.startswith("./"):
        next_page_url = urljoin(url, next_page_url)
    return next_page_url

def last_post_id(post):
    """
    The listing row's "最新回复" link ends in "&p=<last post id>": the thread's signature. A post id, not the
    replier's name: the same person replying again still makes a new id. (An edit of the last post keeps the
    id; the daily full refresh in threadcache picks that up.)
    """
    row = post.find_parent('li')
    match = re.search(r'[?&;]p=(\d+)', str(row)) if row else None
    return match.group(1) if match else None

def thread_url(post):
    return re.sub( '&sid=.*$','', urljoin(domain,post.get('href')) )

def parse(post):
    link=thread_url(post)
    # pages are downloaded only when the last post changed since the last run (threadcache)
    soups = collect_pages('newmitbbs', link, last_post_id(post), next_url, via='requests', pages='all',
                          pause=(5, 10), topic_pause=1)   # sleeps: between pages / between topics, as before
    contents=[]; authors=[]

    for n, soup in enumerate(soups, start=1):
        # "fix" emoji
        emoji_elements = soup.find_all('img', class_='emoji smilies')
        for emoji in emoji_elements:
            # if 'src' in emoji.attrs:
            #     del emoji['src']
            emoji["width"] = "18px"; emoji["height"] = "18px"
        # "fix" blockquote
        for b in soup.find_all('blockquote'):
            b.decompose()

        # contents.extend(soup.find_all('div',class_="content"))
        for content_div in soup.find_all('div', class_="content"):
            for p in content_div.find_all('p'):
                p.insert_after(soup.new_tag('br')) 
                p.insert_after(soup.new_tag('br')) # convert p to two br
                p.unwrap()
            update_iframes(content_div, soup)
            contents.append(content_div.decode_contents().replace('\n', '').strip())
        # username-coloured for admin
        authors.extend([u.find('span',class_=["username", "username-coloured"]).text for u in soup.find_all('div',class_="postbody")])
    
    content=''; op=authors[0]
    for i, a, c in zip(range(len(authors)), authors, contents):
        if a==op:
            content += f"#{i+1}: <i>{a} (op)</i> <br>{c}"
        else:
            content += f"#{i+1}: <i>{a}</i> <br>{c}"
    content += f'<div align="right"><a href="{link}" target="_blank">阅读原文</a></div>'
    
    item = {}
    item['title']=post.text
    item['link']=link
    item['author']=op
    item['pubDate']=datetime.fromisoformat( soups[0].find('time').get('datetime') )
    item['description']=content
    
    return item

@feed('/newmitbbs')
def ctx(category=''):
    """newmitbbs popular + recommended topics, with replies (blocker.json filters)."""
    soup = fetch(domain, via='requests').soup
    
    pop = soup.find('div',attrs={'id':'popular-topics-box'}).find_all('a',attrs={"class":"topictitle"})
    rec = soup.find('div',attrs={'id':'recent-recommended-topics-box'}).find_all('a',attrs={"class":"topictitle"})
    posts = list(dict.fromkeys(pop + rec))  # unique list while preserving order
    
    links = [thread_url(post) for post in posts]
    posts = parse_each(parse, posts)
    forget_except('newmitbbs', links)
    is_blocked = blocklist.matcher('newmitbbs')
    filtered_posts = []
    for post in posts:
        if not is_blocked(author=post['author'], title=post['title'], content=post['description']):
            post['title'] = f"{post['author']}: {post['title']}"
            filtered_posts.append(post)

    return {
        'title': '新未名空间',
        'link': domain,
        'description': '一个海外华人中文交流的论坛',
        'author': 'Jerry',
        'items': filtered_posts
    }

