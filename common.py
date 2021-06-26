from pixivpy3 import PixivAPI
from pixiv_auth import refresh
import sqlite3
from enum import IntEnum
import json
from threading import Thread
import init
import time
from urllib.parse import urljoin
from joblib import Parallel, delayed
import os


class AgeLimit(IntEnum):
    ALL_AGE = 0
    R_15 = 1
    R_18 = 2


class APIType(IntEnum):
    PIXIV = 0


class StatusCode(IntEnum):
    SCCESS = 0
    ERROR = 1
    WARNING = 2


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


img_dir = 'static/img/%d'

history = JsonDict('history.json')
CONFIG = JsonDict('config.json').value
pixiv_reftoken = CONFIG['pixiv_refresh_token']
pixiv_acctoken = None

papi = PixivAPI()


def pixiv_token_thread():
    while True:
        time.sleep(3000)
        refresh_pixiv_token()


def refresh_pixiv_token():
    global pixiv_acctoken
    pixiv_acctoken = refresh(pixiv_reftoken)['access_token']
    papi.set_auth(pixiv_acctoken, pixiv_reftoken)


refresh_pixiv_token()
Thread(target=pixiv_token_thread, daemon=True).start()

sql_conn = sqlite3.connect(CONFIG['sqlite_db'])
sql_cursor = sql_conn.cursor()

def ref_sql_db():
    global sql_conn, sql_cursor
    sql_conn = sqlite3.connect(CONFIG['sqlite_db'])
    sql_cursor = sql_conn.cursor()

def close_db():
    sql_conn.close()

with open('init.sql') as f:
    sql_cursor.executescript(f.read())


class Illust:
    def __init__(self, from_id=None, pixiv_info=None, pixiv_id=None):
        if from_id is not None:
            self.load_from_id(from_id)
        elif pixiv_info is not None:
            self.load_from_pixiv(pixiv_info)
        elif pixiv_id is not None:
            fetched = sql_cursor.execute(
                'SELECT id FROM illusts WHERE type_id=?', (pixiv_id,)).fetchall()
            if fetched:
                self.load_from_id(fetched[0][0])
            else:
                resp = papi.works(pixiv_id)
                if resp['status'] != 'success':
                    print('response:', resp)
                    raise APIError('load illust from pixiv failed')
                self.load_from_pixiv(resp['response'][0])
        else:
            raise Exception()
        self.set_image_urls()

    def load_from_id(self, from_id):
        self.id = from_id
        fetched = sql_cursor.execute(
            'SELECT type, user, raw_json FROM illusts WHERE id=?', (from_id,)).fetchall()
        if fetched is None:
            raise IdNotFoundError('Invalid user id')
        self.type, user_id, json_str = fetched[0]
        self.user = User(from_id=user_id)
        self.raw_json = json.loads(json_str)

    def load_from_pixiv(self, info):
        self.raw_json = info
        self.type = APIType.PIXIV
        self.user = User(pixiv_id=info['user']['id'])
        sql_cursor.execute('INSERT INTO illusts (type, type_id, user, raw_json, downloaded) VALUES (?, ?, ?, ?, ?)',
                           (APIType.PIXIV, info['id'], self.user.id, json.dumps(info), False))
        self.id = sql_cursor.execute(
            'select last_insert_rowid() from illusts').fetchall()[0][0]
        sql_conn.commit()

    def set_image_urls(self):
        if self.type == APIType.PIXIV:
            urls = self.raw_json['image_urls']
            self.image_url = ImageUrl(
                urls['small'], urls['medium'], urls['large'])
        else:
            raise Exception()

    def download(self):
        if self.type == APIType.PIXIV:
            ddir = img_dir % self.id
            if not os.path.exists(ddir):
                os.mkdir(ddir)
            try:
                papi.download(self.image_url.large, path=ddir, fname='large')
                papi.download(self.image_url.medium, path=ddir, fname='medium')
                papi.download(self.image_url.small, path=ddir, fname='small')
            except:
                raise APIError('download illust failed')
            sql_cursor.execute(
                'UPDATE illusts SET downloaded=true WHERE id=?', (self.id,))
        else:
            raise Exception()

    def json(self):
        if self.type == APIType.PIXIV:
            img_path = '/img/%d/' % self.id
            return {
                'id': self.id,
                'title': self.raw_json['title'],
                'tags': self.raw_json['tags'],
                'image_urls': {
                    'small': urljoin(img_path, 'small'),
                    'medium': urljoin(img_path, 'medium'),
                    'large': urljoin(img_path, 'large')
                },
                'type': 'illust/pixiv',
                'type_info': {
                    'id': self.raw_json['id'],
                    'url': 'https://www.pixiv.net/artworks/%d' % self.raw_json['id']
                },
                'user': self.user.json()
            }
        else:
            raise Exception()


