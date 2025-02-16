from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_puppeteer, extract_html
import requests 
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import time
import re
import arrow
import feedparser

domain = 'https://www.1point3acres.com/'

def ctx(category=''):
    urls=[urljoin(domain,'/bbs/forum.php?mod=guide&view=hot'), urljoin(domain,'/bbs/forum.php?mod=guide&view=digest')]
    items=[]
    
    for url in urls:
        html = fetch(url, headers=DEFAULT_HEADERS).get()
        soup = BeautifulSoup(html, 'lxml')
        
        for tbody in soup.find_all('tbody', attrs={'id':re.compile("normalthread_\d+")}):
            for th in tbody.find_all('th', attrs={'class':'common'}):
                if th.find('img', attrs={'alt':'heatlevel'}) or th.find('img', attrs={'alt':'digest'}):
                    item={}
                    post=th.find('a',attrs={'class':'xst'})
                    item['title']=post.text
                    item['link']=urljoin(domain,'bbs/'+post.get('href'))
                    item['author']=tbody.find('cite',class_="truncate").text
                    pubDate=tbody.find('em').find('span',title=re.compile("^\d{4}\-\d{1,2}\-\d{1,2}"))
                    if pubDate:
                        pubDate=pubDate.get('title')
                    else:
                        pubDate=tbody.find('em').find('span').text
                    item['pubDate']=datetime.strptime( pubDate, "%Y-%m-%d")
                    item['description']=''
                    items.append(item)
    
    items = list({tuple(d.items()): d for d in items}.values())  # unique list while preserving order

    return {
        'title': '一亩三分地',
        'link': 'https://www.1point3acres.com/bbs/forum.php?mod=guide&view=hot&mobile=2',
        'description': '伴你一起成长',
        'author': 'Jerry',
        'items': items
    }
