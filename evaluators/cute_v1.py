from keras import models
from keras.preprocessing import image
import numpy as np

model = None
target_size = (224, 224)

def _rescale(x):
    return x/255

def load():
    global model
    if model:
        return
    model = models.load_model('saved_models/cute_model.h5')


def eval(img_path):
    img = image.load_img(img_path, target_size=target_size)
    img = image.img_to_array(img)
    img = _rescale(img)
    imgs = np.expand_dims(img)
    res = model.predict(imgs)[0]
    if res[0] > .5:
        return True
    else:
        return False

def eval_batch(img_paths):
    num = len(img_paths)
    imgs = np.zeros((num, target_size[0], target_size[1], 3), dtype=float)
    for i in range(num):
        img = image.load_img(img_paths[i], target_size=target_size)
        img = image.img_to_array(img)
        img = _rescale(img)
        imgs[i] = img
    ret = []
    for res in model.predict(imgs):
        if res[0] > .5:
            ret.append(True)
        else:
            ret.append(False)
    return ret
