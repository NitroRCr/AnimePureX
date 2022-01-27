# AnimePureX

一个二次元图片网站的后端

前端项目：[NitroRCr/anime-purex](https://github.com/NitroRCr/anime-purex)

### 实现功能

- 自动从pixiv排行榜下载图片，获取图片的标题、标签等信息
- 用keras的模型对图片进行评估（效果可能并不好，因为主观性太大）
- 基于flask的服务端，为前端提供图片，提供搜索、用户登录等功能
- 基于elasticsearch的图片搜索

~~代码写得可能比较乱~~

## 运行和部署

生成配置文件 

```sh
python init.py
```

编辑配置文件`config.json`

- `pixiv_api`:
  - `ranking`: 从排行榜下载作品的相关设置
    - `illust_only`: 是否仅下载插画
    - `mode`: 排行榜类型（周期），可选值:
      - `day`: 日榜
      - `week`: 周榜
      - `month`: 月榜
    - `limit`: 从每个排行榜下载作品的数量
    - `loop`: 循环下载多少个周期排行榜
    - (下载顺序为从最近的排行榜开始向前循环，已下载过的会跳过)
  - `refresh_token`: 用来认证pixiv账号。[获取方法](https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362)
  - `accept_language`: 接受语言
- `elasticsearch`: Elasticsearch服务的地址、用户、密码
- `flask`:
  - `host`: 调试服务端的运行主机名
  - `port`: 调试服务端的运行端口
  - `token_key`: 随机生成的服务端私钥，用于生成、验证token
- `download_threads`: 下载作品的线程数
- `image_scale`: 图片压缩相关设置
  - `pixel_num`: 不同清晰度的最大像素数量
  - `webp_q`: webp格式图片压缩质量，取值0~100，越大质量越高
  - `jpg_q`: jpg格式图片压缩质量，取值1~31，越小质量越高

配置评估模型，可以参考`evaluators`目录的内容。需在`common.py`中填写`evaluators`的信息

下载、评估图片

```sh
python update.py
```

运行调试服务端

```sh
python app.py
```

生产环境请使用[uwsgi](https://uwsgi-docs.readthedocs.io/en/latest/WSGIquickstart.html)等运行服务端

