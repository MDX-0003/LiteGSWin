import os
import pycolmap
import argparse

import multiprocessing
import cv2
import numpy as np
# The project folder must contain a folder "images" with all the images.
colmap_path = "colmap"
args = None
res =[]

def worker(j,frame_num):
    data_path = args.data_path
    image_path = "{}/images".format(data_path)
    
    dense_path ="{}/dense".format(args.output_path)
    os.system("rm -rf {}".format(dense_path))
    os.makedirs(dense_path,exist_ok=True)
    cali_path = args.cali_path + "/sparse/0"
    pycolmap.undistort_images(output_path=dense_path,input_path=cali_path,image_path=image_path)
    
if __name__ == '__main__':
    import time
# 暂停 2 秒
    parser = argparse.ArgumentParser(description="Process data")
    parser.add_argument("--data_path", type=str, default = "")
    parser.add_argument("--start", type=int, default = 0)
    parser.add_argument("--end", type=int, default = 1)
    parser.add_argument("--cali_path", type=str, default = "")
    parser.add_argument("--output_path", type=str, default = None)

    args = parser.parse_args()
    max_threads = 20
    pool = multiprocessing.Pool(processes=max_threads)
    frame_num = 1000
    from tqdm import tqdm 
    
    file_num = os.listdir(args.output_path)
    for name in tqdm(file_num):
        pool.apply_async(worker,args= (name, frame_num))
    pool.close()
    pool.join()
    print('Main process continues to run')