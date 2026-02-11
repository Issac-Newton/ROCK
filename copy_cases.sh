#!/bin/bash

# 源目录和目标目录
SOURCE_DIR="/root/terminal-bench-datasets/datasets/swebench-verified"
TARGET_DIR="/root/rock_opensource/ROCK/swebench-verified"

# 确保目标目录存在
mkdir -p "$TARGET_DIR"

# 读取 docker_images.jsonl 的前20行，提取 case ID
head -20 /root/rock_opensource/ROCK/docker_images.jsonl | while IFS= read -r line; do
    # 从 JSON 中提取 docker_image 字段的值
    docker_image=$(echo "$line" | grep -o '"docker_image": *"[^"]*"' | sed 's/"docker_image": *"\(.*\)"/\1/')
    
    # 从 docker 镜像名称中提取 case ID (冒号后面的部分，去掉 sweb.eval.x86_64. 前缀)
    case_id=$(echo "$docker_image" | awk -F':' '{print $2}' | sed 's/sweb\.eval\.x86_64\.//')
    
    echo "处理 case: $case_id"
    
    # 检查源文件是否存在并复制
    if [ -f "$SOURCE_DIR/$case_id" ]; then
        cp "$SOURCE_DIR/$case_id" "$TARGET_DIR/"
        echo "  ✓ 已复制: $case_id"
    elif [ -d "$SOURCE_DIR/$case_id" ]; then
        cp -r "$SOURCE_DIR/$case_id" "$TARGET_DIR/"
        echo "  ✓ 已复制目录: $case_id"
    else
        echo "  ✗ 未找到: $case_id"
    fi
done

echo ""
echo "复制完成！"
echo "已复制的文件列表："
ls -la "$TARGET_DIR"
