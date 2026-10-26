import json
import re
from datetime import datetime
from feeds import feed
from browser import window

domain = 'https://digital.fidelity.com/prgw/digital/research'

# Shorten the sector names in the sector performance table before the screenshot
SECTOR_LABELS_JS = """(() => {
            // Get the table element
            var table = document.getElementById('market-sector-performance-table');
            // Function to process text nodes
            function processTextNodes(node) {
                if (node.nodeType === 3) {  // Text node
                    // Replace the text
                    node.textContent = node.textContent.replace(/S&P 500 Financials Sector/g, "Financials");
                    node.textContent = node.textContent.replace(/S&P 500 Real Estate Sector/g, "Real Estate");
                    node.textContent = node.textContent.replace(/S&P 500 Consumer Discretionary Sector/g, "Cons. Disc. Y");
                    node.textContent = node.textContent.replace(/S&P 500 Information Technology Sector/g, "Info Tech.");
                    node.textContent = node.textContent.replace(/S&P 500 Industrials Sector/g, "Industrials");
                    node.textContent = node.textContent.replace(/S&P 500 Materials Sector/g, "Materials");
                    node.textContent = node.textContent.replace(/S&P 500 Consumer Staples Sector/g, "Cons. Stap. P");
                    node.textContent = node.textContent.replace(/S&P 500 Health Care Sector/g, "Health Care");
                    node.textContent = node.textContent.replace(/S&P 500 Energy Sector/g, "Energy");
                    node.textContent = node.textContent.replace(/S&P 500 Communication Services Sector/g, "Comm. Serv.");
                    node.textContent = node.textContent.replace(/S&P 500 Utilities Sector/g, "Utilities");
                    node.textContent = node.textContent.replace(/S&P 500/g, "-------------------");
                } else {
                    // Process child nodes recursively
                    for (var i = 0; i < node.childNodes.length; i++) {
                        processTextNodes(node.childNodes[i]);
                    }
                }
            }
            // Process all text nodes in the table
            processTextNodes(table);
            return true;
})()"""

# Bring the whole sector table into view (scroll so its top is near the top of the viewport)
SECTOR_SCROLL_JS = """(async () => {
    var table = document.getElementById('market-sector-performance-table');
    var rect = table.getBoundingClientRect();
    if (rect.height > window.innerHeight) {
        window.scrollTo({top: Math.max(0, table.offsetTop - 50), behavior: 'smooth'});
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    return true;
})()"""


def navigate_to_target(page, url, selector):
    """CDP: open url, wait for selector and scroll it into view, then let the page settle."""
    page.open(url)
    page.wait(selector, timeout=60)
    page.sleep(3)


def shoot(page, selector):
    """
    UC/WebDriver element screenshot as base64 (SeleniumBase native, as in the original code:
    sb.driver.find_element(selector).screenshot_as_base64) plus the element's text as shown on screen.
    """
    element = page.driver.find_element('css selector', selector)
    return element.screenshot_as_base64, element.text


def fidelity_market_screenshot():
    """
    Screenshots of 4 Fidelity research elements in one window: CDP for navigation, UC/WebDriver for the
    screenshots, like the original navigate_to_target + reconnect. Returns (html, pubDate, texts).
    """
    imgs, texts = {}, {}
    with window(domain, uc=True, timeout=480) as page:
        label="market"; url=f"{domain}/market"; selector=".market-chart-container"
        navigate_to_target(page, url, selector)
        imgs[label], texts[label] = shoot(page, selector)

        label="sector"; url=f"{domain}/sector"; selector="#market-sector-performance-table"
        navigate_to_target(page, url, selector)
        page.js(SECTOR_LABELS_JS)
        # Ensure the entire table is in view for screenshot
        page.js(SECTOR_SCROLL_JS)
        page.wait(selector)
        page.sleep(3)
        imgs[label], texts[label] = shoot(page, selector)

        # sector's date is the latest, so we can use it as the pubDate for the whole website
        text = page.soup().find('research-card').text
        pattern = r"As of ([A-Za-z]{3}-\d{1,2}-\d{4} \d{1,2}:\d{2} [AP]M ET) \|"
        match = re.search(pattern, text)
        if match:
            date_time_str = match.group(1)
            pubDate = datetime.strptime(date_time_str, "%b-%d-%Y %I:%M %p ET")
        else:
            pubDate = datetime.now()

        label="mover"; url=f"{domain}/src/overview"; selector=".src-market-movers-card-div"
        navigate_to_target(page, url, selector)
        imgs[label], texts[label] = shoot(page, selector)

        label="order"; selector=".orders-padding"
        # originally the same page was loaded a second time:
        # label="order"; url=f"{base_url}/src/overview"; selector=".orders-padding"
        # navigate_to_target(sb, url, selector)   # = open + wait for selector + scroll + sb.wait(3)
        # now: it is already open (movers), so only scroll to it and wait the same 3s
        page.wait(selector)
        page.sleep(3)
        imgs[label], texts[label] = shoot(page, selector)

    html=''
    for k in imgs:
        img = imgs[k]
        html += f'<img alt="{k}" width="100%" src="data:image/png;base64,{img}"><br>'
    return html, pubDate, texts

@feed('/fidelity/market')
def ctx(category=''):
    """Fidelity research screenshots: market, sector, movers, orders (browser)."""
    content, pubDate, texts = fidelity_market_screenshot()
    item = {}
    item['title'] = f'Fidelity Market: {pubDate.strftime("%b-%d-%Y %I:%M %p ET")}'
    item['link'] = f'{domain}'
    item['pubDate'] = pubDate
    item['id'] = f'{domain}#{pubDate.strftime("%b-%d-%Y")}'   # one post each day
    item['description'] = content
    
    return {
        # Same on-screen text = same content: the cached copy is kept, so new screenshot bytes alone do not
        # show up as an update in the reader (feedcache). Replaces the old cache_content(...) per pubDate.
        'fingerprint': json.dumps(texts, ensure_ascii=False),
        'title': f'Fidelity Market',
        'link': domain,
        'description': f'Fidelity Market Screenshot',
        'author': 'Jerry',
        'items': [item]
    }
