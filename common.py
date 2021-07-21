from pixivpy3 import PixivAPI, AppPixivAPI
from pixiv_auth import refresh
import sqlite3
from enum import IntEnum, Enum
import json
from threading import Thread
import init
import time
from urllib.parse import urljoin
#from joblib import Parallel, delayed
import os
from elasticsearch import Elasticsearch
import re
import subprocess
import evaluators as evals


class AgeLimit(IntEnum):
    ALL_AGE = 0
    R_18 = 1


class APIType(IntEnum):
    PIXIV = 0


class StatusCode(IntEnum):
    SCCESS = 0
    ERROR = 1
    WARNING = 2


class IllustSort(IntEnum):
    DEFAULT = 0
    RANDOM = 1
    LIKES = 2
    TIME = 3


class Paths(Enum):
    IMG_DIR = 'static/img/%s'
    USER_DIR = 'static/user/%s'


class Fnames(Enum):
    AVATAR = 'avatar'
    IMAGE = 'p%d_%s.%s'


class Keys(Enum):
    ILLUST_ID = 'illust_id'
    USER_ID = 'user_id'


class Indexes(Enum):
    ILLUSTS = 'purex_illusts'
    USERS = 'purex_users'


class JsonDict:
    def __init__(self, filename):
        self.filename = filename
        self.read()

    def read(self):
        with open(self.filename) as f:
            self.value = json.loads(f.read())

    def write(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(json.dumps(self.value, ensure_ascii=False, indent=4))

    def get(self, key):
        return self.value[key]

    def set(self, key, value):
        self.value[key] = value
        self.write()


class APIError(Exception):
    def __init__(self, message):
        status = 101
        super().__init__(message, status)
        self.message = message
        self.status = status


class IdNotFoundError(ValueError):
    def __init__(self, message):
        status = 102
        super().__init__(message, status)
        self.message = message
        self.status = status


class ConfigError(Exception):
    def __init__(self, message):
        status = 103
        super().__init__(message, status)
        self.message = message
        self.status = status


history = JsonDict('data/history.json')
CONFIG = JsonDict('config.json').value
pixiv_reftoken = CONFIG['pixiv_api']['refresh_token']
pixiv_acctoken = None

aapi = AppPixivAPI()
aapi.set_accept_language(CONFIG['pixiv_api']['accept_language'])

api_tries = [0.1, 0.5, 1, 3, 10, None]


def get_id(type):
    history.read()
    ids = history.value['ids']
    if type in ids:
        ids[type] += 1
    else:
        ids[type] = 0
    history.write()
    return str(ids[type])


def pixiv_token_thread():
    while True:
        time.sleep(3000)
        refresh_pixiv_token()


def refresh_pixiv_token():
    global pixiv_acctoken
    pixiv_acctoken = refresh(pixiv_reftoken)['access_token']
    aapi.set_auth(pixiv_acctoken, pixiv_reftoken)


refresh_pixiv_token()
Thread(target=pixiv_token_thread, daemon=True).start()

es = Elasticsearch(CONFIG['elasticsearch']['hosts'],
                   http_auth=CONFIG['elasticsearch']['auth'])

if not es.indices.exists(Indexes.ILLUSTS.value):
    res = es.indices.create(Indexes.ILLUSTS.value, body={
        'mappings': {
            'properties': {
                'title': {
                    'type': 'text',
                    'index': False
                },
                'caption': {
                    'type': 'text',
                    'index': False
                },
                'type': {
                    'type': 'byte'
                },
                'user': {
                    'type': 'integer'
                },
                'type_id': {
                    'type': 'integer'
                },
                'type_tags': {
                    'type': 'text',
                    'analyzer': 'whitespace'
                },
                'original_tags': {
                    'type': 'text',
                    'index': False
                },
                'searched': {
                    'type': 'text',
                    'analyzer': 'ik_max_word',
                    'search_analyzer': 'ik_smart'
                },
                'image_urls': {
                    'type': 'text',
                    'index': False
                },
                'image_exts': {
                    'type': 'text',
                    'index': False
                },
                'type_likes': {
                    'type': 'integer'
                },
                'publish_time': {
                    'type': 'date'
                },
                'age_limit': {
                    'type': 'byte'
                },
                'downloaded': {
                    'type': 'boolean'
                },
                'passed_evals': {
                    'type': 'text',
                    'analyzer': 'whitespace'
                },
                'tested_evals': {
                    'type': 'text',
                    'analyzer': 'whitespace'
                }
            }
        },
        'settings': {
            'refresh_interval': '60s'
        }
    })

if not es.indices.exists(Indexes.USERS.value):
    res = es.indices.create(Indexes.USERS.value, body={
        'mappings': {
            'properties': {
                'name': {
                    'type': 'text',
                    'analyzer': 'ik_max_word',
                    'search_analyzer': 'ik_smart'
                },
                'account': {
                    'type': 'text'
                },
                'type': {
                    'type': 'byte'
                },
                'type_id': {
                    'type': 'integer'
                },
                'total_illusts': {
                    'type': 'integer'
                },
                'comment': {
                    'type': 'text',
                    'index': False
                },
                'avatar_url': {
                    'type': 'text',
                    'index': False
                }
            }
        },
        'settings': {
            'refresh_interval': '3s'
        }
    })

evaluators = [
    {
        'name': 'quality_v1',
        'enable': False,
        'eval': evals.quality_v1.eval,
        'show_name': '质量v1'
    }
]

class Illust:
    def __init__(self, from_id=None, pixiv_info=None, pixiv_id=None):
        if from_id is not None:
            self.id = from_id
            self.read()
        elif pixiv_info is not None:
            self.load_from_pixiv(pixiv_info)
        elif pixiv_id is not None:
            hits = es.search({
                'query': {'bool': {'filter': [
                    {'term': {
                        'type': APIType.PIXIV.value,
                    }},
                    {'term': {
                        'type_id': pixiv_id
                    }}
                ]}},
                'size': 1,
                '_source': []
            }, Indexes.ILLUSTS.value)['hits']['hits']
            if hits:
                self.id = hits[0]['_id']
                self.read()
            else:
                for i in api_tries:
                    try:
                        resp = aapi.illust_detail(pixiv_id)
                        if resp.error:
                            raise APIError(resp.error.message)
                        break
                    except:
                        if i is not None:
                            time.sleep(i)
                        else:
                            raise APIError('get illust_detail failed')
                if resp.error:
                    raise APIError(resp.error.message)
                self.load_from_pixiv(resp.illust)
        else:
            raise Exception()

    def load_from_pixiv(self, info):
        self.id = get_id(Keys.ILLUST_ID.value)
        self.raw_json = info
        self.title = info.title
        self.type = APIType.PIXIV
        self.user = User(pixiv_id=info.user.id)
        self.type_id = info.id
        self.type_tags = self.get_translated_tags(info.tags)
        self.origin_tags = [tag.name for tag in info.tags]
        self.image_urls = self.get_original_urls(info)
        self.image_exts = [url.split('.')[-1] for url in self.image_urls]
        self.type_likes = info.total_bookmarks
        self.caption = info.caption
        self.publish_time = round(time.mktime(time.strptime(
            info.create_date.replace(':', ''), '%Y-%m-%dT%H%M%S%z')))
        if info.x_restrict == 0:
            self.age_limit = AgeLimit.ALL_AGE
        elif info.x_restrict == 1:
            self.age_limit = AgeLimit.R_18
        else:
            raise Exception()
        self.downloaded = False
        self.passed_evals = []
        self.tested_evals = []
        self.write()

    def get_original_urls(self, info):
        if info.page_count == 1:
            return [info.meta_single_page.original_image_url]
        else:
            return [page.image_urls.original for page in info.meta_pages]

    def get_translated_tags(self, tags):
        cn = re.compile(r'[\u4e00-\u9fff]')
        jap = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7A3]')
        transtated = []
        for tag in tags:
            if tag.translated_name and cn.search(tag.translated_name):
                transtated.append(tag.translated_name)
            elif cn.search(tag.name) and (not jap.search(tag.name)):
                transtated.append(tag.name)
        return transtated

    def download(self):
        self.read()
        if self.downloaded:
            return
        scale_conf = CONFIG['image_scale']
        ddir = Paths.IMG_DIR.value % self.id
        pixel_numl = scale_conf['pixel_num']['large']
        pixel_numm = scale_conf['pixel_num']['medium']
        webpq = scale_conf['webp_q']
        jpgq = scale_conf['jpg_q']
        fname = Fnames.IMAGE.value
        if not os.path.exists(ddir):
            os.mkdir(ddir)
        for i in range(len(self.image_urls)):
            url = self.image_urls[i]
            ext = self.image_exts[i]
            oname = fname % (i, 'original', ext)
            opath = os.path.join(ddir, oname)
            if self.type == APIType.PIXIV:
                for j in api_tries:
                    try:
                        aapi.download(url, path=ddir, fname=oname)
                        break
                    except:
                        if j is not None:
                            time.sleep(i)
                        else:
                            raise APIError('download illust failed')
            else:
                raise Exception()
            for quality, pixel_num in ('large', pixel_numl), ('medium', pixel_numm):
                webp_out = os.path.join(ddir, fname % (i, quality, 'webp'))
                jpg_out = os.path.join(ddir, fname % (i, quality, 'jpg'))
                scale = "scale='min(iw, sqrt(%d/iw/ih)*iw)':-2" % pixel_num
                subprocess.run(['ffmpeg', '-i', opath, '-codec', 'libwebp', '-q', str(webpq),
                                '-vf', scale, webp_out, '-loglevel', 'error', '-y'], check=True)
                subprocess.run(['ffmpeg', '-i', opath, '-q', str(jpgq),
                                '-vf', scale, jpg_out, '-loglevel', 'error', '-y'], check=True)

        self.read()
        self.downloaded = True
        self.write()

    def read(self):
        info = es.get(Indexes.ILLUSTS.value, self.id)['_source']
        self.title = info['title']
        self.caption = info['caption']
        self.type = APIType(info['type'])
        self.user = User(from_id=info['user'])
        self.type_id = info['type_id']
        self.type_tags = info['type_tags'].split(' ')
        self.original_tags = json.loads(info['original_tags'])
        self.image_urls = json.loads(info['image_urls'])
        self.image_exts = json.loads(info['image_exts'])
        self.type_likes = info['type_likes']
        self.publish_time = info['publish_time']
        self.age_limit = AgeLimit(info['age_limit'])
        self.downloaded = info['downloaded']
        self.passed_evals = info['passed_evals'].split(' ')
        self.tested_evals = info['tested_evals'].split(' ')

    def write(self):
        es.index(Indexes.ILLUSTS.value, {
            'title': self.title,
            'caption': self.caption,
            'type': self.type.value,
            'user': self.user.id,
            'type_id': self.type_id,
            'type_tags': ' '.join(self.type_tags),
            'original_tags': json.dumps(self.origin_tags, ensure_ascii=False),
            'searched': ' '.join([self.title] + self.type_tags),
            'image_urls': json.dumps(self.image_urls, ensure_ascii=False),
            'image_exts': json.dumps(self.image_exts, ensure_ascii=False),
            'type_likes': self.type_likes,
            'publish_time': self.publish_time,
            'age_limit': self.age_limit.value,
            'downloaded': self.downloaded,
            'passed_evals': ' '.join(self.passed_evals),
            'tested_evals': ' '.join(self.tested_evals)
        }, id=self.id)

    def json(self):
        img_base_url = '/img/%s/' % self.id
        res = {
            'id': self.id,
            'title': self.title,
            'caption': self.caption,
            'type': self.type.value,
            'type_id': self.type_id,
            'tags': self.type_tags,
            'likes': self.type_likes,
            'publish_time': self.publish_time,
            'age_limit': self.age_limit.value,
            'user': self.user.json(),
            'downloaded': self.downloaded,
            'passed_evals': self.passed_evals
        }
        if self.downloaded:
            res['image_urls'] = []
            fname = Fnames.IMAGE.value
            for i in range(len(self.image_urls)):
                res['image_urls'].append({
                    'medium_webp': urljoin(img_base_url, fname % (i, 'medium', 'webp')),
                    'medium_jpg': urljoin(img_base_url, fname % (i, 'medium', 'jpg')),
                    'large_webp': urljoin(img_base_url, fname % (i, 'large', 'webp')),
                    'large_jpg': urljoin(img_base_url, fname % (i, 'large', 'jpg')),
                    'original': urljoin(img_base_url, fname % (i, 'original', self.image_exts[i]))
                })
        else:
            res['image_urls'] = None
        return res


