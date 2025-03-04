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
    
    # feed level
    posts = feed.entries
    
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
    
    for post in posts:
        soup = BeautifulSoup(post['summary'],'lxml')
        
        if post['title']=='': 
            post['title']=post['author'] + ": " + soup.text.replace("$","")[:20]
        else:
            post['title']=post['author'] + ": " + post['title']

        if regex_match(post['author'], blocker['xueqiu']['author']): posts.remove(post)
        if regex_match(post['title'], blocker['xueqiu']['title']): posts.remove(post)
        if regex_match(post['summary'], blocker['xueqiu']['content']): posts.remove(post)
        
        for img in soup.find_all('img', src=lambda x: 'emoji' in x):
            # Replace the height attribute with a smaller value
            img['height'] = '12'
        post['summary'] = str(soup)
        
    return {
        'title': "雪球",
        'link': "https://xueqiu.com",
        'description': "雪球热门帖子",
        'author': 'Jerry',
        'items': posts 
    }  
