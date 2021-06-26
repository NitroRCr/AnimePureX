from flask import Flask, request, abort
from common import (
    Illust,
    CONFIG,
    random_illusts,
    Illust,
    User,
    IdNotFoundError,
    ref_sql_db,
    close_db
)
import json

app = Flask(__name__, static_url_path='')

@app.route('/illusts')
def get_illusts():
    ref_sql_db()
    limit = request.args['limit'] if 'limit' in request.args else 20
    ret = json.dumps(random_illusts(limit), ensure_ascii=False)
    close_db()
    return ret

@app.route('/illusts/<int:id>')
def get_illust(id):
    ref_sql_db()
    try:
        illust = Illust(id)
    except IdNotFoundError:
        abort(404)
    close_db()
    return json.dumps(illust.json(), ensure_ascii=False)

@app.route('/users/<int:id>')
def get_user(id):
    ref_sql_db()
    try:
        user = User(id)
    except IdNotFoundError:
        abort(404)
    close_db()
    return json.dumps(user.json(), ensure_ascii=False)

if __name__ == '__main__':
    app.run(host=CONFIG['host'], port=CONFIG['port'])