class User:
    def __init__(self, from_id=None, pixiv_id=None):
        if from_id is not None:
            self.id = from_id
            self.read()
        elif pixiv_id is not None:
            hits = es.search({
                'query': {'bool': {'filter': [
                    {'term': {
                        'type': APIType.PIXIV.value,
                    }},
                    {'term': {
                        'type_id': pixiv_id
                    }}
                ]}},
                'size': 1,
                '_source': []
            }, Indexes.USERS.value)['hits']['hits']
            if hits:
                self.id = hits[0]['_id']
                self.read()
            else:
                self.load_from_pixiv(pixiv_id)
        else:
            raise Exception()

    def load_from_pixiv(self, pixiv_id):
        for i in api_tries:
            try:
                info = aapi.user_detail(pixiv_id)
                if info.error:
                    raise APIError(info.error.message)
                break
            except:
                if i is not None:
                    time.sleep(i)
                else:
                    raise APIError('get user_detail failed')
        user = info.user
        self.id = get_id(Keys.USER_ID.value)
        self.raw_json = info
        self.type = APIType.PIXIV
        self.name = user.name
        self.account = user.account
        self.comment = user.comment
        self.type_id = user.id
        self.avatar_url = user.profile_image_urls.medium
        self.total_illusts = info.profile.total_illusts
        self.download_avatar()
        self.write()

    def read(self):
        info = es.get(Indexes.USERS.value, self.id)['_source']
        self.name = info['name']
        self.type = APIType(info['type'])
        self.account = info['account']
        self.type_id = info['type_id']
        self.total_illusts = info['total_illusts']
        self.comment = info['comment']
        self.avatar_url = info['avatar_url']

    def write(self):
        es.index(Indexes.USERS.value, {
            'name': self.name,
            'type': self.type.value,
            'account': self.account,
            'type_id': self.type_id,
            'total_illusts': self.total_illusts,
            'comment': self.comment,
            'avatar_url': self.avatar_url
        }, id=self.id)

    def download_avatar(self):
        ddir = Paths.USER_DIR.value % self.id
        fname = Fnames.AVATAR.value
        if not os.path.exists(ddir):
            os.mkdir(ddir)
        if self.type == APIType.PIXIV:
            for i in api_tries:
                try:
                    aapi.download(self.avatar_url, path=ddir, fname=fname)
                    break
                except:
                    if i is not None:
                        time.sleep(i)
                    else:
                        raise APIError('download user avatar failed')
        else:
            raise Exception()

    def json(self):
        return {
            'id': self.id,
            'type': self.type.value,
            'type_id': self.type_id,
            'name': self.name,
            'account': self.account,
            'comment': self.comment,
            'avatar_url': urljoin('/user/%s/' % self.id, Fnames.AVATAR.value),
            'total_illusts': self.total_illusts
        }


