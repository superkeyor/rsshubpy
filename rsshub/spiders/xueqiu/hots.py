import requests 
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, extract_html
import re, json

def ctx(category=''):
    feed_url = f"http://192.168.1.2:1200/xueqiu/hots"
    res = requests.get(feed_url,headers=DEFAULT_HEADERS,verify=False)
    feed = feedparser.parse(res.text)
    
    # feed level
    posts = feed.entries
    
    blocker = requests.get("https://raw.githubusercontent.com/superkeyor/rsshub_python/blocker.json").json
    def regex_match(text, keywords):
        """Helper function to check if any of the keywords match the text using regex."""
        for keyword in keywords:
            if re.search(keyword, text):
                return True
        return False
    
    for post in posts:
        if regex_match(post['author'], blocker['xueqiu']['author'])]: posts.pop(post)

    return {
        'title': "雪球",
        'link': "https://xueqiu.com",
        'description': "雪球热门帖子",
        'author': 'Jerry',
        'items': posts 
    }  
