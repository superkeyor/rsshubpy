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

def parse_html_content(html_content):
    soup = BeautifulSoup(html_content, 'lxml')
    # Find all <a> tags with xueqiu.com in href and remove them
    for tag in soup.find_all('a', href=lambda x: x and 'xueqiu.com' in x):
        tag.decompose()
    return str(soup).replace("$","")  # replace $ to remove stock symbol link

def parse_conversation(text):
    # Split by '//' to separate different comments
    parts = text.split('//')
    result = []
    for part in parts:
        # Remove "回复@username:" pattern and extract the actual content
        match = re.match(r'@([^:]+):\s*(?:回复@[^:]+:\s*)?(.*)', part.strip())
        if match:
            username = '# ' + match.group(1).strip()
            content = match.group(2).strip()
            result.append(username+'<br>'+content+'<br><br>')
    return result[::-1]

def parse_picture(pic_urls, pic_sizes):
    pics_html = ''
    # pic_urls: 'https://xqimg.imedao.com/19c0bc53b0a3e3343faf13d5.png,https://xqimg.imedao.com/19c0bc53dbb3ea2c3fd615ab.png,https://xqimg.imedao.com/19c0bc53fbd3fe813fe363b8.png'
    # pic_sizes: [{'width': 550, 'height': 304}, {'width': 550, 'height': 275}, {'width': 550, 'height': 304}]
    if pic_urls:
        pic_urls = pic_urls if type(pic_urls) is list else pic_urls.split(',')
        for pic_url, size in zip(pic_urls, pic_sizes):
            pics_html += f'<a href="{pic_url}" target="_blank"><img src="{pic_url}" width="{size["width"]//2}" height="{size["height"]//2}"></a>'
        pics_html += '<br><br>'
    return pics_html

def ctx(id='', category=''):
    # 10:'全部'  0:'原发布'  2:'长文'  4:'问答'  9:'热门'  11:'交易'
    url1 = f"{domain}/u/{id}" # set cookie first
    url2 = f"{domain}/v4/statuses/user_timeline.json?user_id={id}&type={category}"
    soup, source, url, title = fetch_by_browser([url1, url2], wait=10)
    items=json.loads(soup.text)['statuses']
    
    posts = []
    for item in items:
        post = {}
        post['author'] = item['user']['screen_name']
        post['link'] = f"{domain}/{item['user_id']}/{item['id']}"
        post['id'] = post['link']
        post['pubDate'] = arrow.get(item['created_at']).isoformat()
        text = parse_html_content(item['description'])
        post['title'] = f"{post['author']}: {text[:20]}"
        
        post['description'] = ''.join(parse_conversation(f"@{post['author']}: {text}"))
        post['description'] += parse_picture(item['pic'], item['pic_sizes']) # add pictures if any
        
        if item['retweeted_status']:
            retweet = item['retweeted_status']
            retweet_author = retweet['user']['screen_name']
            retweet_link = f"{domain}/{retweet['user_id']}/{retweet['id']}"
            retweet_title = retweet['title']
            retweet_text = parse_html_content(retweet['description']) + '<br><br>'
            retweet_text += parse_picture(retweet['pic'], retweet['pic_sizes'])
            post['description'] = f"# {retweet_author}<br><a href='{retweet_link}' target='_blank'>🔄</a>{retweet_title} {retweet_text}" + post['description']

        post['description'] += f'<div align="right"><a href="{post["link"]}" target="_blank">阅读原文</a></div>'
        posts.append(post)

    return {
        'title': "雪球",
        'link': url1,
        'description': "雪球用户动态",
        'author': 'Jerry',
        'items': posts
    }
