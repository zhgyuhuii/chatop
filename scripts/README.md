# 构建脚本

## cleanup-image.sh

镜像构建完成后的垃圾清理脚本，用于减小最终镜像体积。

**清理内容：**
- APT 缓存与包列表
- pip 缓存
- 临时文件 (/tmp, /var/tmp)
- 日志文件
- 文档、手册、info 页
- 各类缓存（fontconfig、ldconfig 等）
- libtool 归档 (*.la)

**使用：** 由 Dockerfile 在构建最后阶段自动调用，无需手动执行。
