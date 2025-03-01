import re
from flask import Response
import requests
from parsel import Selector
import bs4

DEFAULT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}


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
