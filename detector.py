#!/usr/bin/env python2
# -*- coding: utf-8 -*

# Copyright (c) 2017-present, Facebook, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##############################################################################

"""Perform inference on a single image or all images with a certain extension
(e.g., .jpg) in a folder.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import sys
from collections import defaultdict
import cv2  # NOQA (Must import before importing caffe2 due to bug in cv2)
import glob
import logging
import os
import sys
import time
import numpy as np
from caffe2.python import workspace

from detectron.core.config import assert_and_infer_cfg
from detectron.core.config import cfg
from detectron.core.config import merge_cfg_from_file
from detectron.utils.io import cache_url
from detectron.utils.logging import setup_logging
from detectron.utils.timer import Timer
import detectron.core.test_engine as infer_engine
import detectron.datasets.dummy_datasets as dummy_datasets
import detectron.utils.c2 as c2_utils
import detectron.utils.vis as vis_utils
import copy
c2_utils.import_detectron_ops()

workspace.GlobalInit(['caffe 2', '--caffe2_log_level=0'])

dummy_coco_datasets = dummy_datasets.get_coco_dataset()
# OpenCL may be enabled by default in OpenCV3; disable it because it's not
# thread safe and causes unwanted GPU memory allocations.
cv2.ocl.setUseOpenCL(False)
def convert_from_cls_format(cls_boxes, cls_segms, cls_keyps):
    """Convert from the class boxes/segms/keyps format generated by the testing
    code.
    """
    box_list = [b for b in cls_boxes if len(b) > 0]
    if len(box_list) > 0:
        boxes = np.concatenate(box_list)
    else:
        boxes = None
    if cls_segms is not None:
        segms = [s for slist in cls_segms for s in slist]
    else:
        segms = None
    if cls_keyps is not None:
        keyps = [k for klist in cls_keyps for k in klist]
    else:
        keyps = None
    classes = []
    for j in range(len(cls_boxes)):
        classes += [j] * len(cls_boxes[j])
    return boxes, segms, keyps, classes


def get_class_string(class_index, score, dataset):
    class_text = dataset.classes[class_index] if dataset is not None else \
        'id{:d}'.format(class_index)
    return class_text + ' {:0.2f}'.format(score).lstrip('0')


def convert_from_cls_format(cls_boxes, cls_segms, cls_keyps):
    """Convert from the class boxes/segms/keyps format generated by the testing
    code.
    """
    box_list = [b for b in cls_boxes if len(b) > 0]
    if len(box_list) > 0:
        boxes = np.concatenate(box_list)
    else:
        boxes = None
    if cls_segms is not None:
        segms = [s for slist in cls_segms for s in slist]
    else:
        segms = None
    if cls_keyps is not None:
        keyps = [k for klist in cls_keyps for k in klist]
    else:
        keyps = None
    classes = []
    for j in range(len(cls_boxes)):
        classes += [j] * len(cls_boxes[j])
    return boxes, segms, keyps, classes

# def Convert_bbox_to_json(im_height,im_width,bbox,classes):
#     """Convert the result of bbox to json file"""
#     if bbox is None or classes is None:
#         return None
#     global dummy_coco_datasets
#     if len(bbox) != len(classes):
#         return None
#     all_boxes = []
#     for i in range(len(bbox)):
#         each_box = {}
#         each_box['conf'] = int(bbox[i][-1] * 100)
#         each_box['x'] = bbox[i][0] / im_width
#         each_box['y'] = bbox[i][1] / im_height
#         each_box['width'] = bbox[i][2] / im_width - each_box['x']
#         each_box['height'] = bbox[i][3] / im_height - each_box['y']
#         each_box['name'] = dummy_coco_datasets['classes'][classes[i]]
#         all_boxes.append(each_box)
#     return all_boxes

def Convert_bbox_to_json(im_height,im_width,bbox,classes):
    """Convert the result of bbox to json file"""
    if bbox is None or classes is None:
        return None
    global dummy_coco_datasets
    if len(bbox) != len(classes):
        return None
    all_boxes = []
    for i in range(len(bbox)):
        each_box = {}
        each_box['conf'] = int(bbox[i][-1] * 100)
        each_box['x'] = bbox[i][0]
        each_box['y'] = bbox[i][1]
        each_box['width'] = bbox[i][2]- each_box['x']
        each_box['height'] = bbox[i][3] - each_box['y']
        each_box['name'] = dummy_coco_datasets['classes'][classes[i]]
        all_boxes.append(each_box)
    return all_boxes

def visual_all_box(im,boxes,classes):
    """rectangle the bbox"""
    if boxes is None or classes is None:
        return im
    if len(boxes) != len(classes):
        return im
    for i in range(len(boxes)):
        bbox =[int(item) for item in  boxes[i][:4]]
        conf = boxes[i][-1]
        if conf < 0.7:
            continue
        category_id = classes[i]
        category_name = str(category_id)
        #category_name = dummy_coco_datasets['classes'][category_id]
        #print (category_name)
        point1 = (bbox[0],bbox[1])
        point2 = (bbox[2],bbox[3])
        #print (point1)
        color_list = [(0,255,0),(0,0,255),(255,255,0),(255,0,255),(0,255,255)]
        color = color_list[i%5]
        im[bbox[1]:bbox[1]+10,bbox[0]:bbox[2]] = color
        cv2.rectangle(im,point1,point2,color,1)
        cv2.putText(im,category_name,(bbox[0],bbox[1]+8),2,0.5,(0,0,0))
    return im
def visual_box(im,boxes,classes):
    """rectangle the bbox"""
    if boxes is None or classes is None:
        return im
    if len(boxes) != len(classes):
        return im
    imcopy =copy.deepcopy(im)
    area_no_drew_point1 = (0,0)
    area_no_drew_point2 = (250,1920)
    for i in range(len(boxes)):
        bbox =[int(item) for item in  boxes[i][:4]]
        conf = boxes[i][-1]
        category_id = classes[i]
        category_name = dummy_coco_datasets['classes'][category_id]
        #print (category_name)
        point1 = (bbox[0],bbox[1])
        point2 = (bbox[2],bbox[3])
        #print (point1)
        color = (255,0,0)
        category_list = ['person','bicycle','car','bus','truck','motorcycle']
        #color_list = [(0,255,0),(0,0,255),(255,255,0),(0,255,255),(255,0,255),(255,0,0)]
        if category_name in category_list:
            if category_name == 'person':
                color = (228,108,15)
            else:
                color = (225,242,61)
            if conf > 0.8:
                x1 = point1[1]
                y1 = point1[0]
                x2 = point2[1]
                y2 = point2[0]
                im[x1:x2,y1:y1+2] = color
                im[x1:x1+2,y1:y2] = color
                im[x2-2:x2,y1:y2] = color
                im[x1:x2,y2-2:y2] = color
                #cv2.rectangle(im,point1,point2,color,3)
                #im[bbox[1]:bbox[1]+10,bbox[0]:bbox[2]] = color
                #cv2.putText(im,category_name,(bbox[0],bbox[1]+8),2,0.5,(0,0,0))
                #print (category_name)
                #print (point1,point2,area_no_drew_point1,area_no_drew_point2)
                #print ('**********************')
                #print (((x1+x2)/2),((y1+y2)/2))
                if area_no_drew_point1[0] < (x1 + x2)/2 < area_no_drew_point2[0] and  area_no_drew_point1[1] < (y1 + y2)/2 < area_no_drew_point2[1]:
                    continue
                imcopy[x1:x2,y1:y1+2] = color
                imcopy[x1:x1+2,y1:y2] = color
                imcopy[x2-2:x2,y1:y2] = color
                imcopy[x1:x2,y2-2:y2] = color
    return im,imcopy

class DetectronInfer():
    def __init__(self,cfgPath,weights,gpu_id,if_visual):
        self.gpu_id = gpu_id
        self.cfgPath = cfgPath
        self.weights = weights
        self.if_visual = if_visual
        merge_cfg_from_file(self.cfgPath)
        assert_and_infer_cfg(cache_urls = False,make_immutable=False)
        self.model = infer_engine.initialize_model_from_cfg(self.weights,gpu_id=self.gpu_id)
    
    def infer(self,im):
        if im is None:
            return None
        im_height = im.shape[0]
        im_width = im.shape[1]
        timers = defaultdict(Timer)
        with c2_utils.NamedCudaScope(self.gpu_id):
            cls_boxes, cls_segms, cls_keyps = infer_engine.im_detect_all(
                self.model, im, None, timers=timers
            )
        boxes, segms, keyps, classes = convert_from_cls_format(cls_boxes,cls_segms,cls_keyps)
        if self.if_visual:
            return visual_all_box(im,boxes,classes),boxes,classes
        else:
            return boxes,classes,segms

def destroy_all():
    workspace.ResetWorkspace()

if __name__ == "__main__":
    weightsPath = '/mnt/hdd2/workspace/zhanghang/dataset/model/e2e_mask_rcnn_R-101-FPN_2x.pkl'
    cfgPath = '/mnt/hdd2/workspace/zhanghang/dataset/model/e2e_mask_rcnn_R-101-FPN_2x.yaml'
    if_visual  = False

    detector1 = DetectronInfer(cfgPath,weightsPath,gpu_id=1, if_visual=if_visual)
    detector2 = DetectronInfer(cfgPath,weightsPath,gpu_id=2, if_visual= if_visual)
    filename = "/detectron/demo/15673749081_767a7fa63a_k.jpg"
    im = cv2.imread(filename)

    print (detector1.infer(im))
    print (detector2.infer(im))
    
"""
    import threading
    class myThread(threading.Thread):
        def __init__(self,detector,count,thread_id,im):
            threading.Thread.__init__(self)
            self.count = count
            self.detector = detector
            self.thread_id = thread_id
            self.im = im
        def run(self):
            while  self.count:
                boxes,classes = self.detector.infer(im)
                print(self.thread_id,boxes[0],classes[0])
                self.count -= 1

    thread1 = myThread(detector1,10,1,im)
    thread2 = myThread(detector2,10,2,im)
    
    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()            
"""



