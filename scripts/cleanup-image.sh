#!/bin/bash
# 镜像构建完成后垃圾清理，减小镜像体积
# 在 Dockerfile 最后 RUN 阶段执行

set -e

echo "**** 开始镜像垃圾清理 ****"

# 1. APT 缓存
apt-get clean 2>/dev/null || true
rm -rf /var/lib/apt/lists/* 2>/dev/null || true
rm -rf /var/cache/apt/archives/*.deb 2>/dev/null || true
rm -rf /var/cache/apt/archives/partial/* 2>/dev/null || true

# 2. pip 缓存
pip3 cache purge 2>/dev/null || true
rm -rf /root/.cache/pip 2>/dev/null || true
rm -rf /root/.local/share/pip 2>/dev/null || true

# 3. 临时文件
rm -rf /tmp/* 2>/dev/null || true
rm -rf /var/tmp/* 2>/dev/null || true
rm -rf /tmp/.* 2>/dev/null || true

# 4. 日志（空文件保留，清内容）
find /var/log -type f -name "*.log" -exec truncate -s 0 {} \; 2>/dev/null || true
find /var/log -type f -name "*.gz" -delete 2>/dev/null || true
find /var/log -type f -name "*.1" -delete 2>/dev/null || true

# 5. 文档与手册（可选，节省约 50-100MB）
rm -rf /usr/share/doc/* 2>/dev/null || true
rm -rf /usr/share/man/* 2>/dev/null || true
rm -rf /usr/share/info/* 2>/dev/null || true
rm -rf /usr/share/lintian 2>/dev/null || true

# 6. 其他缓存
rm -rf /root/.cache 2>/dev/null || true
rm -rf /var/cache/fontconfig/* 2>/dev/null || true
rm -rf /var/cache/ldconfig/* 2>/dev/null || true

# 7. 缩略图（可重建）
rm -rf /root/.thumbnails 2>/dev/null || true

# 8. 可选：删除 libtool 归档（通常可安全删除）
find /usr -name "*.la" -delete 2>/dev/null || true

echo "**** 镜像垃圾清理完成 ****"
