from datetime import datetime
from feeds import feed
from fetch import fetch
from utils import to_html

domain = 'https://www.fidelity.com'

@feed('/fidelity/<category>')
def ctx(category=''):
    """Fidelity market updates: weekly | quarterly | ideas."""
    routes = {
        'weekly': f"{domain}/learning-center/trading-investing/weekly-market-update",
        'quarterly': f"{domain}/viewpoints/market-and-economic-insights/quarterly-market-update",
        'ideas': f"{domain}/learning-center/trading-investing/qsiru",
    }
    url = routes[category]
    
    soup = fetch(url, via='browser').soup

    item = {}
    item['title'] = soup.find('h1').text
    item['link'] = url
    item['pubDate'] = datetime.strptime(soup.find('div',attrs={'itemprop': 'datePublished'}).text.strip(), "%B %d, %Y")

    content = []
    ad = soup.find('div',attrs={'class':'Call-Out-Part'})
    subtitle = soup.find('div', attrs={'class': 'article-teaser-paragraph'})
    author = soup.find('div', attrs={"itemprop": "author"})
    summary = soup.find('div', attrs={"class": "article-below-image"})
    article = soup.find('div', attrs={"id": "article-template-body"})
    
    if ad:
        ad.decompose()
    if subtitle:
        content.append(to_html(subtitle))
        content.append('<br>')
        # content.append('<br>'*2)
    if author:
        content.append(f"<i>{to_html(author)}</i>")
    if summary:
        content.append(to_html(summary))
    if article:
        content.append(to_html(article))
    
    content = ''.join(content) 
    item['description'] = content
    
    return {
        'title': f'Fidelity {category.title()}',
        'link': url,
        'description': f'Fidelity Market {category.title()}',
        'author': 'jerry',
        'items': [item]
    }
