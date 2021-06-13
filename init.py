import os
import json

CONF_TEMPLATES = {
    'config.json': {
        "pixiv_refresh_token": "",
        #"img_proxy_host": "i.pixiv.cat",
        "sqlite_db": "sqlite.db",
        "host": "127.0.0.1",
        "port": 5005
    }
}

DIRS = [
    'static',
    'static/img'
]


def init():
    for i in DIRS:
        if not os.path.exists(i):
            print('mkdir', i)
            os.mkdir(i)

    for i in CONF_TEMPLATES:
        if not os.path.exists(i):
            print("init", i)
            f = open(i, 'w')
            f.write(json.dumps(CONF_TEMPLATES[i], indent=4))
            f.close()


init()
