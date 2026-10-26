import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
from feeds import feed
from fetch import fetch
from utils import to_html, remove_tags
import re

def parse(post):
    item = {}
    # fidelity
    if post.author=='"Fidelity Investments" <Fidelity.Alerts@Fidelity.com>':
        item['title'] = post.title
        item['pubDate'] = post.published if post.has_key('published') else datetime.now().astimezone().isoformat()
        item['link'] = "https://scs.fidelity.com/customeronly/alerts.shtml"
        # item['link'] = "http://eresearch.fidelity.com/eresearch/landing.jhtml"
        item['author'] = post.author if post.has_key('author') else ''
        
        # keep essential contents
        html = post.summary
        soup = BeautifulSoup(html, 'html.parser')
        content = []

        header = soup.find('table',attrs={'id':'marketUpdate'})
        if header: 
            market = header.find_next('table')
            market = [header, market]
        else:
            market = header
        news = soup.find_all('table',attrs={'class':'DataTableBorder'})
        news2 = soup.find_all('table',attrs={'class':'DatTableBorder'})  # if subscribe news separately, fidelity gives this
        
        content.append(to_html(news))
        content.append(to_html(news2))
        content.append('<hr>')
        content.append(to_html(market))
        content = ''.join(content)
        # content = content.replace('border="1"','border="1" !important')
        content = content.replace('<a class="SmallText" href="https://yahoo.com/#t">Top</a>','')
        content = content.replace('Links in this table will link to details below.','')
        content = content.replace('This table reflects only Equities in your watch list(s) and account(s).','')
        content = content.replace('All data on these chart(s) provided by third parties','')
        content = content.replace('<td align="middle" class="SmallestDataHeader" rowspan="2" width="8%">Currency\n</td>', '')
        content = content.replace('<td align="center" class="SmallData" valign="top">USD</td>\n', '')
        content = re.sub('bgcolor="[#]?.{6}"','',content)
        
        item['description'] = content
    
    # xe currency
    elif post.author=='"Xe Rate Alerts" <xe@service.xe.com>':
        html = post.summary
        soup = BeautifulSoup(html, 'html.parser')
        
        title = soup.find_all('h2')[1].text
        item['title'] = f"Today: {title}"
        item['description'] = post.summary if hasattr(post,'summary') else post.title
        item['pubDate'] = post.published if post.has_key('published') else datetime.now().astimezone().isoformat()
        item['link'] = ''
        item['author'] = post.author
    
    elif post.author=='"Longtermtrends" <info@longtermtrends.net>':
        html = post.summary
        soup = BeautifulSoup(html, 'lxml')

        # remove header
        soup = remove_tags(soup, 'tr', class_="header")
        soup.find('img', alt="Longtermtrends").find_parent('table').find_parent('table').decompose()
        # change size
        soup.find('table', width="800")['width']="100%"
        # remove color
        content=str(soup)
        content = re.sub('bgcolor="[#]?.{6}"','',content)

        item['description'] = content
        item['link'] = 'https://www.longtermtrends.net/newsletter/'
        item['title'] = f"Long-term Trend: {post.title}"
        item['pubDate'] = post.published if post.has_key('published') else datetime.now().astimezone().isoformat()
        item['author'] = post.author

    else:
        item['title'] = post.title
        item['description'] = post.summary if hasattr(post,'summary') else post.title
        item['pubDate'] = post.published if post.has_key('published') else datetime.now().astimezone().isoformat()
        item['link'] = post.link if hasattr(post,'link') else ''
        item['author'] = post.author if post.has_key('author') else ''
    
    return item

@feed('/ymail/<category>')
def ctx(category=''):
    """Yahoo mail folder via RSSHub's IMAP route; /ymail/market = "Market"."""
    # /ymail/market  --> ymail "Market" folder
    feed_url = f"http://192.168.1.2:1200/mail/imap/jerrywhatsoever@yahoo.com/{category.title()}"
    feed = feedparser.parse(fetch(feed_url, via='requests').html)
    
    # feed level
    title = 'Ymail' # feed.feed.title
    link = feed.feed.link
    description = feed.feed.subtitle if feed.feed.has_key('subtitle') \
        else feed.feed.title
    author = feed.feed.author if feed.feed.has_key('author') \
        else feed.feed.generator if feed.feed.has_key('generator') \
        else title
    posts = feed.entries

    return {
        'title': title,
        'link': link,
        'description': description,
        'author': 'Jerry',
        'items': list(map(parse, posts)) 
    }  
