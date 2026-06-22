### 配置环境
第一步，先 nvcc -V，查看一下显卡驱动的版本号，如果低于12要从英伟达官网下载，可以下载12.4的，链接：https://developer.nvidia.com/cuda-12-4-0-download-archive?target_os=Windows&target_arch=x86_64&target_version=11&target_type=exe_network

下载完一般默认会设置成12.4版本，把当前的终端或vscode关掉再尝试一次nvcc -V.如果还是11.8，先检查环境变量里的CUDA_PATH是不是12.4的，如果没问题，可以选择打开电脑的命令提示符进行后续的配置。

### 用anaconda配置python环境 
1. 创建环境

    ```bash
    conda create -n litegs python=3.11
    conda activate litegs
    ```

2. 下载pytorch （这里是12.4的pytorch，如果是其他版本的pytorch可以去官网上找，一般2.7.0左右的版本都可以，网址：https://pytorch.org/get-started/previous-versions/）
    ```bash
    pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124       
    ```

3. 配置其他的库
    ```bash
    pip install -r requirement.txt
    pip install litegs\submodules\gaussian_raster --no-build-isolation
    pip install litegs\submodules\fused_ssim --no-build-isolation
    pip install litegs\submodules\simple-knn --no-build-isolation
    ```

### 运行脚本：

`python ./example_train.py --sh_degree 3 -s C:\Users\ASUS\Desktop\data\103-2026-06-02-115225\dense -i C:\Users\ASUS\Desktop\data\103-2026-06-02-115225\dense\images -m C:\Users\ASUS\Desktop\output\103-2026-06-02-115225 -r 2 --target_primitives 300000`

### args讲解：

1.   `--sh_degree`\
    sh球谐函数的阶数，0阶就没有view-independent 的颜色区分，一般用3阶train在多视角下颜色会比较好

2. `-s` \
    数据的存放路径，一般是指向到存放了相机参数的sparse文件夹所在的目录

3. `-i` \
    去畸变后的图片所在的目录

4. `-m`\
    model_path, 最后的结果保存的路径，我们会自动保存2min，2.5min和3min的结果以及最终30000iteraion的结果

5. `-r`\
    分辨率的调控，-r 1 代表了就是当前图片的分辨率，-r 2 是把当前的图像的H和W都除2后的分辨率，测试下来-r 1 和 -r 2的质量其实差不多，但是-r 2 会快很多

6. `--target_primitives`\
    目标gs数，对于现在的场景来说，我们觉得30w的点数是一个比较好的结果，可以任意调控

7. `--iterations`\
    训练的轮数，一般是30000

在文件LiteGS\litegs\arguments.py里还有更多的参数可以调整

### 数据的格式
```shell
<location>
├── dense
│    ├── images              
│    │   └──XXX.jpg         - 去畸变的图片
│    ├── sparse   - 没有畸变参数的相机参数和图片信息
│    │   └──0
│    │      └──cameras.bin 没有畸变参数的相机参数
│    │      └──......
│    │ 
│    └── stereo
│
├── images
│    ├── XXX.jpg         - 没有去畸变的图片
├── sparse
│    └──0
│       └──cameras.bin 有畸变参数的相机参数
```

# 注意
一定要把sparse下的所有文件都塞到0这个文件夹里，这样代码才能跑通

### cameras_bin_to_json.py
`python cameras_bin_to_json.py --cameras_bin /data_path/dense/sparse/0/cameras.bin -o /output_path/cameras_1.json`