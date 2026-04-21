# Sandbox Timezone — Requirement Spec

## Background

ROCK 的 Docker sandbox 启动流程此前只向容器传递了 `ROCK_TIME_ZONE`，该变量供 ROCK 自身日志和调度逻辑使用（需要 IANA 时区名，如 `Asia/Shanghai`），但并未设置标准的 `TZ` 环境变量。这导致容器内的系统时区始终为 UTC，产生两个具体问题：

1. **文件修改时间偏差**：sandbox 内创建或修改的文件，其 `mtime` 按 UTC 记录。前端展示文件列表时，用户看到的修改时间与本地实际时间存在时差（东八区场景下差 8 小时）。
2. **系统命令时间不一致**：`date`、`ls -l` 等系统命令输出 UTC 时间，与用户预期不符。

本次修复目标是：
- 让 sandbox 内的系统时区跟随 `TZ` 环境变量，使文件修改时间和系统命令输出与用户所在时区一致
- 前端展示文件信息时不再有时差偏差
- 在镜像来源多样、不可控的前提下保持可用
- 不要求业务镜像预装 `tzdata`

在方案评估过程中，主要有两类候选路径：

1. **当前方案**：向 `docker run` 传递标准环境变量 `TZ`，默认值设置为 `CST-8`
2. **备选方案**：向 `docker run` 传递 `TZ=Asia/Shanghai`，并依赖镜像内存在 `tzdata` / zoneinfo 数据

---

## In / Out

### In（本次要做的）

1. **Docker sandbox 启动时传递标准 `TZ` 环境变量**
   - 从宿主机当前系统环境读取 `TZ`
   - 当宿主机未设置 `TZ` 时，默认使用 `CST-8`

2. **保持现有 `ROCK_TIME_ZONE` 行为不变**
   - `ROCK_TIME_ZONE` 使用 IANA 时区名（如 `Asia/Shanghai`），供 ROCK 日志、调度器、时间戳格式化等 Python 应用层逻辑使用
   - `TZ` 使用 POSIX 格式（如 `CST-8`），供容器内系统层使用
   - 两者职责不同，不做合并

3. **让容器内文件时间和系统命令与用户时区一致**
   - `date`、`ls -l` 等命令按 `TZ` 显示本地时间
   - 文件 `mtime` 的展示格式与用户预期时区一致
   - 前端读取文件修改时间时不再出现时差偏差

4. **补充文档与验证**
   - 明确记录 IANA 与 POSIX TZ 格式的区别
   - 明确记录选择当前方案的原因和边界

### Out（本次不做的）

- 不修改镜像内容
- 不要求所有业务镜像安装 `tzdata`
- 不挂载 `/etc/localtime` 或宿主机 zoneinfo 文件
- 不把系统层时区方案扩展为严格的 IANA 地理时区语义
- 不修改 ROCK 内部 `ROCK_TIME_ZONE` 的默认值

---

## Candidate Comparison

### 方案 A：当前方案（`TZ=CST-8`）

**说明**：
- 在 `docker run` 时传递 `-e TZ=<value>`
- 默认值为 `CST-8`
- `CST-8` 是 POSIX TZ 字符串，表达固定 `UTC+8`

**优点**：
- 不依赖镜像内有 `tzdata`
- 对精简镜像、第三方镜像更稳
- 能满足当前目标：让 `date` 等系统命令显示东八区时间
- 改动面小，只需在 env vars 和 docker 启动参数中补一层透传

**局限**：
- 表达的是固定 `UTC+8`，不是完整 `Asia/Shanghai` 地理时区
- 不包含历史夏令时/历史偏移规则
- 输出的时区缩写可能是 `CST`，语义不如 `Asia/Shanghai` 直观

### 方案 B：`TZ=Asia/Shanghai` + `tzdata`

**说明**：
- 在 `docker run` 时传递 `-e TZ=Asia/Shanghai`
- 依赖镜像内存在 `/usr/share/zoneinfo/Asia/Shanghai`，通常来自 `tzdata`

**优点**：
- 语义更标准，属于 IANA 地理时区标识
- 对历史时区规则表达更完整
- 某些依赖 zoneinfo 的程序表现更标准

**局限**：
- 依赖镜像可控且预装 `tzdata`
- 对第三方镜像、最小镜像不可靠
- 与本次约束冲突：当前 sandbox 镜像来源多样，无法要求镜像统一带 `tzdata`

### 差异总结

| 维度 | 当前方案：`TZ=CST-8` | `TZ=Asia/Shanghai` + `tzdata` |
|------|------|------|
| 依赖镜像内 `tzdata` | 否 | 是 |
| 适配不可控第三方镜像 | 强 | 弱 |
| `date` 当前东八区显示 | 可满足 | 可满足 |
| IANA 地理时区语义 | 不完整 | 完整 |
| 历史规则/夏令时语义 | 不支持 | 支持 |
| 当前问题适配度 | 高 | 中 |

---

## Why Current Solution

选择当前方案的原因：

1. **问题目标明确且偏运行时**
   - 当前要解决的是 sandbox 内 `date` 等系统命令显示东八区时间
   - 不是要在所有镜像中构建完整的 `Asia/Shanghai` 历史时区语义

2. **镜像不可控是第一约束**
   - sandbox 可能来自不同业务镜像、第三方镜像、精简镜像
   - 不能假设这些镜像都内置 `tzdata`
   - 也不能要求调用方为了时区能力重新构建镜像

3. **当前方案在约束下成功率最高**
   - `CST-8` 不依赖 zoneinfo 数据库
   - 对最小依赖场景更稳
   - 可以直接通过 `docker run` 环境变量完成

4. **保留未来升级空间**
   - 当前方案不阻止未来在可控镜像体系中升级为 `TZ=Asia/Shanghai` + `tzdata`
   - 也不影响 ROCK 继续保留 `ROCK_TIME_ZONE=Asia/Shanghai` 作为应用层语义配置

---

## Acceptance Criteria

- **AC1**：Docker sandbox 启动时，`docker run` 包含 `TZ` 环境变量
- **AC2**：当宿主机未设置 `TZ` 时，传入容器的默认值为 `CST-8`
- **AC3**：当宿主机设置了 `TZ` 时，容器内读取到的值与宿主机一致
- **AC4**：容器内执行 `printf %s "$TZ"` 返回期望值
- **AC5**：容器内文件修改时间（`ls -l`、`stat`）按 `TZ` 指定的时区显示，前端获取后无时差偏差
- **AC6**：现有 `ROCK_TIME_ZONE` 行为不变（IANA 格式，供 Python 应用层使用）
- **AC7**：文档明确记录 IANA 与 POSIX TZ 格式的差异，以及两个变量各自的职责

---

## Constraints

- 不引入新的 Python 依赖
- 不要求修改用户镜像 Dockerfile
- 不依赖容器内 `/usr/share/zoneinfo` 是否存在
- 不修改 sandbox 启动 API 的对外字段

---

## Risks & Rollout

- **风险**：`CST-8` 仅表达固定东八区，不是完整 `Asia/Shanghai` 语义
- **风险**：部分应用若显式依赖 IANA zone name，仍可能需要上层自行处理
- **回滚**：仅涉及 `rock/env_vars.py` 与 `rock/deployments/docker.py`，回滚成本低
- **上线策略**：无数据库变更，无协议破坏，可直接随 admin / deployment 代码发布
