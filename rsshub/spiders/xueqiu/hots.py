import requests 
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, extract_html
import re, json, os

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
        post['title'] = post['title'].replace("回复@","Re:")
        
        if ( not regex_match(post['author'], blocker['xueqiu']['author']) ) and \
           ( not regex_match(post['title'], blocker['xueqiu']['title']) ) and \
           ( not regex_match(post['description'], blocker['xueqiu']['content']) ):
            posts.append(post)
        
        for img in soup.find_all('img', src=lambda x: 'emoji' in x):
            # Replace the height attribute with a smaller value
            img['height'] = 18; img['width'] = 18;
        
        content =str(soup)
        # count total <br, if too many then replace single with double
        br_count = len(re.findall(r'<br\s*/?\s*>', content))
        if br_count > 2:
            content=re.sub(r'<br\s*/?\s*>(?!<br)', '<br><br>', content) # easier reading
        # 回复<a href="https://xueqiu.com/n/持股待涨养家糊口" target="_blank">@持股待涨养家糊口</a>: 
        content=re.sub(r'回复<a href="https://xueqiu\.com/n/[^"]*"[^>]*>@[^<]*</a>:\s*', '', content)
        content=re.sub(r'//<a href="https://xueqiu\.com[^"]*"[^>]*>(@[^<]*)</a>:', r'//\1<br>', content) 
        content=re.sub(r'<a href="https://xueqiu\.com[^"]*"[^>]*>([^<]*)</a>', r'\1', content)
        post['description'] = content + f'<div align="right"><a href="{post["link"]}" target="_blank">阅读原文</a></div>'
        
    return {
        'title': "雪球",
        'link': "https://xueqiu.com",
        'description': "雪球热门帖子\nhttps://github.com/superkeyor/rsshub_python/edit/master/rsshub/blocker.json",
        'author': 'Jerry',
        'items': posts 
    }  
