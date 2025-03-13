from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_requests, fetch_by_browser, extract_html, decompose_element
import requests 
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import time
import re
import arrow
import feedparser

domain = 'https://www.bloomberg.com'

def ctx(category=''):
    routes = {
        'wrap': f"{domain}/latest/markets-wrap",
    }
    url = routes[category]

    soup, source, link, title = fetch_by_browser(url)
    item = {}
    item['title'] = soup.find('h1').text
    abstract = soup.find('ul',class_=re.compile("abstract"))
    item['link'] = link
    pubDate = soup.find_all('time')[-1].get('datetime')  # initial time or updated time
    item['pubDate'] = datetime.fromisoformat(pubDate.replace('Z', '+00:00'))
    # item['id'] = link  # comment out, so that update will be a new article based on update time
    item['author'] = soup.find('a',class_=re.compile('Byline_author')).text
    
    content = soup.find('div',class_=re.compile("gridLayout_centerContent"))
    ########## remove author/timestamp
    content = decompose_element(content,'div',class_=re.compile("styles_bylineSpeech"))

    ########## remove all buttons
    buttons = content.find_all('button')
    for button in buttons:
        if not button.find('img'):
            button.decompose()
        else:
            # Change button with img to div tag (to fix mobile view)
            button.name = 'div'
    
    ########## remove players
    pattern = re.compile(r'(Audio|Video)\w*Player')
    divs_to_remove = content.find_all('div', class_=pattern)
    for div in divs_to_remove:
        div.decompose()
    
    ########## remove end of article
    pattern = re.compile(r'authorBlock')
    author_block_div = content.find('div', class_=pattern)
    # If the authorBlock div is found, delete all divs after it
    if author_block_div:
        # Flag to indicate whether we've encountered the authorBlock div
        found_author_block = False
        # Traverse all elements in the document
        for element in content.find_all('div'):
            if element == author_block_div:
                found_author_block = True
            elif found_author_block and element.name == 'div':
                element.decompose()
    
    item['description'] = f'{str(abstract)+str(content)} <div align="right"><a href="{link}" target="_blank">Original Article</a></div>'

    return {
        'title': f'Bloomberg {category.title()}',
        'link': url,
        'description': f'Bloomberg Market {category.title()}',
        'author': 'jerry',
        'items': [item]
    }
