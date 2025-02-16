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

def collect_all_pages(start_url, next_button_attrs):
    """
    Collect all pages starting from the given URL by following the "Next" button.
    Args:
        start_url (str): The URL of the first page to scrape.
        next_button_attrs (dict): attributes used to identify the "Next" button.
    Returns:
        list: A list of BeautifulSoup objects for all pages.
    """
    session = requests.Session()
    soups = []

    url = start_url
    p=1
    while url:
        session.headers.update(headers)
        response = session.get(url)
        if response.status_code != 200:
            print(f"Failed to retrieve page: {url}")
            break

        print(response)
        soup = BeautifulSoup(response.content, "lxml")
        soups.append(soup)

        next_button = soup.find("a", attrs=next_button_attrs)
        if not next_button or not next_button.get("href"):
            print("No more pages found.")
            break

        next_page_url = next_button["href"]
        # Handle relative URLs (e.g., "/page/2")
        if not next_page_url.startswith(('http://', 'https://')):
            next_page_url = urljoin(url, next_page_url)
        else:
            next_page_url = next_page_url

        # Move to the next page
        url = next_page_url

        # Optional: Add a delay to avoid overwhelming the server
        time.sleep(5)  # Sleep for 1 second between requests
        
        p+=1
        if p>1: break
        
    return soups

def parse(post):
    link=urljoin(domain,'bbs/'+post.get('href'))
    print(link)
    soups = collect_all_pages(link, next_button_attrs={'class': 'nxt'})
    contents=[]; thumbups=[]; thumbdowns=[]; authors=[]

    for n, soup in enumerate(soups, start=1):
        authi = soup.find('div',class_="authi")
        author = authi.find('a').text
        # anonymous
        if "添加认证" in author:
            author = authi.text.strip().split()[0]
        
        if n==1: pubDate=datetime.strptime(authi.find(id=re.compile('authorposton')).find('span').get('title'), '%Y-%m-%d %H:%M:%S')

        login_message=soup.find('div',class_="attach_nopermission")
        if login_message: login_message.decompose()
        quote=soup.find('div',class_="quote")
        if quote: quote.decompose()
        
        contents.extend( [e.contents for e in soup.find_all('td',itemprop="articleBody")] )
        thumbups.extend( [e.text for e in soup.find_all('i',id=re.compile('rec_add_\d+'))] )
        thumbdowns.extend( [e.text for e in soup.find_all('i',id=re.compile('rec_sub_\d+'))] )
        authors.extend([author])
  
    
    content=''; op=authors[0]
    for i, a, c, u, d in zip(range(len(authors)), authors, contents, thumbups, thumbdowns):
        if a==op:
            content += f"#{i+1}: <i>{a} (op)</i> {c}<br>👍{u} {d}👎<br>"
        else:
            content += f"#{i+1}: <i>{a}</i> {c}<br>👍{u} {d}👎<br>"
    
    item = {}
    item['title']=post.text
    item['link']=link
    item['author']=op
    item['pubDate']=pubDate
    item['description']=content
    
    return item

def ctx(category=''):
    urls=[urljoin(domain,'/bbs/forum.php?mod=guide&view=hot'), urljoin(domain,'/bbs/forum.php?mod=guide&view=digest')]
    urls=[urljoin(domain,'/bbs/forum.php?mod=guide&view=hot')]
    posts=[]
    
    for url in urls:
        html = fetch(url, headers=headers).get()
        soup = BeautifulSoup(html, 'lxml')
        
        for th in soup.find_all('th', attrs={'class':'common'}):
            if th.find('img', attrs={'alt':'heatlevel'}) or th.find('img', attrs={'alt':'digest'}):
                posts.append(th.find('a',attrs={'class':'xst'}))
    
    posts = list(dict.fromkeys(posts))  # unique list while preserving order

    return {
        'title': '新未名空间',
        'link': domain,
        'description': '一个海外华人中文交流的论坛',
        'author': 'Jerry',
        'items': list(map(parse, posts)) 
    }
