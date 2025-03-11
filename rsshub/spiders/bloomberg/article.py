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
    item['title'] = title
    item['link'] = link
    item['pubDate'] = datetime.fromisoformat(soup.find('time').get('datetime').replace('Z', '+00:00'))
    item['id'] = link
    item['author'] = soup.find('a',class_=re.compile('Byline_author')).text
    
    content = soup.find('div',class_=re.compile("gridLayout_centerContent"))
    ########## remove all buttons
    buttons = content.find_all('button')
    for button in buttons:
        if not button.find('img'):
            button.decompose()
    
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
    
    ########## resize images
    images = content.find_all('img', srcset=True)
    fixed_width = 480
    # Update each image to use the fixed width and proportional height
    for img in images:
        try:
            img['width'] = fixed_width
            if 'srcset' in img.attrs:
                # Get the first URL from srcset to extract dimensions
                srcset_items = img['srcset'].split(', ')
                first_item = srcset_items[0].strip()
                url = first_item.split(' ')[0]  # Extract URL (e.g., "220x147.webp")
                # Extract width and height from the URL
                filename = url.split('/')[-1]
                dimensions = filename.split('.')[0]
                original_width, original_height = map(int, dimensions.split('x'))
                # Calculate proportional height
                aspect_ratio = original_height / original_width
                img['height'] = int(fixed_width * aspect_ratio)
            # Remove srcset and sizes attributes (no longer needed)
            del img['srcset']
            if 'sizes' in img.attrs:
                del img['sizes']
        except Exception as e:
            print(f"Error processing image: {e}")
    
    item['description'] = f'{str(content)} <div align="right"><a href="{link}" target="_blank">Original Article</a></div>'

    return {
        'title': f'Bloomberg {category.title()}',
        'link': url,
        'description': f'Bloomberg Market {category.title()}',
        'author': 'jerry',
        'items': [item]
    }
