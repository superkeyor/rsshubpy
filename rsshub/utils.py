import re
from flask import Response
import requests
from parsel import Selector
import bs4
from bs4 import BeautifulSoup 

# https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
DEFAULT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'}

class XMLResponse(Response):
    def __init__(self, response, **kwargs):
        if 'mimetype' not in kwargs and 'contenttype' not in kwargs:
            if response.startswith('<?xml'):
                kwargs['mimetype'] = 'application/xml'
        return super().__init__(response, **kwargs)

def fetch(url: str, headers: dict=DEFAULT_HEADERS, proxies: dict=None):
    try:
        res = requests.get(url, headers=headers, proxies=proxies)
        res.raise_for_status()
    except Exception as e:
        print(f'[Err] {e}')
    else:
        html = res.text
        tree = Selector(text=html)
        return tree

def fetch_by_requests(url: str, headers: dict=DEFAULT_HEADERS, proxies: dict=None):
    try:
        res = requests.get(url, headers=headers, proxies=proxies)
        res.raise_for_status()
    except Exception as e:
        print(f'[Err] {e}')
    else:
        soup = BeautifulSoup(res.content, "lxml")
        return soup

# # manually setup chromium profile
# # https://github.com/seleniumbase/SeleniumBase/blob/master/seleniumbase/plugins/driver_manager.py#L66
# from seleniumbase import Driver
# driver = Driver(headless=False, headed=True, undetectable=True, uc_cdp_events=True, driver_version="keep", incognito=False, mobile=False, disable_csp=True, ad_block=True, user_data_dir="/home/parallels/Desktop/chromiumprofile")
# # https://nowsecure.nl/#relax   https://bot.sannysoft.com
# driver.open("https://bot.sannysoft.com")
# https://chromewebstore.google.com/detail/violentmonkey/jinjaccalgkegednnccohejagnlnfdag
# https://greasyfork.org/en/scripts/514737-bloomberg-paywall-bypass
# https://www.bloomberg.com/latest/markets-wrap

def fetch_by_browser(url, user_data_dir = None, HEADED = None, DEBUG = None):
    # https://github.com/seleniumbase/SeleniumBase/discussions/2118
    # run uc mode to manually set up profile; profile folder should be nonexistent
    # then it will be created by uc and not be deleted even after closing the browser
    # https://nowsecure.nl/#relax   https://bot.sannysoft.com
    import os
    # print(list(os.environ.items()))
    # vmd
    if os.getenv('FLASK_ENV') == "development" and 'XDG_CURRENT_DESKTOP' in os.environ:
        home = os.path.expanduser("~")
        if user_data_dir is None: user_data_dir = f"{home}/Desktop/chromiumprofile"
        os.system(f"rm -rf {user_data_dir}")
        os.system(f"cp -r {home}/Desktop/rsshub_python/rsshub/chromiumprofile {user_data_dir}")
        if HEADED is None: HEADED = True
        if DEBUG is None: DEBUG = True
    # vmo
    elif os.getenv('FLASK_ENV') == "development" and 'XDG_CURRENT_DESKTOP' not in os.environ:
        home = os.path.expanduser("~")
        if user_data_dir is None: user_data_dir = f"{home}/chromiumprofile"
        os.system(f"rm -rf {user_data_dir}")
        os.system(f"cp -r {home}/rsshub_python/rsshub/chromiumprofile {user_data_dir}")
        if HEADED is None: HEADED = False
        if DEBUG is None: DEBUG = False
    else:
        if user_data_dir is None: user_data_dir = "/app/rsshub/chromiumprofile"
        if HEADED is None: HEADED = False
        if DEBUG is None: DEBUG = False

    # https://github.com/seleniumbase/SeleniumBase/blob/master/seleniumbase/plugins/sb_manager.py
    # https://seleniumbase.io/examples/cdp_mode/ReadMe/#cdp-mode-usage
    from seleniumbase import SB
    with SB(headless=True, headed=HEADED, maximize=True,
            undetectable=True, uc_cdp_events=True, driver_version="keep", 
            incognito=False, mobile=False, disable_csp=True, ad_block=True, 
            user_data_dir=user_data_dir) as sb:
        sb.activate_cdp_mode(url)
        source = sb.get_page_source()
        soup = BeautifulSoup(source, "lxml")
        url = sb.get_current_url()
        title = sb.get_page_title()
        # n(next), s(step), c(continue), q(quit)
        if DEBUG: import pdb; pdb.set_trace()
        return soup, source, url, title

async def fetch_by_puppeteer(url):
    try:
        from pyppeteer import launch
    except Exception as e:
        print(f'[Err] {e}')
    else:
        browser = await launch(  # 启动浏览器
            {'args': ['--no-sandbox']},
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False
        )
        page = await browser.newPage()  # 创建新页面
        await page.goto(url)  # 访问网址
        html = await page.content()  # 获取页面内容
        await browser.close()  # 关闭浏览器
        return Selector(text=html)

def extract_html(element):
    """
    element: a soup find object, or find_all object
    """
    if element is None:
        return ""
    else:
        if type(element) in [bs4.element.ResultSet, list]:
            return ''.join([str(e) for e in element])
        else:
            return str(element)

def escape_html(html_content):
    """
    Escape unescaped HTML tags while preserving already escaped characters.
    """
    import html
    html_content = str(html_content)
    # Regex to match unescaped HTML tags
    pattern = re.compile(r"(?<!&lt;)(<[^>]+>)(?!&gt;)")
    # Replace unescaped tags with their escaped versions
    escaped_content = pattern.sub(lambda match: html.escape(match.group(0)), html_content)
    return escaped_content

def decompose_element(soup, *args, **kwargs):
    """
    all parameters go to soup.find_all()
    returns new soup
    """
    elements=soup.find_all(*args, **kwargs)
    if len(elements)>0: 
        for e in elements:
            e.decompose()
    return soup

def filter_content(items):
    content = []
    p1 = re.compile(r'(.*)(to|will|date|schedule) (.*)results', re.IGNORECASE)
    p2 = re.compile(r'(.*)(schedule|schedules|announce|to) (.*)call', re.IGNORECASE)
    p3 = re.compile(r'(.*)release (.*)date', re.IGNORECASE)

    for item in items:
        title = item['title']
        if p1.match(title) or p2.match(title) or p3.match(title):
            content.append(item)
    return content
