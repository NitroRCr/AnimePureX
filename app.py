from flask import Flask, request, abort
from common import (
    Illust,
    CONFIG,
    random_illusts,
    Illust,
    User,
    IdNotFoundError
)
import json

app = Flask(static_url_path='')

@app.route('/illusts')
def get_illusts():
    limit = request.args['limit'] if 'limit' in request.args else 20
    return json.dumps(random_illusts(limit), ensure_ascii=False)

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
    app.run(host=CONFIG['host'], port=CONFIG['port'])