def search_illusts(limit, offset=0, sort=IllustSort.DEFAULT, query=None):
    body = {
        'from': offset,
        'size': limit,
        '_source': []
    }
    if sort == IllustSort.RANDOM:
        body['sort'] = {"_script": {
            "script": "Math.random()",
            "type": "number",
            "order": "asc"
        }}
    elif sort == IllustSort.LIKES:
        body['sort'] = {"type_likes": {"order": "desc"}}
    elif sort == IllustSort.TIME:
        body['sort'] = {"publish_time": {"order": "desc"}}
    if query:
        must = []
        filter = []
        must_not = []
        body['query'] = {'bool': {'must': must, 'filter': filter, 'must_not': must_not}}
        if 'text' in query:
            must.append({'match': {'searched': query['text']}})
        if 'tags' in query:
            for tag in query['tags']:
                filter.append({'term': {'type_tags': tag}})
        if 'passed_evals' in query:
            for evaluator in query['passed_evals']:
                filter.append({'term': {'passed_evals': evaluator}})
        if 'not_tested_evals' in query:
            for evaluator in query['not_tested_evals']:
                must_not.append({'term': {'tested_evals': evaluator}})
        if 'downloaded' in query:
            filter.append({'term': {'downloaded': query['downloaded']}})
        if 'type' in query:
            filter.append({'term': {'type': query['type']}})
        if 'age_limit' in query:
            filter.append({'term': {'age_limit': query['age_limit']}})
    hits = es.search(body, Indexes.ILLUSTS.value)['hits']['hits']
    return [Illust(from_id=hit['_id']) for hit in hits]

