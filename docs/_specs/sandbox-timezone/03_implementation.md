# Sandbox Timezone — Implementation Plan

## 背景

Docker sandbox 此前未设置标准的 `TZ` 环境变量，导致容器内系统时区为 UTC。具体表现为：文件修改时间按 UTC 记录，前端展示时与用户本地时间存在偏差；`date`、`ls -l` 等系统命令输出 UTC 时间，与用户预期不符。

考虑到 sandbox 镜像来源多样且不可控，本次实现采用 POSIX TZ 格式的运行时方案，而不是依赖镜像内 tzdata 的 IANA 方案。

---

## IANA 与 POSIX TZ 格式

Linux 系统的 `TZ` 环境变量支持两种格式，它们的工作方式和依赖条件完全不同：

### IANA 格式（又称 Olson / zoneinfo）

```
TZ=Asia/Shanghai
TZ=America/New_York
TZ=Europe/London
```

- 引用 IANA 时区数据库中的地理时区标识
- 系统通过查找 `/usr/share/zoneinfo/Asia/Shanghai` 等文件来解析时区规则
- **依赖镜像内安装 `tzdata` 包**，否则无法解析，回退为 UTC
- 包含完整的历史规则（夏令时切换、历史偏移变更等）
- Python 的 `zoneinfo.ZoneInfo()` 和 `pytz.timezone()` 使用此格式

### POSIX 格式

```
TZ=CST-8
TZ=EST5EDT
TZ=UTC0
```

- 直接在字符串中描述时区偏移规则，不依赖任何外部文件
- 格式为 `<缩写><偏移>[<夏令时缩写>[<夏令时偏移>][,<切换规则>]]`
- **注意 POSIX 偏移符号与 ISO 8601 相反**：`CST-8` 表示 UTC**+**8（负号 = 东偏移）
- 不包含历史规则，表达的是固定偏移或简单的夏令时切换
- 任何 Linux 系统均可解析，无需 tzdata

### 本项目的选择

| 变量 | 格式 | 默认值 | 消费方 | 原因 |
|------|------|--------|--------|------|
| `TZ` | POSIX | `CST-8` | 容器内系统命令（`date`、`ls -l`、`stat`） | 不依赖 tzdata，适配不可控镜像 |
| `ROCK_TIME_ZONE` | IANA | `Asia/Shanghai` | Python 应用层（`pytz`、`zoneinfo`、logger） | Python 库需要 IANA 名称 |

两者不能合并：POSIX 格式无法被 `pytz.timezone()` / `zoneinfo.ZoneInfo()` 解析；IANA 格式在无 tzdata 的容器内会静默回退为 UTC。

---

## File Changes

| 文件 | 修改类型 | 说明 |
|------|------|------|
| `rock/env_vars.py` | 修改 | 新增 `TZ` 环境变量读取，默认值为 `CST-8` |
| `rock/deployments/docker.py` | 修改 | 在 `docker run` 环境变量中追加 `TZ={env_vars.TZ}` |
| `tests/unit/test_envs.py` | 修改 | 验证 `TZ` 默认值和系统环境读取逻辑 |
| `tests/unit/rocklet/test_docker_deployment.py` | 修改 | 验证真实 Docker 容器内可读取到 `TZ=CST-8` |

---

## Core Logic

### 变更 1：新增 `TZ` env var 读取

文件：`rock/env_vars.py`

```python
"TZ": lambda: os.getenv("TZ", "CST-8")
```

含义：
- 优先读取宿主机当前环境中的 `TZ`
- 若未设置，则回退到 `CST-8`

### 变更 2：Docker sandbox 透传 `TZ`

文件：`rock/deployments/docker.py`

```python
env_arg.extend(["-e", f"ROCK_TIME_ZONE={env_vars.ROCK_TIME_ZONE}"])
env_arg.extend(["-e", f"TZ={env_vars.TZ}"])
```

含义：
- 保持原有 `ROCK_TIME_ZONE`
- 新增标准 `TZ` 透传

---

## Why POSIX (`CST-8`) Instead of IANA (`Asia/Shanghai`)

1. **镜像不可控**
   - 无法保证业务镜像都带 `tzdata`（提供 `/usr/share/zoneinfo/` 数据）
   - 如果传入 `TZ=Asia/Shanghai` 但镜像内无对应 zoneinfo 文件，系统会静默回退为 UTC，比不传 `TZ` 更容易误导用户
   - 无法要求所有镜像统一重建

2. **需求聚焦于正确的时间展示**
   - 目标是让文件修改时间和系统命令输出与用户时区一致，消除前端展示偏差
   - 不要求完整历史时区规则或夏令时切换
   - POSIX 格式的固定偏移足以满足

3. **实现和维护成本更低**
   - POSIX 格式由内核直接解析，不引入镜像层依赖
   - 不引入挂载 `/etc/localtime` 的宿主机耦合

---

## Validation Plan

### 用例 1：默认值回退

- 清除宿主机环境中的 `TZ`
- 读取 `env_vars.TZ`
- 预期结果：`CST-8`

### 用例 2：读取宿主机环境

- 宿主机设置 `TZ=CST-8`
- 读取 `env_vars.TZ`
- 预期结果：`CST-8`

### 用例 3：真实 Docker 容器验证

- 设置宿主机环境 `TZ=CST-8`
- 启动真实 Docker sandbox
- 在容器内执行：

```bash
/bin/sh -lc 'printf %s "$TZ"'
```

- 预期结果：输出 `CST-8`

---

## Rollback & Compatibility

- 回滚仅需恢复 `rock/env_vars.py` 与 `rock/deployments/docker.py`
- 测试回滚仅需移除新增的 `TZ` 验证用例
- 对现有对外接口无兼容性影响

---

## Future Evolution

若未来 sandbox 镜像体系变为统一可控，可进一步评估升级为：

1. `TZ=Asia/Shanghai` + 镜像内置 `tzdata`
2. 挂载标准 zoneinfo 文件到 `/etc/localtime`
3. 在可控镜像上提供完整 IANA 时区语义

在当前阶段，这些都不是默认路径，原因是它们对镜像可控性有更高要求。
