
import pickle
import numpy as np
import json
import matplotlib.pyplot as plt
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.metrics import *
import sklearn
import re
from scipy.spatial import distance
from skimage.transform import resize
import subprocess

from sklearn.svm import SVC

import cv2

np.random.seed(10)
cascade_path = './cv2/haarcascade_frontalface_alt2.xml'

if tf.__version__ == '2.0.0-alpha0':
    coreModel = tf.keras.models.load_model("./models/facenet_512.h5")
else:
    import keras
    coreModel = keras.models.load_model("./models/facenet_512.h5")

def l2_normalize(x, axis=-1, epsilon=1e-10):
    output = x / np.sqrt(np.maximum(np.sum(np.square(x), axis=axis, keepdims=True), epsilon))
    return output

def to_rgb(img):
    if img.ndim == 2: 
        w, h = img.shape
        ret = np.empty((w, h, 3), dtype=img.dtype)
        ret[:, :, 0] = ret[:, :, 1] = ret[:, :, 2] = img
        return ret
    elif img.shape[2] == 3:
        return img
    elif img.shape[2] == 4:
        w, h, t = img.shape 
        ret = np.empty((w, h, 3), dtype=img.dtype)
        #ret[:, :, 0] = ret[:, :, 1] = ret[:, :, 2] = img
        return img[:, :, :3]

class AIengine: 
    def __init__(self, modelpath, create = False):
        try:
            self.modelpath = modelpath 
            classifier = modelpath + "/model.pkl"
            meta = modelpath + "/model.meta"
            self.clfMap = {'img':self.classifyImg, 'vec':self.classifyVec}
            self.fitMap = {'img':self.fitImg, 'vec':self.fitVec}
            print(classifier)

            if create:
                print("Creating new AI Engine")
                #   We Need to create this AI engine and save it on disk
                self.classifier = SVC(kernel='linear', probability=True)
                
                self.labelEncodeMap = dict()    # Contains mapping from id string to hash
                self.labelDecodeMap = dict()    # self.metadata['labelDecodeMap']   # Contains mapping from hash to id string

                self.image_size = 160
                self.margin = 1.1
                
                subprocess.getoutput("mkdir " + modelpath)
                self.save(modelpath)
            else:
                if ("No such file or directory" in (subprocess.getoutput("ls " + modelpath))):
                    return "AI Engine not created yet!"
                print("Loading AI Engine")
                self.classifier = pickle.loads(open(classifier, 'rb').read())
                self.metadata = pickle.loads(open(meta, 'rb').read())

                self.labelEncodeMap = dict(self.metadata['labelEncodeMap'])   # Contains mapping from id string to hash
                self.labelDecodeMap = {value: key for key, value in self.labelEncodeMap.items()}#self.metadata['labelDecodeMap']   # Contains mapping from hash to id string

                self.image_size = self.metadata['imagesize']#160
                self.margin = self.metadata['similarity_margin']#1.1
        except Exception as e:
            print("Error in AIengine.init")
            print(e) 
        return None

    def embed(self, images, preprocess = False):
        try:
            if preprocess is True:
                images = self.preprocess(images, 10)
            return l2_normalize(coreModel.predict(images))
        except Exception as e:
            print("Error in AIengine.embed")
            print(e)
        return None

    def fitImg(self, images, labels):
        try:
            embs = self.embed(images)
            self.classifier.fit(embs, labels)
            return embs 
        except Exception as e:
            print("Error in AIengine.fitImg")
            print(e)
        return False

    def fitVec(self, vectors, labels):
        try:
            embs = vectors#self.embed(images)
            self.classifier.fit(embs, labels)
            return embs 
        except Exception as e:
            print("Error in AIengine.fitVec")
            print(e)
        return False
    
    def fit(self, data, labels, fitType = 'img'):
        try:
            lbls = list()
            for i in labels:
                if i not in self.labelEncodeMap:
                    self.labelEncodeMap[i] = hash(i)
                    self.labelDecodeMap[hash(i)] = i
                lbls.append(self.labelEncodeMap[i])
            print(self.labelEncodeMap)
            return self.fitMap[fitType](data, lbls).tolist()
        except Exception as e:
            print("Error in AIengine.fit")
            print(e)
        return False

    def classifyImg(self, images):
        return [self.labelDecodeMap[i] for i in self.classifier.predict(self.embed(images))]
    
    def classifyVec(self, vectors):
        return [self.labelDecodeMap[i] for i in self.classifier.predict(vectors)]

    def classify(self, data, clfType = 'img'):
        try:
            return self.clfMap[clfType](data)
        except Exception as e:
            print(clfType)
            print("Error in AIengine.classify")
            print(e)
        return None

    def isSimilar(self, img1, img2, margin = 1.1):
        try:
            v1 = self.embed([img1])
            v2 = self.embed([img2])
            dis = distance.euclidean(v1, v2)
            if dis > margin:
                return False 
            else:
                return True
        except Exception as e:
            print("Error in AIengine.isSimilar")
            print(e)
        return None
    
    def isSimilarVec(self, img, vec, margin = 1.1):
        try:
            v1 = self.embed([img])
            v2 = vec
            dis = distance.euclidean(v1, v2)
            if dis > margin:
                return False 
            else:
                return True
        except Exception as e:
            print("Error in AIengine.isSimilarVec")
            print(e)
        return None

    def prewhiten(self, x):
        if x.ndim == 4:
            axis = (1, 2, 3)
            size = x[0].size
        elif x.ndim == 3:
            axis = (0, 1, 2)
            size = x.size
        else:
            raise ValueError('Dimension should be 3 or 4')

        mean = np.mean(x, axis=axis, keepdims=True)
        std = np.std(x, axis=axis, keepdims=True)
        std_adj = np.maximum(std, 1.0/np.sqrt(size))
        y = (x - mean) / std_adj
        return y

    def align_images(self, images, margin):
        cascade = cv2.CascadeClassifier(cascade_path)
        
        aligned_images = []
        for img in images:
            faces = cascade.detectMultiScale(img,
                                            scaleFactor=1.1,
                                            minNeighbors=3)
            (x, y, w, h) = faces[0]
            cropped = img[y-margin//2:y+h+margin//2,
                        x-margin//2:x+w+margin//2, :]
            aligned = resize(cropped, (self.image_size, self.image_size), mode='reflect')
            aligned_images.append(aligned)
                
        return np.array(aligned_images)

    @staticmethod
    def preprocess(images, margin = 10, image_size = 160):
        cascade = cv2.CascadeClassifier(cascade_path)
        aligned_images = []
        for img in images:
            #print(filepath)
            if type(img) is list:
                img = np.array(img)
            if img.dtype in ('uint8', 'int64'):
                img = img.astype('float')/255.
            img = to_rgb(img)
            #plt.imshow(img)
            #plt.show()
            img = resize(img, (image_size, image_size), mode='reflect')
            #plt.imshow(img)
            #plt.show()
            aligned_images.append(img)
        return np.array(aligned_images)

    def save(self, modelpath):
        self.modelpath = modelpath 
        self.metadata = {'labelEncodeMap':self.labelEncodeMap, 'labelDecodeMap':self.labelDecodeMap,
                            'imagesize':self.image_size, 'similarity_margin':self.margin}
        f = open(modelpath+'/model.meta', 'wb')
        f.write(pickle.dumps(self.metadata))
        f.close() 

        f = open(modelpath+'/model.pkl', 'wb')
        f.write(pickle.dumps(self.classifier))
        f.close() 
        return True