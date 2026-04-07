# Kata DinD overlay2 修复

## 问题

使用 kata runtime（`io.containerd.kata.v2`）启动的 sandbox，内部 Docker（DinD）无法使用 `overlay2` storage driver。

---

## 根因分析

### 旧方案调用链

**宿主机侧（`docker.py`）**：
1. `truncate` 创建 sparse 文件（`.img`）
2. `mkfs.ext4 -F <img>` 直接格式化镜像文件
3. `-v /data/docker-disk/<name>.img:/docker-disk.img` 挂载进容器

**容器内侧（`docker_run.sh`）**：
```bash
mknod -m 660 /dev/loop$i b 7 $i   # 手动创建 loop 设备
mount -o loop /docker-disk.img /var/lib/docker
```

### 为什么 overlay2 失败

kata 容器中，`-v` 挂载的文件通过 **virtio-fs / 9p** 协议传入 VM。在 9p 文件上执行 `mount -o loop` 得到的是一个 **loop 设备 backed by 9p**。当 Docker 尝试在 `/var/lib/docker`（loop-on-9p）上初始化 overlay2 时，内核拒绝，因为 overlayfs 要求 upperdir 所在文件系统支持 `trusted.*` xattr，而 9p 不支持：

```
overlay: filesystem on '/var/lib/docker/overlay2' not supported as upperdir
```

---

## 修复方案

关键思路：将 `.img` 在宿主机上 attach 到 loop 设备，通过 `--device` 传入 kata。kata 会将 block device 转换为 VM 内的 **virtio-blk** 设备，guest 看到的是真实块设备，overlay2 可以正常运行在 ext4 之上。

### 宿主机侧变更（`rock/deployments/docker.py`）

| 步骤 | 旧行为 | 新行为 |
|------|--------|--------|
| 格式化 | `mkfs.ext4 -F <img>` | `losetup -f --show <img>` 得到 `/dev/loopN`，再 `mkfs.ext4 -F -L kata-docker /dev/loopN` |
| 记录设备 | 无 | loop 设备路径写入 `<name>.loop` 文件 |
| docker run 参数 | `-v <img>:/docker-disk.img` | `--device /dev/loopN:/dev/loopN` |
| 清理 | 删 `.img` | `losetup -d /dev/loopN`，删 `.loop` 和 `.img` |

新增方法 `_get_kata_loop_device_path()`，返回 `.loop` 文件路径，用于跨方法共享 loop 设备名。

### 容器内侧变更（`rock/rocklet/local_files/docker_run.sh`）

```bash
# 旧
mknod -m 660 /dev/loop$i b 7 $i
mount -o loop /docker-disk.img /var/lib/docker

# 新
mount LABEL=kata-docker /var/lib/docker
```

通过 ext4 卷标（`-L kata-docker`，格式化时设置）定位块设备，无需硬编码设备路径（kata 将 block device 映射为 `/dev/vdX` 等，路径因配置而异）。

---

## 涉及文件

- `rock/deployments/docker.py` — `_get_kata_loop_device_path`、`_prepare_kata_disk`、`_cleanup_kata_disk`、`_start` 中的 docker run 参数构建
- `rock/rocklet/local_files/docker_run.sh` — `setup_kata_dind`
