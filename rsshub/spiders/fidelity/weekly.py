import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_puppeteer

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

def escape_unescaped_html(html_content):
    """
    Escape unescaped HTML tags while preserving already escaped characters.
    """
    html_content = str(html_content)
    # Regex to match unescaped HTML tags
    pattern = re.compile(r"(?<!&lt;)(<[^>]+>)(?!&gt;)")
    # Replace unescaped tags with their escaped versions
    escaped_content = pattern.sub(lambda match: html.escape(match.group(0)), html_content)
    return escaped_content
    
def ctx(lang=''):
    url = f"{domain}/learning-center/trading-investing/weekly-market-update"
    html = fetch(url, headers=DEFAULT_HEADERS).get()
    soup = BeautifulSoup(html, 'html.parser')

    item = {}
    item['title'] = soup.find('h1').text
    item['content'] = escape_unescaped_html( soup.find('div',attrs={'id':'article-template-body'}) )
    item['link'] = url
    item['pubDate'] = datetime.strptime(soup.find('div',attrs={'class':'article-teaser-paragraph'}).text.split(':')[1].strip(), "%B %d, %Y")

    return {
        'title': 'Fidelity Market Weekly',
        'link': url,
        'description': 'Fidelity Market Weekly',
        'author': 'jerry',
        'items': [item]
    }
