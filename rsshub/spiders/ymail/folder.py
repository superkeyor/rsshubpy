import requests 
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, extract_html
import re

def parse(post):
    item = {}
    # fidelity
    if post.author=='"Fidelity Investments" <Fidelity.Alerts@Fidelity.com>':
        item['title'] = post.title
        item['pubDate'] = post.published if post.has_key('published') else arrow.now().isoformat()
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
        
        content.append(extract_html(market))
        content.append('<hr>')
        content.append(extract_html(news))
        content.append(extract_html(news2))
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
        item['pubDate'] = post.published if post.has_key('published') else arrow.now().isoformat()
        item['link'] = ''
        item['author'] = post.author
        
    else:
        item['title'] = post.title
        item['description'] = post.summary if hasattr(post,'summary') else post.title
        item['pubDate'] = post.published if post.has_key('published') else arrow.now().isoformat()
        item['link'] = post.link if hasattr(post,'link') else ''
        item['author'] = post.author if post.has_key('author') else ''
    
    return item

def ctx(category=''):
    # /ymail/market  --> ymail "Market" folder
    feed_url = f"http://192.168.1.2:1200/mail/imap/you@yahoo.com/{category.title()}"
    res = requests.get(feed_url,headers=DEFAULT_HEADERS,verify=False)
    feed = feedparser.parse(res.text)
    
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
