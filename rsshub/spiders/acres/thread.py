from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_puppeteer, extract_html, decompose_element
import requests 
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import time, random
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
        # session.headers.update(headers)
        session.headers.update(DEFAULT_HEADERS)
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
        time.sleep(random.uniform(10, 15))  # Sleep for seconds between requests
        
        p+=1
        if p>1: break
    return soups

def parse(post):
    link=urljoin(domain,'bbs/'+post.get('href'))
    print(link)
    soups = collect_all_pages(link, next_button_attrs={'class': 'nxt'})
    if len(soups)==0: # could not retrieve page
        item={'title':post.text,
              'link':link,
              'author':'timeout',
              'pubDate':datetime.now(),
              'description':f'<a href="{link}" target="_blank">阅读原文</a>'}
        return item
    contents=[]; thumbups=[]; thumbdowns=[]; authors=[]

    # p: page number
    for p, soup in enumerate(soups, start=1):
        # all posts in one page
        authis = soup.find_all('div',class_="authi")
        # print(soup)
        for authi in authis:
            author = authi.text.strip().split()[0]
            # anonymous or anonymous via app
            if "匿名用户" not in author: 
                author = authi.find('a').text
            authors.extend([author])
        
        if p==1: 
            try:
                pubDate=datetime.strptime(authis[0].find(itemprop="datePublished").get('content'), '%Y-%m-%d %H:%M')
            except:
                # anonymous
                try: 
                    pubDate=datetime.strptime(authis[0].find(id=re.compile('authorposton')).find('span').get('title'), '%Y-%m-%d %H:%M:%S')
                except:
                # anonymous via app
                    pubDate=datetime.strptime(authis[0].find(id=re.compile('authorposton')).text, '%Y-%m-%d %H:%M:%S')
        
        login_message=soup.find('div',class_="attach_nopermission")
        if login_message: login_message.decompose()
        
        soup = decompose_element(soup, 'div',class_="quote")
        soup = decompose_element(soup, 'font',class_="jammer")
        soup = decompose_element(soup, 'i',class_="pstatus")
        soup = decompose_element(soup, 'div',style="display:none;")
        
        # contents.extend( soup.find_all('td',itemprop="articleBody") )
        contents.extend( soup.select('td[itemprop="articleBody"], div.locked') ) # sometimes locked contents
        thumbups.extend( [e.text for e in soup.find_all('i',id=re.compile('rec_add_\d+'))] )
        thumbdowns.extend( [e.text for e in soup.find_all('i',id=re.compile('rec_sub_\d+'))] )
    
    content=''
    op=authors[0]
    for i, a, c, u, d in zip(range(len(authors)), authors, contents, thumbups, thumbdowns):
        reaction = '&nbsp;&nbsp;&nbsp;&nbsp;'
        if int(u)>0: reaction += f" ↑{u}"
        if int(d)>0: reaction += f" ↓{d}"
        # c = str(c).replace("\n<br/>\r\n","")
        if a==op: 
            content += f"#{i+1}: <i>{a} (op)</i> {reaction} <br>{c}<br><br>"
        else:
            content += f"#{i+1}: <i>{a}</i> {reaction} <br>{c}<br><br>"
    content += f'<a href="{link.replace("-1-1.","-2-1.")}" target="_blank">阅读原文</a>'
    
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
        html = fetch(url, headers=DEFAULT_HEADERS).get()
        soup = BeautifulSoup(html, 'lxml')
        
        for th in soup.find_all('th', attrs={'class':'common'}):
            if th.find('img', attrs={'alt':'heatlevel'}) or th.find('img', attrs={'alt':'digest'}):
                posts.append(th.find('a',attrs={'class':'xst'}))
    
    posts = list(dict.fromkeys(posts))  # unique list while preserving order

    return {
        'title': '一亩三分地',
        'link': domain,
        'description': '伴你一起成长',
        'author': 'Jerry',
        'items': list(map(parse, posts)) 
    }
