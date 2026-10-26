from feeds import feed
from browser import window
from utils import remove_tags
from datetime import datetime
import random
import re

domain = 'https://www.bloomberg.com'

@feed('/bloomberg/<category>')
def ctx(category=''):
    """Bloomberg article (wrap = Markets Wrap), paywall bypassed by userscripts/bloomberg-paywall-bypass.user.js."""
    routes = {
        'wrap': f"{domain}/latest/markets-wrap",
    }
    url = routes[category]


    # originally a fixed 60s dwell on the page:
    # soup, source, link, title = fetch_by_browser(url, wait=60)
    # now: wait until the article body is there (up to 60s), then dwell a little
    with window(url) as page:
        page.open(url)   # redirects to today's article
        page.wait('div[class*="gridLayout_centerContent"] p', timeout=60)
        page.sleep(random.uniform(5, 10))   # body was complete ~5s after load in tests; a human-like dwell
        soup, link = page.soup(), page.url
    item = {}
    item['title'] = soup.find('h1').text
    abstract = soup.find('ul',class_=re.compile("abstract"))
    abstract = abstract if abstract else ''  # sometimes no abstract
    item['link'] = link
    pubDate = soup.find_all('time')[-1].get('datetime')  # initial time or updated time
    item['pubDate'] = datetime.fromisoformat(pubDate.replace('Z', '+00:00'))
    item['id'] = link  # one post each day
    item['author'] = soup.find('a',class_=re.compile('Byline_author')).text
    
    content = soup.find('div',class_=re.compile("gridLayout_centerContent"))
    ########## remove newsletter
    content = remove_tags(content,'div',class_=re.compile("inlineNewsletter"))

    ########## remove author/timestamp
    content = remove_tags(content,'div',class_=re.compile("styles_bylineSpeech"))

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
