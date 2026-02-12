import requests 
import feedparser
import arrow
from bs4 import BeautifulSoup
from rsshub.utils import DEFAULT_HEADERS, extract_html, fetch_by_browser
import re, json, os

from opencc import OpenCC
cc = OpenCC('t2s')  # t2s = Traditional to Simplified

# https://github.com/DIYgod/RSSHub/blob/master/lib/routes/xueqiu/hots.ts
domain = 'https://xueqiu.com'

def avg_text_len_between_br(content):
    """
    Calculate average visible text length between <br> tags.
    For easier reading: if average text segment between <br> tags is long enough, double all single <br>.
    """
    segments = re.split(r'<br\s*/?\s*>', content)
    if len(segments) > 1:
        visible_lengths = [len(re.sub(r'<[^>]+>', '', seg)) for seg in segments]
        return sum(visible_lengths) / len(visible_lengths)
    return 0

def ctx(category=''):
    url1 = f"{domain}" # set cookie first
    url2 = f"{domain}/statuses/hots.json?a=1&count=10&page=1&scope=day&type=status&meigu=0"
    soups, sources, urls, titles = fetch_by_browser([url1, url2], wait=30)
    items=json.loads(soups[1].text)
    
    posts = []
    for item in items:
        post={}

        post['author'] = cc.convert(item['user']['screen_name'])
        post['link'] = f"{domain}{item['target']}"
        post['id'] = post['link']
        post['pubDate'] = arrow.get(item['created_at']).isoformat()
        
        content = cc.convert(item['text'])
        if avg_text_len_between_br(content) > 22:
            content=re.sub(r'<br\s*/?\s*>(?!<br)', '<br><br>', content) # easier reading
        # 回复<a href="https://xueqiu.com/n/持股待涨养家糊口" target="_blank">@持股待涨养家糊口</a>: 
        content=re.sub(r'回复<a href="https://xueqiu\.com/n/[^"]*"[^>]*>@[^<]*</a>:\s*', '', content)
        content=re.sub(r'//<a href="https://xueqiu\.com[^"]*"[^>]*>(@[^<]*)</a>:', r'//\1<br>', content)
        content=re.sub(r'<a href="https://xueqiu\.com[^"]*"[^>]*>([^<]*)</a>', r'\1', content)
        
        title=content.split("//@")
        if len(title)==1:
            post['title'] = f"{post['author']}: {BeautifulSoup(title[0],'lxml').text.replace('$','')[:20]}"
        else:
            post['title'] = f"{post['author']}: Re:{title[1].split('<br>')[0][:10]} {BeautifulSoup(title[0],'lxml').text.replace('$','')[:20]}"

        icomment=f"↴{item['reply_count']}" if item['reply_count']>0 else ""
        ilike=f"↑{item['like_count']}" if item['like_count']>0 else ""
        author_info = f"💭 {post['author']} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {icomment} {ilike}"
        
        content=content.replace('//@', '<br><br>🔃 ')
        # starts with <p> (if there is <p>, likely starts with <p>, or no <p> at all)
        if re.search(r'<p[^>]*>', content):
            content=re.sub(r'(<p[^>]*>)', r'\1' + f"{author_info}<br>", content, count=1)
        else:
            content=f"{author_info}<br>{content}"
        # ends with </p>
        if content.endswith('</p>'):
            content=f"{content}<br>"
        else:
            content=f"{content}<br><br>"

        # excellent comments
        try:
            comment=''
            if len(item['excellent_comments']) > 0:
                cauthor = cc.convert(item['excellent_comments'][0]['user']['screen_name'])
                ccoment = cc.convert(item['excellent_comments'][0]['text'])
                if avg_text_len_between_br(ccoment) > 22:
                    ccoment=re.sub(r'<br\s*/?\s*>(?!<br)', '<br><br>', ccoment) # easier reading
                comment = f"💬 {cauthor}<br>{ccoment}<br><br>"
            content = content + comment
        # KeyError: 'excellent_comments'
        except: 
            pass

        post['description'] = content + f'<div align="right"><a href="{post["link"]}" target="_blank">阅读原文</a></div>'
        
        # print(list(os.environ.items()))
        if os.getenv('FLASK_ENV') == "development": 
            with open('rsshub/blocker.json', 'r') as file:
                blocker = json.load(file)
                print(blocker)
        else:
            blocker = requests.get("https://raw.githubusercontent.com/superkeyor/rsshub_python/refs/heads/master/rsshub/blocker.json").json()
        def regex_match(text, keywords):
            """Helper function to check if any of the keywords match the text using regex."""
            for keyword in keywords:
                if re.search(keyword, text):
                    return True
            return False
        if ( not regex_match(post['author'], blocker['xueqiu']['author']) ) and \
           ( not regex_match(post['title'], blocker['xueqiu']['title']) ) and \
           ( not regex_match(post['description'], blocker['xueqiu']['content']) ):
            posts.append(post)
        
    return {
        'title': "雪球",
        'link': "https://xueqiu.com",
        'description': "雪球热门帖子\nhttps://github.com/superkeyor/rsshub_python/edit/master/rsshub/blocker.json",
        'author': 'Jerry',
        'items': posts 
    }  
