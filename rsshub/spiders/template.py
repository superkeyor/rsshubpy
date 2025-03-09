from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_requests, fetch_by_browser, extract_html, decompose_element
import requests 
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import time
import re
import arrow
import feedparser

domain = 'https://newmitbbs.com'

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
    while url:
        response = session.get(url)
        if response.status_code != 200:
            print(f"Failed to retrieve page: {url}")
            break

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
        time.sleep(1)  # Sleep for 1 second between requests

    return soups

def parse(post):
    link=re.sub( '&sid=.*$','', urljoin(domain,post.get('href')) )
    soups = collect_all_pages(link, next_button_attrs={'rel': 'next'})
    contents=[]; authors=[]

    # print(list(os.environ.items()))
    # if os.getenv('FLASK_ENV') == "development": 
    
    for n, soup in enumerate(soups, start=1):
        # "fix" emoji
        emoji_elements = soup.find_all('img', class_='emoji smilies')
        for emoji in emoji_elements:
            # if 'src' in emoji.attrs:
            #     del emoji['src']
            emoji["width"] = "1em"; emoji["height"] = "1em"
        # "fix" blockquote
        for b in soup.find_all('blockquote'):
            b.decompose()

        contents.extend(soup.find_all('div',class_="content"))
        authors.extend([u.find('span',class_="username").text for u in soup.find_all('div',class_="postbody")])
    
    soup = decompose_element(soup, 'div',class_="quote")
    
    content=''; op=authors[0]
    for i, a, c in zip(range(len(authors)), authors, contents):
        if a==op:
            content += f"#{i+1}: <i>{a} (op)</i> {c}<br>"
        else:
            content += f"#{i+1}: <i>{a}</i> {c}<br>"
    
    item = {}
    item['title']=post.text
    item['link']=link
    item['author']=op
    item['pubDate']=datetime.fromisoformat( soups[0].find('time').get('datetime') )
    item['description']=content
    
    return item

def ctx(category=''):
    html = fetch(domain, headers=DEFAULT_HEADERS).get()
    soup = BeautifulSoup(html, 'lxml')
    
    pop = soup.find('div',attrs={'id':'popular-topics-box'}).find_all('a',attrs={"class":"topictitle"})
    rec = soup.find('div',attrs={'id':'recent-recommended-topics-box'}).find_all('a',attrs={"class":"topictitle"})
    posts = list(dict.fromkeys(pop + rec))  # unique list while preserving order

    return {
        'title': '新未名空间',
        'link': domain,
        'description': '一个海外华人中文交流的论坛',
        'author': 'Jerry',
        'items': list(map(parse, posts)) 
    }
