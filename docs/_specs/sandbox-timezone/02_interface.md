# Sandbox Timezone — Interface Contract

## 1. Runtime Environment Variables

### 新增/使用的标准变量

| 变量 | 来源 | 默认值 | 用途 |
|------|------|------|------|
| `TZ` | 宿主机系统环境 `TZ` | `<+08>-8` | 提供给容器内系统命令和依赖标准时区环境变量的程序 |
| `ROCK_TIME_ZONE` | ROCK env vars | `Asia/Shanghai` | 提供给 ROCK 自身日志、调度等应用层逻辑 |

### 行为规则

- 若宿主机设置了 `TZ`，则 `docker run` 传入该值
- 若宿主机未设置 `TZ`，则 `docker run` 传入 `<+08>-8`
- `ROCK_TIME_ZONE` 继续按原逻辑传入，默认 `Asia/Shanghai`
- 两者可以同时存在：
  - `TZ` 面向系统/标准运行时
  - `ROCK_TIME_ZONE` 面向 ROCK 应用自身

---

## 2. Docker Run Contract

### 环境变量注入

Docker sandbox 启动时，环境变量集合至少包含：

```bash
-e ROCK_TIME_ZONE=<rock_time_zone>
-e TZ=<tz>
```

在默认情况下等价于：

```bash
-e ROCK_TIME_ZONE=Asia/Shanghai
-e TZ=<+08>-8
```

### 示例

#### 示例 1：宿主机未设置 `TZ`

```bash
docker run ...   -e ROCK_TIME_ZONE=Asia/Shanghai   -e TZ=<+08>-8   ...
```

#### 示例 2：宿主机设置 `TZ=UTC`

```bash
docker run ...   -e ROCK_TIME_ZONE=Asia/Shanghai   -e TZ=UTC   ...
```

---

## 3. Container-side Observable Behavior

### 可观测方式

| 检查方式 | 预期 |
|------|------|
| `printf %s "$TZ"` | 返回注入后的 `TZ` 值 |
| `date` | 在大多数标准运行时中按 `TZ` 解释当前时间 |

### 边界说明

- `TZ=<+08>-8` 表达固定 `UTC+8`
- 不保证严格等价于 IANA `Asia/Shanghai`
- 不保证提供历史时区规则或 zoneinfo 文件能力

---

## 4. 与 `TZ=Asia/Shanghai + tzdata` 的接口差异

| 项目 | 当前方案 | `TZ=Asia/Shanghai + tzdata` |
|------|------|------|
| 注入值 | `<+08>-8` | `Asia/Shanghai` |
| 是否需要 zoneinfo 文件 | 否 | 是 |
| 是否要求镜像预装 `tzdata` | 否 | 是 |
| 系统命令对固定东八区显示 | 支持 | 支持 |
| 对地理时区 ID 的表达 | 弱 | 强 |

---

## 5. Backward Compatibility

- `ROCK_TIME_ZONE` 保持不变
- 不新增对外 API 字段
- 不修改 sandbox 启动请求模型
- 仅扩展运行时环境变量集合
