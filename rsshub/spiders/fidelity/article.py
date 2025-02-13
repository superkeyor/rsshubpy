import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup, NavigableString
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
    
def ctx(category=''):
    routes = {
        'weekly': f"{domain}/learning-center/trading-investing/weekly-market-update",
        'quarterly': f"{domain}/viewpoints/market-and-economic-insights/quarterly-market-update",
        'ideas': f"{domain}/learning-center/trading-investing/qsiru",
    }
    url = routes[category]
    
    html = fetch(url, headers=DEFAULT_HEADERS).get()
    soup = BeautifulSoup(html, 'html.parser')

    item = {}
    item['title'] = soup.find('h1').text
    item['link'] = url
    item['pubDate'] = datetime.strptime(soup.find('div',attrs={'itemprop': 'datePublished'}).text.strip(), "%B %d, %Y")

    content = []
    def extract_html(element):
        if element is None:
            return ""
        else:
            return str(element) # ''.join(str(c) for c in element.contents if isinstance(c, NavigableString))
    
    ad = soup.find('div',attrs={'class':'Call-Out-Part'})
    subtitle = soup.find('div', attrs={'class': 'article-teaser-paragraph'})
    author = soup.find('div', attrs={"itemprop": "author"})
    summary = soup.find('div', attrs={"class": "article-below-image"})
    article = soup.find('div', attrs={"id": "article-template-body"})
    
    if ad:
        ad.decompose()
    if subtitle:
        content.append(extract_html(subtitle))
        content.append('<br>')
        # content.append('<br>'*2)
    if author:
        content.append(f"<i>{extract_html(author)}</i>")
    if summary:
        content.append(extract_html(summary))
    if article:
        content.append(extract_html(article))
    
    content = ''.join(content) 
    item['description'] = content
    
    return {
        'title': f'Fidelity {category.title()}',
        'link': url,
        'description': f'Fidelity Market {category.title()}',
        'author': 'jerry',
        'items': [item]
    }