class User:
    def __init__(self, from_id=None, pixiv_id=None):
        if from_id is not None:
            self.load_from_id(from_id)
        elif pixiv_id is not None:
            fetched = sql_cursor.execute(
                'SELECT id FROM users WHERE type_id=?', (pixiv_id,)).fetchall()
            if fetched:
                self.load_from_id(fetched[0][0])
            else:
                self.load_from_pixiv(pixiv_id)
        else:
            raise Exception()

    def load_from_id(self, from_id):
        self.id = from_id
        fetched = sql_cursor.execute(
            'SELECT type, raw_json FROM users WHERE id=?', (from_id,)).fetchall()
        if fetched is None:
            raise IdNotFoundError('Invalid user id')
        self.type, json_str = fetched[0]
        self.raw_json = json.loads(json_str)

    def load_from_pixiv(self, pixiv_id):
        resp = papi.users(pixiv_id)
        if resp['status'] != 'success':
            print('response:', resp)
            raise APIError('load user from pixiv failed')
        info = resp['response'][0]
        self.raw_json = info
        self.type = APIType.PIXIV
        sql_cursor.execute('INSERT INTO users (type, type_id, raw_json) VALUES (?, ?, ?)',
                           (APIType.PIXIV, info['id'], json.dumps(self.raw_json)))
        self.id = sql_cursor.execute(
            'select last_insert_rowid() from users').fetchall()[0][0]
        sql_conn.commit()

    def json(self):
        if self.type == APIType.PIXIV:
            return {
                'id': self.id,
                'name': self.raw_json['name'],
                'type': 'user/pixiv',
                'type_info': {
                    'id': self.raw_json['id'],
                    'url': 'https://www.pixiv.net/users/%d' % self.id
                },
                'intro': self.raw_json['profile']['introduction']
            }
        else:
            raise Exception()


def random_illusts(limit):
    sql_cursor.execute(
        'SELECT id FROM illusts WHERE downloaded=true ORDER BY RANDOM() limit ?', (limit,))
    ids = [i[0] for i in sql_cursor.fetchall()]
    return [Illust(from_id=i).json() for i in ids]


class ImageUrl:
    def __init__(self, small, medium, large):
        self.small = small
        self.medium = medium
        self.large = large


def pixiv_loop_ranking():
    rank = CONFIG['pixiv_ranking']
    rtype = rank['ranking_type']
    mode = rank['mode']
    limit = rank['limit']
    loop = rank['loop']
    rank_histories = history.value['pixiv_ranking']
    matched_hist = None
    for hist in rank_histories:
        if hist['mode'] == mode and hist['limit'] == limit:
            matched_hist = hist
            break
    if mode == 'monthly':
        loop_time = 30*24*60*60
    elif mode == 'weekly':
        loop_time = 7*24*60*60
    elif mode == 'daily':
        loop_time = 24*60*60
    start_time = time.time()
    curtime = start_time + loop_time
    for i in range(loop):
        curtime -= loop_time
        if matched_hist and curtime < matched_hist['start'] and curtime > matched_hist['end']:
            continue
        date = time.strftime('%Y-%m-%d', time.localtime(curtime))
        resp = papi.ranking(rtype, mode, 1, limit, date,
                            image_sizes=['small', 'medium', 'large'])
        if resp['status'] != 'success':
            if resp['errors']['system']['code'] == 404:
                start_time -= loop_time
                continue
            print('response:', resp)
            raise APIError('pixiv rank failed')
        illusts = [Illust(pixiv_info=i['work']) for i in resp['response'][0]['works']]
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
    n_job = CONFIG['download_threads']
    # Parallel(n_job)(delayed(lambda i: i.download())(i) for i in illusts)
    for i in illusts:
        i.download()