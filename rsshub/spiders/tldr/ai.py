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
    
    item = {}
    item['title'] = soup.find('h2').text
    item['link'] = url
    item['pubDate'] = datetime.strptime(soup.find('h1').text.split(' ')[-1].strip(), "%Y-%m-%d")
    
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

    # Remove header
    pt_px_div = soup.find('div', class_='pt-3 px-6')
    if pt_px_div:
        pt_px_div.decompose()

    # Remove the specific footer div
    footer_div = soup.find('div', attrs={'data-sentry-component': 'Footer'})
    if footer_div:
        footer_div.decompose()

    # Center header: freshrss reader could remove css style?
    # for s in soup.find_all('header'):
    #     s['style'] = 'text-align: center !important; display: block !important;'
    
    # Wrap the contents of each <header> with a <center> tag
    headers = soup.find_all('header')
    for header in headers:
        center_tag = soup.new_tag('center')
        header.wrap(center_tag)
        
    sections = [s for s in soup.find_all('section') if s.text.strip()]
    content = "\n".join(str(s) for s in sections)
    
    # Wrap the content in a table with left and right margins
    content = f'''
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td width="2.5%"></td> <!-- Left margin -->
        <td>
          {content} <!-- Content goes here -->
        </td>
        <td width="2.5%"></td> <!-- Right margin -->
      </tr>
    </table>
    '''
    
    item['description'] = content
    
    return {
        'title': 'TLDR AI',
        'link': url,
        'description': 'TLDR AI',
        'author': 'jerry',
        'items': [item]
    }
