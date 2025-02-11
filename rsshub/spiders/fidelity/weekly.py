import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_puppeteer, escape_html

domain = 'https://www.fidelity.com'

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
    url = f"{domain}/learning-center/trading-investing/weekly-market-update"
    html = fetch(url, headers=DEFAULT_HEADERS).get()
    soup = BeautifulSoup(html, 'html.parser')

    item = {}
    item['title'] = soup.find('h1').text
    item['content'] = escape_html( soup.find('div',attrs={'id':'article-template-body'}) )
    item['link'] = url
    item['pubDate'] = datetime.strptime(soup.find('div',attrs={'class':'article-teaser-paragraph'}).text.split(':')[1].strip(), "%B %d, %Y")

    return {
        'title': 'Fidelity Market Weekly',
        'link': url,
        'description': 'Fidelity Market Weekly',
        'author': 'jerry',
        'items': [item]
    }
