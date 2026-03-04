from rsshub.utils import DEFAULT_HEADERS, fetch, fetch_by_puppeteer, extract_html, ContentBlocker
import requests 
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
import time, random
import re
import arrow
import feedparser

domain = 'https://newmitbbs.com'
blocker=ContentBlocker()

def update_iframes(tag, soup):
    for iframe in tag.find_all('iframe'):
        src = iframe.get('src', '')

        # YouTube: replace with clickable thumbnail
        if 'youtube' in src:
            vid_match = re.search(r'/embed/([A-Za-z0-9_-]+)', src)
            video_id = vid_match.group(1) if vid_match else ''
            style = iframe.get('style', '')
            bg_match = re.search(r'background:\s*url\(([^)]+)\)', style)
            thumb_url = bg_match.group(1) if bg_match else f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
            watch_url = f'https://www.youtube.com/watch?v={video_id}'
            a_tag = soup.new_tag('a', href=watch_url, target='_blank')
            img_tag = soup.new_tag('img', src=thumb_url, width='390')
            a_tag.append(img_tag)
            iframe.replace_with(a_tag)
            continue

        # Twitter: replace with a plain link
        if 'twitter' in src:
            fragment = urlparse(src).fragment
            tweet_id = re.sub(r'\D', '', fragment)
            tweet_url = f'https://twitter.com/i/status/{tweet_id}'
            a_tag = soup.new_tag('a', href=tweet_url, target='_blank')
            a_tag.string = 'Tweet Post'
            iframe.replace_with(a_tag)
            continue

        # Other iframes: keep as-is

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
            print("Last page reached.")
            time.sleep(1) # Sleep between topics
            break

        next_page_url = next_button["href"]
        # Handle relative URLs (e.g., "/page/2")
        if next_page_url.startswith("/") or next_page_url.startswith("./"):
            next_page_url = urljoin(url, next_page_url)

        # Move to the next page
        url = next_page_url

        # Optional: Add a delay to avoid overwhelming the server
        time.sleep(random.uniform(5, 10))  # Sleep for seconds between pages of the same topic

    return soups

def parse(post):
    link=re.sub( '&sid=.*$','', urljoin(domain,post.get('href')) )
    soups = collect_all_pages(link, next_button_attrs={'rel': 'next'})
    contents=[]; authors=[]

    for n, soup in enumerate(soups, start=1):
        # "fix" emoji
        emoji_elements = soup.find_all('img', class_='emoji smilies')
        for emoji in emoji_elements:
            # if 'src' in emoji.attrs:
            #     del emoji['src']
            emoji["width"] = "18px"; emoji["height"] = "18px"
        # "fix" blockquote
        for b in soup.find_all('blockquote'):
            b.decompose()

        # contents.extend(soup.find_all('div',class_="content"))
        for content_div in soup.find_all('div', class_="content"):
            for p in content_div.find_all('p'):
                p.insert_after(soup.new_tag('br')) 
                p.insert_after(soup.new_tag('br')) # convert p to two br
                p.unwrap()
            update_iframes(content_div, soup)
            contents.append(content_div.decode_contents().replace('\n', '').strip())
        # username-coloured for admin
        authors.extend([u.find('span',class_=["username", "username-coloured"]).text for u in soup.find_all('div',class_="postbody")])
    
    content=''; op=authors[0]
    for i, a, c in zip(range(len(authors)), authors, contents):
        if a==op:
            content += f"#{i+1}: <i>{a} (op)</i> <br>{c}"
        else:
            content += f"#{i+1}: <i>{a}</i> <br>{c}"
    content += f'<div align="right"><a href="{link}" target="_blank">阅读原文</a></div>'
    
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
    
    posts = list(map(parse, posts))
    filtered_posts = []
    for post in posts:
        if ( not blocker.match(post['author'], blocker.rules['newmitbbs']['author']) ) and \
           ( not blocker.match(post['title'], blocker.rules['newmitbbs']['title']) ) and \
           ( not blocker.match(post['description'], blocker.rules['newmitbbs']['content']) ):
            post['title'] = f"{post['author']}: {post['title']}"
            filtered_posts.append(post)

    return {
        'title': '新未名空间',
        'link': domain,
        'description': '一个海外华人中文交流的论坛',
        'author': 'Jerry',
        'items': filtered_posts
    }