def pixiv_loop_ranking():
    rank = CONFIG['pixiv_api']['ranking']
    illust_only = rank['illust_only']
    mode = rank['mode']
    limit = rank['limit']
    loop = rank['loop']
    rank_histories = history.value['pixiv_ranking']
    matched_hist = None
    ids = []
    for hist in rank_histories:
        if hist['mode'] == mode and hist['limit'] == limit:
            matched_hist = hist
            break
    if mode == 'month':
        loop_time = 30*24*60*60
    elif mode == 'week':
        loop_time = 7*24*60*60
    elif mode == 'day':
        loop_time = 24*60*60
    start_time = time.time()
    curtime = start_time + loop_time
    for i in range(loop):
        curtime -= loop_time
        if matched_hist and curtime < matched_hist['start'] and curtime > matched_hist['end']:
            continue
        date = time.strftime('%Y-%m-%d', time.localtime(curtime))
        print('updating:', date)
        illusts = []
        offset = 0
        date_err = False
        while len(illusts) < limit:
            for j in api_tries:
                try:
                    resp = aapi.illust_ranking(mode, date=date, offset=offset)
                    break
                except:
                    if j is not None:
                        time.sleep(i)
                    else:
                        raise APIError('illust_ranking failed')
            if resp.error:
                raise APIError(resp.error.message)
            if len(resp.illusts) == 0:
                date_err = True
                break
            for illust in resp.illusts:
                if illust_only and illust.type != 'illust':
                    continue
                if illust.id in ids:
                    continue
                illusts.append(Illust(pixiv_info=illust))
                ids.append(illust.id)
            offset += 30
        if date_err:
            start_time -= loop_time
            continue
        download_batch(illusts)
    if matched_hist:
        if curtime < matched_hist['start']:
            matched_hist['start'] = start_time
            if curtime < matched_hist['end']:
                matched_hist['end'] = curtime
        elif (start_time - curtime) > (matched_hist['start'] - matched_hist['end']):
            matched_hist['start'] = start_time
            matched_hist['end'] = curtime
    else:
        rank_histories.append({
            'mode': mode,
            'limit': limit,
            'start': start_time,
            'end': curtime
        })
    history.write()


def download_batch(illusts):
    for i in illusts:
        i.download()


def evaluate_all():
    batch_size = 32
    limit = 1000
    for evaluator in evaluators:
        offset = 0
        illusts = []
        res = search_illusts(limit, offset, IllustSort.TIME, {
            'not_tested_evals': [evaluator['name']]
        })
        while len(res) != 0:
            illusts += res
            offset += len(res)
            res = search_illusts(limit, offset, IllustSort.TIME, {
                'not_tested_evals': [evaluator['name']]
            })
        offset = 0
        num = len(illusts)
        while offset < num:
            batch_illusts = illusts[offset:min(offset+batch_size, num)]
            size = len(batch_illusts)
            iids = [i.id for i in batch_illusts]
            img_paths = [os.path.join(Paths.IMG_DIR.value % iid, 'large.jpg') for iid in iids]
            results = evaluator['eval_batch'](img_paths)
            for i in range(size):
                illust = batch_illusts[i]
                illust.read()
                illust.tested_evals.append(evaluator['name'])
                if results[i]:
                    illust.passed_evals.append(evaluator['name'])
                illust.write()
            offset += size
