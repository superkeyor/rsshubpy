from feeds import feed
from fetch import fetch
from threadcache import collect_pages, forget_except
from utils import remove_tags, parse_each
import logging
from urllib.parse import urljoin
from datetime import datetime
import re

log = logging.getLogger(__name__)

# this is the one I use.
domain = 'https://www.1point3acres.com/'
headers = {
    "Host": "www.1point3acres.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7,zh-CN;q=0.3",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://www.1point3acres.com",
    "DNT": "1",
    "Sec-GPC": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1"
}

# Pages per thread: 0 = none | N = the first N pages | 'all' (hot threads: 1-18 pages, median 5).
# Originally only page 1 (`if p>1: break` in collect_all_pages). Thread pages are cached (threadcache): a later
# run downloads only pages of changed threads that can have changed (none once the first PAGES pages are full).
PAGES = 5

def next_url(soup, url):
    """The next page of a thread ("下一页", a.nxt), or None on the last page."""
    next_button = soup.find("a", attrs={'class': 'nxt'})
    if not next_button or not next_button.get("href"):
        return None
    next_page_url = next_button["href"]
    # Handle relative URLs (e.g., "/page/2")
    if not next_page_url.startswith(('http://', 'https://')):
        next_page_url = urljoin(url, next_page_url)
    return next_page_url

def thread_url(post):
    return urljoin(domain,'bbs/'+post.get('href'))

def signature(post):
    """Reply count + last post time from the listing row: changes with every reply."""
    row = post.find_parent('tr')
    replies = row.select_one('td.num a') if row else None
    last = row.select('td.by em span[title]') if row else []
    if not replies or not last:
        return None
    return f"{replies.get_text(strip=True)}@{last[-1]['title']}"

def total_pages(post):
    """The thread's page count from the listing's page links (span.tps), 1 if it has none."""
    numbers = [int(a.get_text()) for a in post.find_parent('th').select('span.tps a') if a.get_text().strip().isdigit()]
    return max(numbers, default=1)

def clean_and_combine_text(text):
    """
    Split text by <br> tags, remove empty lines, calculate average length,
    and combine with appropriate number of <br> tags.
    Args:
        text: HTML text containing <br> or <br/> tags
    Returns:
        Cleaned and combined text with <br> tags
    """
    import re
    # Split by both <br> and <br/>, remove any whitespace
    lines = re.split(r'<br\s*/?\s*>', text)
    # Keep only non-empty lines (strip whitespace first)
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    # If no lines, return empty string
    if not non_empty_lines:
        return ''
    # Calculate average length
    total_length = sum(len(line) for line in non_empty_lines)
    avg_length = total_length / len(non_empty_lines)
    # Combine with appropriate separator
    if avg_length > 22:
        result = '<br><br>'.join(non_empty_lines)
    else:
        result = '<br>'.join(non_empty_lines)
    return result

