from flask import Flask, request, abort, send_from_directory
from common import (
    Illust,
    search_illusts,
    search_users,
    IllustSort,
    User,
    Xuser,
    CONFIG,
    AgeLimit
)
from elasticsearch import NotFoundError
import json
import jwt
import time

app = Flask(__name__, static_url_path='')


@app.route('/illusts', methods=['GET'])
def get_illusts():
    try:
        search = json.loads(request.args['search']) if 'search' in request.args else {
            'sort': IllustSort.RANDOM.value
        }
    except json.JSONDecodeError:
        abort(400)
    limit = search['limit'] if 'limit' in search else 20
    sort = IllustSort(
        search['sort']) if 'sort' in search else IllustSort.DEFAULT
    query = search['query'] if 'query' in search else {}
    offset = search['offset'] if 'offset' in search else 0
    if 'downloaded' not in query:
        query['downloaded'] = True
    if 'ids' in search:
        illusts = [Illust(from_id=id) for id in search['ids']
                   [offset:min(len(search['ids']), offset + limit)]]
    else:
        illusts = search_illusts(limit, offset, sort, query)
    return json.dumps([i.json() for i in illusts], ensure_ascii=False)


@app.route('/users', methods=['GET'])
def get_users():
    try:
        search = json.loads(request.args['search']
                            ) if 'search' in request.args else {}
    except json.JSONDecodeError:
        abort(400)
    limit = search['limit'] if 'limit' in search else 20
    query = search['query'] if 'query' in search else {}
    offset = search['offset'] if 'offset' in search else 0
    if 'downloaded' not in query:
        query['downloaded'] = True
    if 'age_limit' not in query:
        query['age_limit'] = AgeLimit.ALL_AGE.value
    if 'ids' in search:
        users = [User(from_id=id)
                 for id in search['ids'][offset:min(len(search['ids']), offset + limit)]]
    else:
        users = search_users(limit, offset, query)
    return json.dumps([i.json() for i in users], ensure_ascii=False)


@app.route('/illusts/<id>', methods=['GET'])
def get_illust(id):
    try:
        illust = Illust(id)
    except NotFoundError:
        abort(404)
    return json.dumps(illust.json(), ensure_ascii=False)


@app.route('/users/<id>', methods=['GET'])
def get_user(id):
    try:
        user = User(id)
    except NotFoundError:
        abort(404)
    return json.dumps(user.json(), ensure_ascii=False)


@app.route('/xusers/<name>', methods=['GET', 'PUT'])
def get_xuser(name):
    headers = request.headers
    if request.method == 'GET':
        data = request.args
        try:
            xuser = Xuser(name=name)
        except ValueError:
            abort(404)
        if 'Authorization' not in headers:
            return json.dumps(xuser.brief(), ensure_ascii=False)
        cert = cert_token(headers['Authorization'])
        if not cert or cert != xuser.name:
            abort(401)
        return json.dumps(xuser.json(), ensure_ascii=False)
    else:
        data = request.form
        try:
            xuser = Xuser(name=name)
        except ValueError:
            xuser = Xuser(info={
                'name': name,
                'password': data['password'],
                'salt': data['salt']
            })
            time.sleep(1)
            return {'success': True}
        if 'Authorization' not in headers:
            abort(409)
        if cert_token(headers['Authorization']) != name:
            abort(401)
        if 'password' in data:
            xuser.password = data['password']
        if 'favorited' in data:
            try:
                xuser.favorited = json.loads(data['favorited'])
            except json.JSONDecodeError:
                abort(400)
        if 'following' in data:
            try:
                xuser.following = json.loads(data['following'])
            except json.JSONDecodeError:
                abort(400)
        xuser.write()
        return {'success': True}


@app.route('/token', methods=['POST'])
def token():
    data = request.form
    try:
        xuser = Xuser(name=data['name'])
    except ValueError:
        abort(404)
    if data['password'] != xuser.password:
        abort(403)
    return gen_token(xuser.name)


@app.route('/download/<path:fname>')
def download_file(fname):
    kwargs = {'as_attachment': True}
    if 'filename' in request.args:
        kwargs['attachment_filename'] = request.args['filename']
    return send_from_directory('static', fname, **kwargs)


def gen_token(name):
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    payload = {
        'name': name,
        'exp': int(time.time() + 60*60*24*30)
    }
    key = CONFIG['flask']['token_key']
    return jwt.encode(payload=payload, key=key,
                      algorithm='HS256', headers=headers).decode('utf-8')


def cert_token(token):
    key = CONFIG['flask']['token_key']
    info = jwt.decode(token, key, False, algorithm='HS256')
    if info['exp'] < time.time():
        return False
    return info['name']

if __name__ == '__main__':
    app.run(host=CONFIG['flask']['host'], port=CONFIG['flask']['port'])
