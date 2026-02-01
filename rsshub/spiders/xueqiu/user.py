import requests
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, extract_html, fetch_by_browser
import re, json, os

# https://xueqiu.com/u/1247347556
# http://192.168.1.2:1200/xueqiu/user/1247347556
# https://github.com/DIYgod/RSSHub/blob/master/lib/routes/xueqiu/user.ts

domain = 'https://xueqiu.com'

def ctx(id='', category=''):
    # 10:'全部'  0:'原发布'  2:'长文'  4:'问答'  9:'热门'  11:'交易'
    url1 = f"{domain}/u/{id}" # set cookie first
    url2 = f"{domain}/v4/statuses/user_timeline.json?user_id={id}&type={category}"
    soups, sources, urls, titles = fetch_by_browser([url1, url2], wait=10)
    
    items=json.loads(soups[1].text)['statuses']
    articles = soups[0].find_all('article')
    posts = []
    for item, article in zip(items, articles):
        post = {}

        post['author'] = item['user']['screen_name']
        post['link'] = f"{domain}/{item['user_id']}/{item['id']}"
        post['id'] = post['link']
        post['pubDate'] = arrow.get(item['created_at']).isoformat()

        # inner html
        if article.find('div', class_='content--description'):
            content=article.find('div', class_='content--description').find('div').decode_contents()
        else:
            content=item['description']
        # 回复<a href="https://xueqiu.com/n/持股待涨养家糊口" target="_blank">@持股待涨养家糊口</a>: 
        content=re.sub(r'回复<a href="https://xueqiu\.com/n/[^"]*"[^>]*>@[^<]*</a>:\s*', '', content)
        content=re.sub(r'//<a href="https://xueqiu\.com[^"]*"[^>]*>(@[^<]*)</a>:', r'//\1<br>', content)
        
        title=content.split("//@")
        if len(title)==1:
            post['title'] = f"{post['author']}: {BeautifulSoup(title[0],'lxml').text[:20]}"
        else:
            post['title'] = f"{post['author']}: Re:{title[1].split('<br>')[0][:10]} {BeautifulSoup(title[0],'lxml').text[:20]}"

        # Check for forwarded blockquote
        flink = fname = fcontent = fimages = ''
        fblock = article.find('blockquote', class_='timeline__item__forward')
        if fblock:
            flink = domain + fblock.find('a', class_='fake-anchor').get('href')
            fname = fblock.find('span', class_='user-name').get_text(strip=True).lstrip('@')
            # Get forwarded content
            content_div = fblock.find('div', class_='content--description')
            if content_div:
                inner_div = content_div.find('div')
                if inner_div:
                    fcontent = inner_div.decode_contents()
            
            # Get images from nested blockquote
            images_block = fblock.find('blockquote', class_='status__images')
            if images_block:
                for img in images_block.find_all('img'):
                    src = img.get('data-src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        fimages += f'<a href="{src}" target="_blank"><img src="{src}" width="200"></a>'
                fimages += '<br><br>'
        
        # Get stats from footer
        icomment=ilike=''
        footer = article.find('div', class_='timeline__item__ft--other')
        if footer:
            stats = []
            controls = footer.find_all('a', class_='timeline__item__control')
            for ctrl in controls:
                span = ctrl.find('span')
                if span:
                    text = span.get_text(strip=True)
                    if text.isdigit():
                        stats.append(int(text))
                    else:
                        stats.append(0)
            # forward, comment, like, favorite, complain
            icomment=f"↴{stats[1]}" if stats[1]>0 else ""
            ilike=f"↑{stats[2]}" if stats[2]>0 else ""
        
        content=content.replace('//@', '<br><br>💬')
        content=f"💬{post['author']} {icomment} {ilike}<br>{content}<br><br>"
        quote=f"🔄{fname}<br><a href=\"{flink}\" target=\"_blank\">{fcontent}</a><br>{fimages}" if fname else ""

        post['description'] = f'{content}{quote}'
        post['description'] += f'<div align="right"><a href="{post["link"]}" target="_blank">阅读原文</a></div>'
        posts.append(post)

    return {
        'title': "雪球",
        'link': url1,
        'description': "雪球用户动态",
        'author': 'Jerry',
        'items': posts
    }
