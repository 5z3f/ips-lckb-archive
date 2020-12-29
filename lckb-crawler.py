__author__                  = 'agsvn'

import requests
import json
import ehp
import json
import bs4
import os
import urllib

config = {
    'start_at': 1,
    'end_at': 15000, # latest is 14XXX
    'avatars': False,
    'cookies': {
        'ips4_member_id': '',
        'ips4_device_key': '',
        'ips4_login_key': ''
    }
}

headers = {
    'Cookie': f"ips4_device_key={config['cookies']['ips4_device_key']}; ips4_member_id={config['cookies']['ips4_member_id']}; ips4_login_key={config['cookies']['ips4_login_key']}"
}

def util_between(st, e, s):
    return (str(s).split(st))[1].split(e)[0]

def util_replace_all(t, d):
    for i, j in d.items():
        t = t.replace(i, j)
    return t

def util_get_ldjson(h):
    s = bs4.BeautifulSoup(h, "html.parser") # rewrite to ehp
    return [x.find_all(text=True)[0] for x in s.find_all('script', {'type': 'application/ld+json'})]

def get_avatar_by_id(id):
    r = requests.get(f'https://lckb.dev/forum/index.php?/profile/{id}-x/')
    ldjson = util_get_ldjson(r.text)
    return json.loads(ldjson[0])['primaryImageOfPage']['contentUrl']

def get_thread_by_id(id):
    r = requests.get(f'https://lckb.dev/forum/index.php?/topic/{id}-x', headers=headers)

    thread_html_data = []
    thread_json_data = []
    thread_html_title = util_between("<title>", '</title>', r.text)

    print(f'Thread ID: {id} | Title: {thread_html_title}')

    keyword_failed = [
        'Sorry, we could not find that!', 
        'Sorry, you do not have permission for that!', 
        '403 Forbidden', # 1904 ID
        #'520: Web server is returning an unknown error'
    ]

    if any(x in thread_html_title for x in keyword_failed):
        with open(f'error-ids.txt', 'a+') as f:
            f.write(f"{thread_id} | {thread_html_title}\n")
        return False
    else: 
        fp_json_data = util_get_ldjson(r.text)
        temp_page_json = json.loads(fp_json_data[0])

        last_page = temp_page_json['pageEnd']
        page_url = temp_page_json["url"]

        if 'ipsPagination_page' in r.text:        
            for page_id in range(1, last_page+1):
                r = requests.get(f'{page_url}page/{page_id}/', headers=headers)
                thread_html_data.append(r.text)
                thread_json_data.append(util_get_ldjson(r.text))
        else: 
            thread_html_data.append(r.text)
            thread_json_data.append(fp_json_data)

    return {'html': thread_html_data, 'json': thread_json_data}

for thread_id in range(config['start_at'], config['end_at']):
    data = get_thread_by_id(thread_id)

    if data == False:
        continue

    thread_json_data = json.loads(data['json'][0][0])
    position_json_data = json.loads(data['json'][0][3])

    thread_data = {
        'meta': {
            'threadId': thread_id,
            'threadName': thread_json_data['name'],
            'dateCreated': thread_json_data['dateCreated'],
            'datePublished': thread_json_data['datePublished'],
            'pageCount': thread_json_data['pageEnd'],
            'originalUrl': thread_json_data['url']
        }
    }

    try:                author_id = int(util_between('profile/', '-', thread_json_data['author']['url'])) 
    except KeyError:    author_id = None

    thread_data['meta']['authorId'] = author_id
    thread_data['meta']['position'] = position_json_data['itemListElement']

    thread_data_comment_content = []

    for i, html in enumerate(data['html']):
        dom = ehp.Html().feed(html)
        for j, html_comment in enumerate(dom.find('div', ('data-controller', 'core.front.core.comment'))):
            quote_data_json = json.loads(util_between('data-quotedata="', '" class', html_comment))

            dom_comment = ehp.Html().feed(str(html_comment))
            for x in dom_comment.find('div', ('data-role', 'commentContent')):
                html_comment_content = x

            user_id = quote_data_json['userid']
            author_name = quote_data_json['username']
            comment_id = quote_data_json['contentcommentid']

            if config['avatars']:
                if user_id is not None:
                    image_data = get_avatar_by_id(user_id) # rewrite to get from html instead of making new request
                    if 'https://' in image_data:
                        file_extension = image_data.split('/')[-1].split('.')[-1]
                        image_directory = f"data/avatars/{user_id}.{file_extension}"
                        if os.path.exists(image_directory) == False:
                            with open(image_directory, 'wb') as f:
                                f.write(requests.get(image_data).content)
                        image_data = f'/{image_directory}'
                    else:
                        image_data = urllib.parse.unquote(image_data)
                else:
                    image_data = None
                    
            thread_data_comment_content.append(
            {
                'id': quote_data_json['contentcommentid'],
                'timestamp': quote_data_json['timestamp'],
                'author': {
                    'id': user_id,
                    'name': author_name,
                    'image': image_data if config['avatars'] else None
                },
                'comment': str(html_comment_content).replace(u'\xa0', ' ').replace('<div data-role="commentContent" class="ipsType_normal ipsType_richText ipsContained" data-controller="core.front.core.lightboxedImages" >\n\t\t\t', '').replace('\n\n\t\t\t\n\t\t</div>', '')
            })

    thread_data['commentData'] = thread_data_comment_content

    with open(f'data/{thread_id}.json', 'w+') as f:
        f.write(json.dumps(thread_data, indent=4))
