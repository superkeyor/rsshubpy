import requests 
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, extract_html
import re, json, os

from opencc import OpenCC
cc = OpenCC('t2s')  # t2s = Traditional to Simplified

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

def ctx(category=''):
    feed_url = f"http://192.168.1.2:1200/xueqiu/hots"
    res = requests.get(feed_url,headers=DEFAULT_HEADERS,verify=False)
    feed = feedparser.parse(res.text)
    
    # print(list(os.environ.items()))
    if os.getenv('FLASK_ENV') == "development": 
        with open('rsshub/blocker.json', 'r') as file:
            blocker = json.load(file)
            print(blocker)
    else:
        blocker = requests.get("https://raw.githubusercontent.com/superkeyor/rsshub_python/refs/heads/master/rsshub/blocker.json").json()
    def regex_match(text, keywords):
        """Helper function to check if any of the keywords match the text using regex."""
        for keyword in keywords:
            if re.search(keyword, text):
                return True
        return False
    
    posts = []
    for post in feed.entries:
        # feedparser has both summary and description as aliases; rsshub/templates/main/atom.xml template uses 'description'
        soup = BeautifulSoup(post['description'],'lxml')
        
        if post['title']=='': 
            post['title']=post['author'] + ": " + soup.text.replace("$","")[:20]
        else:
            post['title']=post['author'] + ": " + post['title']
        post['title'] = post['title'].replace("回复@","Re ")
        
        if ( not regex_match(post['author'], blocker['xueqiu']['author']) ) and \
           ( not regex_match(post['title'], blocker['xueqiu']['title']) ) and \
           ( not regex_match(post['description'], blocker['xueqiu']['content']) ):
            posts.append(post)
        
        for img in soup.find_all('img', src=lambda x: 'emoji' in x):
            # Replace the height attribute with a smaller value
            img['height'] = 18; img['width'] = 18;
        
        content =str(soup)
        content = cc.convert(content)  # 繁转简, e.g., 管我财
        if avg_text_len_between_br(content) > 22:
            content=re.sub(r'<br\s*/?\s*>(?!<br)', '<br><br>', content)
        # 回复<a href="https://xueqiu.com/n/持股待涨养家糊口" target="_blank">@持股待涨养家糊口</a>: 
        content=re.sub(r'回复<a href="https://xueqiu\.com/n/[^"]*"[^>]*>@[^<]*</a>:\s*', '', content)
        content=re.sub(r'//<a href="https://xueqiu\.com[^"]*"[^>]*>(@[^<]*)</a>:', r'//\1<br>', content) 
        content=re.sub(r'<a href="https://xueqiu\.com[^"]*"[^>]*>([^<]*)</a>', r'\1', content)
        content=content.replace('//@', '<br><br>💬 ')
        if re.search(r'<p[^>]*>', content):
            content=re.sub(r'(<p[^>]*>)', r'\1' + f"💭 {post['author']}<br>", content, count=1)
            content=f"{content}<br>"
        else:
            content=f"💭 {post['author']}<br>{content}<br><br>"
        post['description'] = content + f'<div align="right"><a href="{post["link"]}" target="_blank">阅读原文</a></div>'
        
    return {
        'title': "雪球",
        'link': "https://xueqiu.com",
        'description': "雪球热门帖子\nhttps://github.com/superkeyor/rsshub_python/edit/master/rsshub/blocker.json",
        'author': 'Jerry',
        'items': posts 
    }  
