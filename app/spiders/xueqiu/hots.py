from datetime import datetime, timezone
from bs4 import BeautifulSoup
from feeds import feed
from browser import window
from utils import blocklist
from spiders.xueqiu.common import domain, avg_text_len_between_br, load_json
import random
import re

from opencc import OpenCC
cc = OpenCC('t2s')  # t2s = Traditional to Simplified

# https://github.com/DIYgod/RSSHub/blob/master/lib/routes/xueqiu/hots.ts

@feed('/xueqiu/hots')
def ctx(category=''):
    """Xueqiu hot posts of the day (blocker.json filters)."""
    url1 = f"{domain}" # set cookie first
    url2 = f"{domain}/statuses/hots.json?a=1&count=10&page=1&scope=day&type=status&meigu=0"

    # originally a fixed 30s dwell after each page:
    # soups, sources, urls, titles = fetch_by_browser([url1, url2], wait=30)
    # items=json.loads(soups[1].text)
    # now: dwell a few seconds on the home page, then read the JSON as soon as it is complete
    # (load_json retries with longer dwells, 5s then 20s, if xueqiu answers with an error)
    with window(url1) as page:
        page.open(url1)   # sets the session cookie
        page.sleep(random.uniform(4, 8))
        items = load_json(page, url2, cookie_url=url1)
    
    is_blocked = blocklist.matcher('xueqiu')
    posts = []
    for item in items:
        post={}

        post['author'] = cc.convert(item['user']['screen_name'])
        post['link'] = f"{domain}{item['target']}"
        post['id'] = post['link']
        post['pubDate'] = datetime.fromtimestamp(item['created_at'] / 1000, timezone.utc).isoformat()  # created_at: epoch ms (same string as arrow.get(...).isoformat())
        
        content = cc.convert(item['text'])
        if avg_text_len_between_br(content) > 22:
            content=re.sub(r'<br\s*/?\s*>(?!<br)', '<br><br>', content) # easier reading
        # 回复<a href="https://xueqiu.com/n/持股待涨养家糊口" target="_blank">@持股待涨养家糊口</a>: 
        content=re.sub(r'回复<a href="https://xueqiu\.com/n/[^"]*"[^>]*>@[^<]*</a>:\s*', '', content)
        content=re.sub(r'//<a href="https://xueqiu\.com[^"]*"[^>]*>(@[^<]*)</a>:', r'//\1<br>', content)
        content = re.sub(r'<a href="https://xueqiu\.com/(?:[nS]/|k\?q=)[^"]*"[^>]*>([^<]*)</a>', r'\1', content)

        title=content.split("//@")
        if len(title)==1:
            post['title'] = f"{post['author']}: {BeautifulSoup(title[0],'lxml').text.replace('$','')[:20]}"
        else:
            post['title'] = f"{post['author']}: Re:{title[1].split('<br>')[0][:10]} {BeautifulSoup(title[0],'lxml').text.replace('$','')[:20]}"

        icomment=f"↴{item['reply_count']}" if item['reply_count']>0 else ""
        ilike=f"↑{item['like_count']}" if item['like_count']>0 else ""
        author_info = f"💭 {post['author']} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {icomment} {ilike}"
        
        content=content.replace('//@', '<br><br>🔃 ')
        # starts with <p>
        if content.startswith('<p>'):
            content=re.sub(r'(<p[^>]*>)', r'\1' + f"{author_info}<br>", content, count=1)
        else:
            content=f"{author_info}<br>{content}"
        # ends with </p>
        if content.endswith('</p>'):
            content=f"{content}<br>"
        else:
            content=f"{content}<br><br>"

        # excellent comments
        try:
            comment=''
            if len(item['excellent_comments']) > 0:
                cauthor = cc.convert(item['excellent_comments'][0]['user']['screen_name'])
                ccoment = cc.convert(item['excellent_comments'][0]['text'])
                if avg_text_len_between_br(ccoment) > 22:
                    ccoment=re.sub(r'<br\s*/?\s*>(?!<br)', '<br><br>', ccoment) # easier reading
                comment = f"💬 {cauthor}<br>{ccoment}<br><br>"
            content = content + comment
        # KeyError: 'excellent_comments'
        except: 
            pass
        
        # Replace emoji height attribute with a smaller value and width (including comment)
        content=re.sub(r'(<img[^>]*emoji[^>]*)\sheight="[^"]*"', r'\1 height="18" width="18"', content)
        post['description'] = content + f'<div align="right"><a href="{post["link"]}" target="_blank">阅读原文</a></div>'
        
        if not is_blocked(author=post['author'], title=post['title'], content=post['description']):
            posts.append(post)
        
    return {
        'title': "雪球",
        'link': "https://xueqiu.com",
        'description': "雪球热门帖子\nhttps://github.com/superkeyor/rsshubpy/edit/master/app/blocker.json",
        'author': 'Jerry',
        'items': posts 
    }  
