from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_requests, fetch_by_browser, extract_html, decompose_element
import requests 
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import time, random
import re
import arrow
from urllib.parse import urlparse, urlunparse

domain = 'https://www.v2ex.com'

def get_base_url(url):
    parsed_url = urlparse(url)
    base_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
    return base_url

def collect_all_pages(start_url, next_button_attrs={'title': '下一页'}):
    session = requests.Session()
    soups = []

    url = start_url; i = 1
    base_url = get_base_url(url)
    while url:
        response = session.get(url)
        if response.status_code != 200:
            print(f"Failed to retrieve page: {url}")
            break

        soup = BeautifulSoup(response.content, "lxml")
        soups.append(soup)

        next_button = soup.find("td", attrs=next_button_attrs)
        if not next_button:
            print(f"Found {i} page(s).")
            time.sleep(1) # Sleep between topics
            break

        next_page_url = next_button.get("onclick").replace("location.href='",base_url).replace("';","")
        url = next_page_url; i += 1
        
        time.sleep(random.uniform(5, 10)) # Sleep between pages of same topic

    return soups

def parse(post):
    link = post
    soups = collect_all_pages(link)
    if len(soups)==0:  # Failed to retrieve page
        return {'title': 'null',
                'link': link,
                'id': link,
                'author': 'null',
                'pubDate': datetime.now(),
                'description': ''}
    title=soups[0].select_one('.header h1').text
    author=soups[0].select_one('div.header > small > a').text
    pubDate=datetime.fromisoformat( soups[0].select_one('div.header > small > span').get('title') )
    
    reply_list = []
    for soup in soups:
        reply_list.extend(soup.select('[id^="r_"]'))
    reply_content = ""
    for reply in reply_list:
        content = reply.select_one('.reply_content').decode_contents()
        author1 = reply.select_one('.dark').text
        if reply.select_one('.badge.op'):
            op = "(op)"
        else:
            op = "&nbsp;&nbsp;&nbsp;&nbsp;"
        no = reply.select_one('.no').text
        if reply.select_one('.small.fade'):
            heart = f"❤️{reply.select_one('.small.fade').text.strip()}"
        else:
            heart = ''
        reply_content += f"<p><div>#{no}: <i>{author1} {op}</i>&nbsp;&nbsp;&nbsp;&nbsp;{heart}</div><div>{content}</div></p>"

    content='<br><div>附言</div>'.join([d.decode_contents() for d in soup.select('div.topic_content')])
    content=f"#0: <i>{author} (op)</i><br>{content}<div>{reply_content}</div>"
    content+=f'<div align="right"><a href="{link}" target="_blank">阅读原文</a></div>'

    item = {}
    item['title']=title
    item['link']=link
    item['author']=author
    item['pubDate']=pubDate
    item['description']=content
    
    return item

def ctx(category=''):
    url = f"{domain}/?tab={category}"
    soup = fetch_by_requests(url)
    posts = soup.select('span.item_title > a')
    posts = [f"{domain}{re.sub(r'#.*$', '',post.get('href'))}" for post in posts]

    return {
        'title': 'V2EX',
        'link': domain,
        'description': '',
        'author': 'Jerry',
        'items': list(map(parse, posts)) 
    }
