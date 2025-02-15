import requests 
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, fetch, extract_html
import re
from datetime import datetime

url = 'https://newmitbbs.com'

def parse(post):
    
    link=re.sub('&sid=.*$','',url+post.get('href')[1:])
    html=fetch(link, headers=DEFAULT_HEADERS).get()
    soup=BeautifulSoup(html, 'lxml')
    contents=soup.find_all('div',class_="content")
    
    # "fix" emoji
    emoji_elements = soup.find_all('img', class_='emoji smilies')
    for emoji in emoji_elements:
        if 'src' in emoji.attrs:
            del emoji['src']
    
    content=''
    authors=[u.find('span',class_="username").text for u in soup.find_all('div',class_="postbody")]
    for i, a, p in zip(range(len(authors)), authors, contents):
        content += f"#{i+1}: <i>{a}</i> {p}"
    
    item = {}
    item['title']=post.text
    item['link']=link
    item['author']=authors[0]
    item['pubDate']=datetime.fromisoformat( soup.find('time').get('datetime') )
    item['description']=content
    
    return item

def ctx(category=''):
    html = fetch(url, headers=DEFAULT_HEADERS).get()
    soup = BeautifulSoup(html, 'lxml')
    
    pop = soup.find('div',attrs={'id':'popular-topics-box'}).find_all('a',attrs={"class":"topictitle"})
    rec = soup.find('div',attrs={'id':'recent-recommended-topics-box'}).find_all('a',attrs={"class":"topictitle"})
    posts = list(dict.fromkeys(pop + rec))  # unique list while preserving order

    return {
        'title': '新未名空间',
        'link': url,
        'description': '一个海外华人中文交流的论坛',
        'author': 'Jerry',
        'items': list(map(parse, posts)) 
    }  
