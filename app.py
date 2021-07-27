from flask import Flask, request, abort
from common import (
    Illust,
    search_illusts,
    search_users,
    IllustSort,
    User,
    CONFIG,
    AgeLimit,
    IdNotFoundError
)
import json

app = Flask(__name__, static_url_path='')

@app.route('/illusts')
def get_illusts():
    search = json.loads(request.args['search']) if 'search' in request.args else {
        'sort': IllustSort.RANDOM.value
    }
    limit = search['limit'] if 'limit' in search else 20
    sort = IllustSort(search['sort']) if 'sort' in search else IllustSort.DEFAULT
    query = search['query'] if 'query' in search else {}
    offset = search['offset'] if 'offset' in search else 0
    if 'downloaded' not in query:
        query['downloaded'] = True
    illusts = search_illusts(limit, offset, sort, query)
    return json.dumps([i.json() for i in illusts], ensure_ascii=False)

@app.route('/users')
def get_users():
    search = json.loads(request.args['search']) if 'search' in request.args else {}
    limit = search['limit'] if 'limit' in search else 20
    query = search['query'] if 'query' in search else {}
    offset = search['offset'] if 'offset' in search else 0
    if 'downloaded' not in query:
        query['downloaded'] = True
    if 'age_limit' not in query:
        query['age_limit'] = AgeLimit.ALL_AGE.value
    users = search_users(limit, offset, query)
    return json.dumps([i.json() for i in users], ensure_ascii=False)

@app.route('/illusts/<int:id>')
def get_illust(id):
    try:
        illust = Illust(id)
    except IdNotFoundError:
        abort(404)
    return json.dumps(illust.json(), ensure_ascii=False)

@app.route('/users/<int:id>')
def get_user(id):
    try:
        user = User(id)
    except IdNotFoundError:
        abort(404)
    return json.dumps(user.json(), ensure_ascii=False)

if __name__ == '__main__':
    app.run(host=CONFIG['flask']['host'], port=CONFIG['flask']['port'])
