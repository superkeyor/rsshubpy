import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, fetch, extract_html

domain = 'https://digital.fidelity.com/prgw/digital/research'

def fidelity_market_screenshot(HEADED=True, DEBUG=True):
    from bs4 import BeautifulSoup
    from seleniumbase import SB
    base_url='https://digital.fidelity.com/prgw/digital/research'
    imgs = {}
    with SB(headless=True, headed=HEADED, maximize=True,
            undetectable=True, uc_cdp_events=True, driver_version="keep", 
            incognito=False, mobile=False, disable_csp=True, ad_block=True, 
            user_data_dir=None) as sb:
        label="market"; url=f"{base_url}/market"; selector=".market-chart-container"
        sb.activate_cdp_mode(url)
        sb.wait_for_element(selector, timeout=60)
        sb.connect()
        sb.scroll_into_view(selector)
        sb.wait(3)
        imgs[label]=sb.driver.find_element(selector).screenshot_as_base64

        label="sector"; url=f"{base_url}/sector"; selector="#market-sector-performance-table"
        sb.disconnect()
        sb.cdp.open(url)
        sb.wait_for_element(selector, timeout=60)
        sb.connect()
        sb.execute_script("""
            // Get the table element
            var table = document.getElementById('market-sector-performance-table');
            // Function to process text nodes
            function processTextNodes(node) {
                if (node.nodeType === 3) {  // Text node
                    // Replace the text
                    node.textContent = node.textContent.replace(/S&P 500 Financials Sector/g, "Financials");
                    node.textContent = node.textContent.replace(/S&P 500 Real Estate Sector/g, "Real Estate");
                    node.textContent = node.textContent.replace(/S&P 500 Consumer Discretionary Sector/g, "Cons. Disc.");
                    node.textContent = node.textContent.replace(/S&P 500 Information Technology Sector/g, "Info Tech.");
                    node.textContent = node.textContent.replace(/S&P 500 Industrials Sector/g, "Industrials");
                    node.textContent = node.textContent.replace(/S&P 500 Materials Sector/g, "Materials");
                    node.textContent = node.textContent.replace(/S&P 500 Consumer Staples Sector/g, "Cons. Stap.");
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
            return "Text in table replaced successfully!";
        """)
        # Ensure the entire table is in view for screenshot
        sb.execute_script("""
            // Get the table element
            var table = document.getElementById('market-sector-performance-table');
            // Get table dimensions
            var rect = table.getBoundingClientRect();
            // If table is larger than viewport, adjust the view
            if (rect.height > window.innerHeight) {
                // Scroll to position where we can see the whole table
                // or at least maximize visibility
                window.scrollTo({
                    top: Math.max(0, table.offsetTop - 50),
                    behavior: 'smooth'
                });
                // Give time for scrolling to complete
                return new Promise(resolve => setTimeout(resolve, 500));
            }
        """)
        sb.scroll_into_view(selector)
        sb.wait(3)
        imgs[label]=sb.driver.find_element(selector).screenshot_as_base64

        label="mover"; url=f"{base_url}/src/overview"; selector=".pvd3-table-root"
        sb.disconnect()
        sb.cdp.open(url)
        sb.wait_for_element(selector, timeout=60)
        sb.connect()
        sb.scroll_into_view(selector)
        sb.wait(3)
        imgs[label]=sb.driver.find_element(selector).screenshot_as_base64
        
        source = sb.get_page_source()
        soup = BeautifulSoup(source, "lxml")
        import re
        from datetime import datetime
        text = soup.find('research-card').text
        pattern = r"As of ([A-Za-z]{3}-\d{1,2}-\d{4} \d{1,2}:\d{2} [AP]M ET) \|"
        match = re.search(pattern, text)
        if match:
            date_time_str = match.group(1)
            pubDate = datetime.strptime(date_time_str, "%b-%d-%Y %I:%M %p ET")
        else:
            pubDate = datetime.now()

        html=''
        for k in imgs:
            img = imgs[k]
            html += f'<img alt="{k}" src="data:image/png;base64,{img}"><br>'
        if DEBUG: print(html,file=open('snapshot.html','w'))
        # n(next), s(step), c(continue), q(quit)
        if DEBUG: import pdb; pdb.set_trace()
        return html, pubDate

def ctx(category=''):
    content, pubDate = fidelity_market_screenshot(HEADED=False, DEBUG=False)
    item = {}
    item['title'] = f'Fidelity Market: {pubDate.strftime("%b-%d-%Y %I:%M %p ET")}'
    item['link'] = f'{domain}'
    item['pubDate'] = pubDate
    item['id'] = f'{domain}#{pubDate.strftime("%b-%d-%Y")}'   # one post each day
    item['description'] = content
    
    return {
        'title': f'Fidelity Market',
        'link': domain,
        'description': f'Fidelity Market Screenshot',
        'author': 'Jerry',
        'items': [item]
    }