def parse(post):
    link=thread_url(post)
    log.info("%s", link)
    soups = collect_pages('acres', link, signature(post), next_url, via='browser', pages=PAGES,
                          pause=(10, 15))   # sleep between pages, as before
    if len(soups)==0: # could not retrieve page: skipped by parse_each (a placeholder item would get a new id every run)
        raise RuntimeError(f'could not retrieve {link}')
    contents=[]; thumbups=[]; thumbdowns=[]; authors=[]

    # p: page number
    for p, soup in enumerate(soups, start=1):
        # all posts in one page
        authis = soup.find_all('div',class_="authi")
        # print(soup)
        for authi in authis:
            author = authi.text.strip().split()[0]
            # anonymous or anonymous via app
            if "匿名用户" not in author: 
                author = authi.find('a').text
            authors.extend([author])
        
        if p==1: 
            try:
                pubDate=datetime.strptime(authis[0].find(itemprop="datePublished").get('content'), '%Y-%m-%d %H:%M')
            except:
                # anonymous
                try: 
                    pubDate=datetime.strptime(authis[0].find(id=re.compile('authorposton')).find('span').get('title'), '%Y-%m-%d %H:%M:%S')
                except:
                # anonymous via app
                    pubDate=datetime.strptime(authis[0].find(id=re.compile('authorposton')).text, '%Y-%m-%d %H:%M:%S')
        
        login_message=soup.find('div',class_="attach_nopermission")
        if login_message: login_message.decompose()

        imgtip=soup.find_all('div',class_="aimg_tip")
        if len(imgtip)>0:
            for tip in imgtip:
                tip.decompose()
            for div in soup.find_all('div', class_='mbn'):
                imgs = div.find_all('img')
                for img in imgs:
                    if img.has_attr('file'):
                        file_url = img['file']
                        img['src'] = file_url
                        del img['file']
        
        soup = remove_tags(soup, 'div',class_="quote")
        soup = remove_tags(soup, 'font',class_="jammer")
        soup = remove_tags(soup, 'i',class_="pstatus")
        soup = remove_tags(soup, 'div',style="display:none;")
        # soup = remove_tags(soup, 'span',style="display:none;")
        soup = remove_tags(soup, 'span')
        
        # contents.extend( soup.find_all('td',itemprop="articleBody") )
        contents.extend( soup.select('td[itemprop="articleBody"], div.locked') ) # sometimes locked contents
        thumbups.extend( [e.text for e in soup.find_all('i',id=re.compile(r'rec_add_\d+'))] )
        thumbdowns.extend( [e.text for e in soup.find_all('i',id=re.compile(r'rec_sub_\d+'))] )
    
    content=''
    op=authors[0]
    for i, a, c, u, d in zip(range(len(authors)), authors, contents, thumbups, thumbdowns):
        reaction = '&nbsp;&nbsp;&nbsp;&nbsp;'
        if int(u)>0: reaction += f" ↑{u}"
        if int(d)>0: reaction += f" ↓{d}"
        # c = str(c).replace("\n<br/>\r\n","")
        c=clean_and_combine_text(c.decode_contents().replace('\n', '').replace('\r', ''))
        c=c.replace("</ignore_js_op><br><br>", "</ignore_js_op><br>") # break after image
        if a==op: 
            content += f"#{i+1}: <i>{a} (op)</i> {reaction} <br>{c}<br><br>"
        else:
            content += f"#{i+1}: <i>{a}</i> {reaction} <br>{c}<br><br>"
    # originally always: <a href="{page 2}">更多原文</a> (only page 1 was read)
    total, shown = total_pages(post), len(soups)
    if total > shown:
        more = link.replace("-1-1.", f"-{shown + 1}-1.")
        rest = f'p. {total}' if total == shown + 1 else f'pp. {shown + 1}–{total}'
        content += f'<div align="right"><a href="{more}" target="_blank">{rest} →</a></div>'
    else:
        content += f'<div align="right"><a href="{link}" target="_blank">阅读原文</a></div>'
    
    item = {}
    item['title']=post.text
    item['link']=link
    item['author']=op
    item['pubDate']=pubDate
    item['id']=link  # do not add date to the link because date may be incorrect(?) causing rss duplication
    item['description']=content
    
    return item

@feed('/13')
def ctx(category=''):
    """1point3acres hot threads with replies (browser)."""
    urls=[urljoin(domain,'/bbs/forum.php?mod=guide&view=hot'), urljoin(domain,'/bbs/forum.php?mod=guide&view=digest')]
    urls=[urljoin(domain,'/bbs/forum.php?mod=guide&view=hot')]
    posts=[]
    
    for url in urls:
        soup = fetch(url, via='browser').soup
        
        for th in soup.find_all('th', attrs={'class':'common'}):
            if th.find('img', attrs={'alt':'heatlevel'}) or th.find('img', attrs={'alt':'digest'}):
                posts.append(th.find('a',attrs={'class':'xst'}))
    
    posts = list(dict.fromkeys(posts))  # unique list while preserving order
    
    # modify Dockerfile to increase timeout for gunicorn
    items = parse_each(parse, posts)
    forget_except('acres', [thread_url(post) for post in posts])
    
    return {
        'title': '一亩三分地',
        'link': domain,
        'description': '伴你一起成长',
        'author': 'Jerry',
        'items': items
    }
