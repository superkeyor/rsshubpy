import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_puppeteer, escape_html

domain = 'https://tldr.tech'

def parse_news(news):
    title = news.get('content', '') if news.get('title', '')=='' else news.get('title', '')

    content = news.get('content', '')
    detail_url = news.get('detailUrl', '')
    time = datetime.utcfromtimestamp(int(news['time'])).strftime('%Y-%m-%dT%H:%M:%SZ')

    item = {
        'title': title,
        'description': content,
        'link': detail_url,
        'pubDate': time
    }
    return item
    
def ctx(lang=''):
    url = f"{domain}/api/latest/ai"
    html = fetch(url, headers=DEFAULT_HEADERS).get()
    soup = BeautifulSoup(html, 'html.parser')

    # Remove sponsored articles
    articles = soup.find_all('article')
    for article in articles:
        heading = article.find('h3')
        if heading and '(Sponsor)' in heading.text:
            article.decompose()  # Remove the article from the DOM

    # Remove elements with specific margin classes
    margin_elements = soup.find_all(class_='mb-2')
    for element in margin_elements:
        element.decompose()  # Remove the element from the DOM


    item = {}
    item['title'] = soup.find('h2').text
    item['description'] = str( soup )
    item['link'] = url
    item['pubDate'] = datetime.strptime(soup.find('h1').text.split(' ')[-1].strip(), "%Y-%m-%d")

    return {
        'title': 'TLDR AI',
        'link': url,
        'description': 'TLDR AI',
        'author': 'jerry',
        'items': [item]
    }
