import os
import json

CONF_TEMPLATES = {
    'config.json': {
        "pixiv_api": {
            "ranking": {
                "illust_only": True,
                "mode": "day",
                "limit": 100,
                "loop": 100
            },
            "refresh_token": "",
            "accept_language": "zh-cn"
        },
        "elasticsearch": {
            "hosts": [
                "127.0.0.1:9200"
            ],
            "auth": [
                "user",
                "password"
            ]
        },
        "flask": {
            "host": "127.0.0.1",
            "port": 5005
        },
        "download_threads": 4,
        "image_scale": {
            "pixel_num": {
                "large": 720*1280,
                "medium": 360*640
            },
            "webp_q": 75,
            "jpg_q": 7
        }
    },
    'data/history.json': {
        "pixiv_ranking": [],
        "ids": {}
    }
}

DIRS = [
    'static',
    'static/img',
    'static/user',
    'data',
    'saved_models'
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
