import os
import argparse

def batch_rename(img_dir, old_str, new_str):
    # 计数器
    success_count = 0
    
    # 检查路径是否存在
    if not os.path.exists(img_dir):
        print(f"错误: 目标路径不存在 -> {img_dir}")
        return

    print(f"开始处理目录: {img_dir}")
    print(f"替换规则: 将文件名中的 '{old_str}' 替换为 '{new_str}'")
    print("-" * 50)

    for filename in os.listdir(img_dir):
        # 检查文件名中是否包含要替换的字符串，且是 .jpg 结尾
        if old_str in filename and filename.endswith(".jpg"):
            # 生成新文件名
            new_filename = filename.replace(old_str, new_str)
            
            old_path = os.path.join(img_dir, filename)
            new_path = os.path.join(img_dir, new_filename)
            
            try:
                # 直接重命名文件
                os.rename(old_path, new_path)
                success_count += 1
            except Exception as e:
                print(f"重命名失败: {filename} -> {e}")

    print("-" * 50)
    print(f"文件名替换完成！成功修改了 {success_count} 个文件。")

if __name__ == "__main__":
    # 创建参数解析器
    parser = argparse.ArgumentParser(description="批量修改图片文件名中的特定字符串（例如时间戳）")
    
    # 添加命令行参数
    parser.add_argument("--dir", type=str, required=True, help="图片所在的文件夹路径")
    parser.add_argument("--old", type=str, required=True, help="需要被替换的旧字符串（如：115334）")
    parser.add_argument("--new", type=str, required=True, help="替换后的新字符串（如：115225）")
    
    # 解析参数
    args = parser.parse_args()
    
    # 执行重命名
    batch_rename(args.dir, args.old, args.new)