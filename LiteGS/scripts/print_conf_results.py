import pandas as pd

# ==========================================
# 1. 读取并预处理数据
# ==========================================
try:
    df = pd.read_csv('./output/litegs_results_freeze.csv')
except FileNotFoundError:
    print("未找到 ./output/litegs_results_freeze.csv，请检查路径。")
    exit()

df = df.groupby(['scene', 'primitives']).mean().reset_index()
if 'repeat_i' in df.columns:
    df = df.drop(columns=['repeat_i'])

# ==========================================
# 2. 定义配置与数据集映射
# ==========================================
big_conf = {
    "bicycle": 2000000,
    "flowers": 1000000,
    "garden": 2000000,
    "stump": 1000000,
    "treehill": 800000,
    "room": 800000,
    "counter": 600000,
    "kitchen": 1000000,
    "bonsai": 800000,
    "truck": 600000,
    "train": 600000,
    "drjohnson": 800000,
    "playroom": 500000
}

datasets = {
    "mipnerf360": ["bicycle", "flowers", "garden", "stump", "treehill", "room", "counter", "kitchen", "bonsai"],
    "tat": ["truck", "train"],
    "db": ["drjohnson", "playroom"],
}

# ==========================================
# 3. 提取指定配置的场景数据
# ==========================================
# 优化：使用列表收集结果，最后一次性 concat，运行效率更高且不会报 Warning
scene_results_list = []
for scene, conf in big_conf.items():
    results = df[(df['scene'] == scene) & (df['primitives'] == conf)]
    if not results.empty:
        scene_results_list.append(results)
    else:
        print(f"[警告] 未在 csv 中找到匹配的数据: Scene={scene}, Primitives={conf}")

# 合并所有符合条件的场景数据
if scene_results_list:
    scene_results = pd.concat(scene_results_list, ignore_index=True)
else:
    scene_results = pd.DataFrame(columns=['scene', 'primitives', 'time', "SSIM_test", "PSNR_test", "LPIPS_test"])

# ==========================================
# 4. 按数据集计算均值 (Dataset-level Aggregation)
# ==========================================
dataset_rows = []
for dataset_name, scenes in datasets.items():
    # 筛选出属于当前数据集的场景
    ds_data = scene_results[scene_results['scene'].isin(scenes)]
    
    if not ds_data.empty:
        # 计算该数据集下的各项指标均值
        mean_vals = ds_data[['primitives', 'time', 'SSIM_test', 'PSNR_test', 'LPIPS_test']].mean()
        
        dataset_rows.append({
            'dataset': dataset_name,
            'primitives': mean_vals['primitives'],
            'time': mean_vals['time'],
            'PSNR_test': mean_vals['PSNR_test'],
            'SSIM_test': mean_vals['SSIM_test'],
            'LPIPS_test': mean_vals['LPIPS_test']
        })

dataset_results = pd.DataFrame(dataset_rows)

# ==========================================
# 5. 格式化输出 (方便填入 LaTeX 表格)
# ==========================================
print("\n" + "="*50)
print(" 📊 Dataset Averages (Ready for LaTeX Table) ")
print("="*50)

# 对输出进行四舍五入格式化，PSNR保留2位小数，SSIM/LPIPS保留3位小数，Time/Primitives转为整数
for index, row in dataset_results.iterrows():
    print(f"Dataset: {row['dataset'].upper()}")
    print(f"  - Primitives (avg) : {int(row['primitives']):,}")
    print(f"  - Time (avg)       : {int(row['time'])} s")
    print(f"  - PSNR             : {row['PSNR_test']:.2f}")
    print(f"  - SSIM             : {row['SSIM_test']:.3f}")
    print(f"  - LPIPS            : {row['LPIPS_test']:.3f}")
    print("-" * 30)
