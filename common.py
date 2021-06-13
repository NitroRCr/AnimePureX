from pixivpy3 import PixivAPI
from pixiv_auth import refresh
import sqlite3
from enum import IntEnum
import json
from threading import Thread
import init
import time
from urllib.parse import urljoin


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


def get_json(filename):
    f = open(filename)
    j = json.loads(f.read())
    f.close()
    return j


class APIError(Exception):
    def __init__(self, message, status):
        super().__init__(message, status)
        self.message = message
        self.status = status


class IdNotFoundError(ValueError):
    def __init__(self, message, status):
        super().__init__(message, status)
        self.message = message
        self.status = status


img_dir = 'static/img/%d'

CONFIG = get_json('config.json')
pixiv_reftoken = CONFIG['pixiv_refresh_token']
pixiv_acctoken = refresh(pixiv_reftoken)['access_token']


def refresh_pixiv_token():
    global pixiv_acctoken
    while True:
        time.sleep(3000)
        pixiv_acctoken = refresh(pixiv_reftoken)['access_token']


Thread(target=refresh_pixiv_token, daemon=True).start()

papi = PixivAPI()
papi.set_auth(pixiv_acctoken, pixiv_reftoken)

sql_conn = sqlite3.connect(CONFIG['sqlite_db'])
sql_cursor = sql_conn.cursor()
with open('init.sql') as f:
    sql_cursor.executescript(f.read())


class Illust:
    def __init__(self, from_id=None, pixiv_id=None):
        if from_id is not None:
            self.load_from_id(from_id)
        elif pixiv_id is not None:
            self.load_from_pixiv(pixiv_id)
        else:
            raise Exception()
        self.set_image_urls()

    def load_from_id(self, from_id):
        self.id = from_id
        fetched = sql_cursor.execute(
            'SELECT (type, user, raw_json) FROM illusts WHERE id=?', (from_id,))
        if fetched is None:
            raise IdNotFoundError('Invalid user id')
        self.type, user_id, json_str = fetched[0]
        self.user = User(from_id=user_id)
        self.raw_json = json.loads(json_str)

    def load_from_pixiv(self, pixiv_id):
        resp = papi.works(pixiv_id)
        if resp['status'] != 'success':
            raise APIError('load illust from pixiv failed')
        info = resp['response'][0]
        self.raw_json = info
        self.user = User(pixiv_id=info['user']['id'])
        sql_cursor.execute('INSERT INTO illusts (type, user, raw_json, downloaded) VALUES (?, ?, ?, ?)',
                           (APIType.PIXIV, self.user.id, json.dumps(self.raw_json), False))
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
            self.load_from_pixiv(pixiv_id)
        else:
            raise Exception()

    def load_from_id(self, from_id):
        self.id = from_id
        fetched = sql_cursor.execute(
            'SELECT (type, user, raw_json) FROM users WHERE id=?', (from_id,))
        if fetched is None:
            raise IdNotFoundError('Invalid user id')
        self.type, user_id, json_str = fetched[0]
        self.user = User(from_id=user_id)
        self.raw_json = json.loads(json_str)

    def load_from_pixiv(self, pixiv_id):
        resp = papi.users(pixiv_id)
        if resp['status'] != 'success':
            raise APIError('load user from pixiv failed')
        info = resp['response'][0]
        self.raw_json = info
        self.type = APIType.PIXIV
        sql_cursor.execute('INSERT INTO illusts (type, user, raw_json) VALUES (?, ?, ?)',
                           (APIType.PIXIV, self.user.id, json.dumps(self.raw_json)))
        self.id = sql_cursor.execute(
            'select last_insert_rowid() from illusts').fetchall()[0][0]
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
                'intro': self.raw_json['introduction']
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
