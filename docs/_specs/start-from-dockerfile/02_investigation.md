# Start from Dockerfile — 调研：各 Sandbox 平台如何支持从 Dockerfile 启动

## 概述

调研 Daytona、E2B、Modal、Runloop、GKE、Docker 六个 Sandbox 平台如何实现从 Dockerfile 启动沙箱，为 Rock 的实现提供参考。

---

## 各平台接口定义

### Daytona

**核心类型：**

```python
class Image(BaseModel):
    """不直接构造，通过静态工厂方法创建。"""
    _dockerfile: str = PrivateAttr(default="")
    _context_list: list[Context] = PrivateAttr(default_factory=list)

    @staticmethod
    def from_dockerfile(path: str | Path) -> "Image": ...
    @staticmethod
    def base(image: str) -> "Image": ...

class Resources:
    cpu: int | None = None
    memory: int | None = None   # GiB
    disk: int | None = None     # GiB
    gpu: int | None = None

class CreateSandboxFromImageParams(BaseModel):
    image: str | Image                          # 必填
    resources: Resources | None = None
    env_vars: dict[str, str] | None = None
    auto_stop_interval: int | None = None       # 分钟
    auto_delete_interval: int | None = None
    network_block_all: bool | None = None
    # ... 其他可选字段
```

**启动接口：**

```python
class AsyncDaytona:
    async def create(
        self,
        params: CreateSandboxFromImageParams | CreateSandboxFromSnapshotParams | None = None,
        *,
        timeout: float = 60,
        on_snapshot_create_logs: Callable[[str], None] | None = None,
    ) -> AsyncSandbox: ...
```

- `Image.from_dockerfile(path)` 读取 Dockerfile，自动提取 COPY 依赖的上下文文件
- `create()` 一步完成构建和启动，平台侧处理
- 支持 Snapshot 缓存复用

---

### E2B

**核心类型：**

```python
class TemplateBase:
    def from_dockerfile(self, dockerfile_content_or_path: str) -> TemplateBuilder: ...
    def from_image(self, image: str, username: str | None = None, password: str | None = None) -> TemplateBuilder: ...
```

`from_dockerfile()` 返回 `TemplateBuilder`，支持链式调用追加指令：

```python
class TemplateBuilder:
    def run_cmd(self, command: str | list[str]) -> TemplateBuilder: ...
    def copy(self, src, dest) -> TemplateBuilder: ...
    def set_envs(self, envs: dict[str, str]) -> TemplateBuilder: ...
    def apt_install(self, packages) -> TemplateBuilder: ...
    def pip_install(self, packages) -> TemplateBuilder: ...
    # ... 其他 builder 方法
```

**构建接口：**

```python
class AsyncTemplate(TemplateBase):
    @staticmethod
    async def build(
        template: TemplateBuilder,
        name: str | None = None,
        *,
        alias: str | None = None,
        cpu_count: int = 2,
        memory_mb: int = 1024,
        skip_cache: bool = False,
    ) -> BuildInfo: ...

    @staticmethod
    async def alias_exists(alias: str) -> bool: ...
```

**启动接口：**

```python
class AsyncSandbox:
    @classmethod
    async def create(
        cls,
        template: str | None = None,    # template name 或 ID
        timeout: int | None = None,
        envs: dict[str, str] | None = None,
        allow_internet_access: bool = True,
    ) -> Self: ...
```

- 两步模型：先 `build()` Template，再从 Template `create()` Sandbox
- Template 按 alias 缓存，内容哈希作为 alias 一部分

---

### Modal

**核心类型：**

```python
class Image(_Object):
    """不直接构造，通过静态工厂方法创建。"""

    @staticmethod
    def from_dockerfile(
        path: str | Path,
        *,
        force_build: bool = False,
        context_dir: Path | str | None = None,
        build_args: dict[str, str] = {},
        secrets: Collection[Secret] | None = None,
        gpu: GPU_T = None,
        add_python: str | None = None,
    ) -> "Image": ...

    @staticmethod
    def from_registry(
        tag: str,
        secret: Secret | None = None,
        *,
        force_build: bool = False,
        add_python: str | None = None,
    ) -> "Image": ...
```

**启动接口：**

```python
class Sandbox(_Object):
    @staticmethod
    async def create(
        *args: str,
        app: App | None = None,
        image: Image | None = None,
        cpu: float | tuple[float, float] | None = None,
        memory: int | tuple[int, int] | None = None,    # MiB
        gpu: GPU_T = None,
        timeout: int = 300,
        block_network: bool = False,
        volumes: dict[str | PathLike, Volume | CloudBucketMount] = {},
        env: dict[str, str | None] | None = None,
    ) -> "Sandbox": ...
```

- `Image` 是惰性声明，实际构建在 `Sandbox.create()` 时由平台触发
- 平台内部按内容哈希缓存

---

### Runloop

**核心类型：**

```python
class BlueprintCreateParams(TypedDict, total=False):
    name: Required[str]
    dockerfile: str | None                      # Dockerfile 内容（原始文本）
    build_context: BuildContext | None           # 构建上下文
    build_args: dict[str, str] | None
    launch_parameters: LaunchParameters | None
    # ... 其他可选字段

class BuildContext(TypedDict, total=False):
    object_id: Required[str]                    # storage object ID
    type: Required[Literal["object"]]

class LaunchParameters(BaseModel):
    architecture: Literal["x86_64", "arm64"] | None = None
    custom_cpu_cores: int | None = None
    custom_gb_memory: int | None = None         # GiB
    custom_disk_size: int | None = None         # GiB
    keep_alive_time_seconds: int | None = None
    # ... 其他字段

class BlueprintView(BaseModel):
    id: str
    name: str
    status: Literal["queued", "provisioning", "building", "failed", "build_complete"]
    # ... 其他字段
```

**构建接口：**

```python
class AsyncRunloopSDK:
    storage_object: AsyncStorageObjectOps
    blueprint: AsyncBlueprintOps
    devbox: AsyncDevboxOps

# 上传构建上下文
storage_object = await sdk.storage_object.upload_from_dir(
    dir_path: Path, name: str, ttl: timedelta,
) -> StorageObject

# 创建 Blueprint
blueprint = await sdk.blueprint.create(
    name: str, dockerfile: str, build_context: BuildContext, ...
) -> AsyncBlueprint
```

**启动接口：**

```python
devbox = await sdk.devbox.create_from_blueprint_id(
    blueprint_id: str, name: str | None = None, ...
) -> AsyncDevbox
```

- 三步模型：上传上下文 → 创建 Blueprint → 从 Blueprint 创建 Devbox
- Blueprint 按名称缓存

---

### GKE

无平台 SDK，通过 `gcloud` CLI 和 Kubernetes Python SDK 组合实现。

**构建：**

```bash
gcloud builds submit \
    --tag <registry>/<env_name>:latest \
    --timeout 2400 \
    --machine-type E2_HIGHCPU_8 \
    <environment_dir>
```

**镜像检查：**

```bash
gcloud artifacts docker images describe <image_url>
```

**启动：**

```python
from kubernetes import client as k8s_client

core_api = k8s_client.CoreV1Api()
core_api.create_namespaced_pod(namespace=..., body=pod)
# pod spec 中引用 Cloud Build 产出的镜像
```

- 构建和启动分离：Cloud Build 产出镜像 → Kubernetes 从镜像创建 Pod
- 按 `{environment_name}:latest` 检查 Artifact Registry 中镜像是否存在

---

### Docker

无平台 SDK，直接通过 `docker compose` CLI 操作。

```bash
# 构建
docker compose -f base.yaml -f build.yaml build

# 启动
docker compose ... up --detach --wait
```

- 构建和启动由 compose 统一管理
- 依赖本地 Docker daemon，Docker layer cache 天然缓存

---

## 缓存机制

### Daytona — Snapshot

缓存基于外部预创建的 Snapshot。Snapshot 名称由调用方通过模板字符串指定（如 `harbor__{name}__snapshot`），运行时替换 `{name}` 为 `environment_name`。

```python
snapshot_name = snapshot_template_name.format(name=environment_name)

# 检查 Snapshot 是否存在且可用
snapshot = await daytona.snapshot.get(snapshot_name)   # REST GET，不存在则抛异常
if snapshot.state == SnapshotState.ACTIVE:
    # 从 Snapshot 启动，跳过构建
    params = CreateSandboxFromSnapshotParams(snapshot=snapshot_name, ...)
```

- 缓存 key：调用方指定的 Snapshot 名称
- 内容变更检测：无，Snapshot 必须外部预创建和更新
- `force_build` 无法绕过 Snapshot（如果存在则始终使用）

### E2B — Template 内容哈希

缓存基于 `environment_dir` 目录内容的 SHA-256 哈希，嵌入 Template alias。

```python
# alias 格式：<environment_name>__<sha256[:8]>
template_name = f"{environment_name}__{dirhash(environment_dir, 'sha256')[:8]}".replace(".", "-")

# 检查 Template 是否已存在
exists = await AsyncTemplate.alias_exists(template_name)   # REST GET /templates/aliases/{alias}

if not force_build and exists:
    pass   # 跳过构建，直接用已有 Template 启动
else:
    await AsyncTemplate.build(template=..., alias=template_name, ...)
```

- 缓存 key：`environment_name` + 目录内容哈希
- 内容变更检测：自动，任何文件变化产生新哈希 → 新 alias → 触发重建
- 旧 Template 不会自动清理

### Modal — 平台侧隐式缓存

调用方无需管理缓存。`Image` 对象在 `Sandbox.create()` 时发送给 Modal 服务端，服务端根据完整的镜像定义（Dockerfile 内容、上下文文件、构建参数等）计算缓存 key。

```python
# 调用方代码中无任何缓存逻辑
image = Image.from_dockerfile(path, context_dir=environment_dir)
sandbox = await Sandbox.create(image=image, ...)

# SDK 内部：将完整镜像定义序列化为 protobuf，发送 ImageGetOrCreate 请求
# 服务端判断是否命中缓存，命中则直接返回已有镜像
req = api_pb2.ImageGetOrCreateRequest(image=image_definition, force_build=force_build, ...)
resp = await client.stub.ImageGetOrCreate(req)
```

- 缓存 key：服务端根据镜像定义 protobuf 计算（包含 Dockerfile 内容、上下文文件哈希）
- 内容变更检测：自动，服务端按内容哈希判断
- `force_build` 通过 `Image.from_dockerfile(force_build=True)` 传递

### Runloop — Blueprint 名称查找

缓存基于 Blueprint 名称查找，无内容哈希。

```python
blueprint_name = f"harbor_{environment_name}_blueprint"

# 查找已有 Blueprint：查私有 + 公有列表，取最新的 build_complete 状态
private_page = await client.api.blueprints.list(name=blueprint_name)
public_page  = await client.api.blueprints.list_public(name=blueprint_name)
candidates = [bp for bp in all_blueprints if bp.name == blueprint_name and bp.status == "build_complete"]
candidates.sort(key=lambda bp: bp.create_time_ms, reverse=True)
blueprint_id = candidates[0].id if candidates else None

if not force_build and blueprint_id:
    pass   # 复用已有 Blueprint
else:
    blueprint_id = await client.blueprint.create(name=blueprint_name, dockerfile=..., ...)
```

- 缓存 key：`harbor_{environment_name}_blueprint`（仅名称）
- 内容变更检测：无，`environment_dir` 内容变化但名称不变时，静默复用旧 Blueprint
- 同名 Blueprint 可共存多个，取最新的 `build_complete`

### GKE — Registry 镜像检查

缓存基于 Artifact Registry 中镜像是否存在。

```python
image_url = f"{registry_location}-docker.pkg.dev/{project_id}/{registry_name}/{environment_name}:latest"

# 检查镜像是否存在
check_cmd = ["gcloud", "artifacts", "docker", "images", "describe", image_url, "--project", project_id]
result = await asyncio.create_subprocess_exec(*check_cmd, stdout=DEVNULL, stderr=DEVNULL)
exists = (result.returncode == 0)

if not force_build and exists:
    pass   # 使用已有镜像
else:
    await _build_and_push_image()   # gcloud builds submit，覆盖 :latest
```

- 缓存 key：`{environment_name}:latest`（固定 tag）
- 内容变更检测：无，`environment_dir` 内容变化但名称不变时，静默复用旧镜像
- `force_build=True` 重新构建并覆盖 `:latest`

### Docker — Layer Cache + 进程内锁

缓存依赖 Docker daemon 自身的 layer cache，进程内通过 `asyncio.Lock` 去重并发构建。

```python
# 类级别锁字典
_image_build_locks: dict[str, asyncio.Lock] = {}

# 构建时按 environment_name 加锁
lock = _image_build_locks.setdefault(environment_name, asyncio.Lock())
async with lock:
    await docker_compose(["build"])   # Docker layer cache 处理增量构建
```

- 缓存 key：Docker layer cache（按 Dockerfile 指令 + 文件内容）
- 内容变更检测：自动，Docker 逐层比对，变化的层及后续层重建
- 进程内锁保证同一 `environment_name` 不并发构建，但不跨进程

---

## 构建产物存储

### Daytona — 平台托管 Snapshot

- **产物形式**：Snapshot（平台内部格式，非标准 Docker 镜像）。Snapshot 是一个预配置的沙箱快照，包含 `id`、`name`、`image_name`、`state`、`size`、`cpu/gpu/mem/disk` 等属性
- **存储位置**：Daytona 平台内部 Object Storage（S3 兼容），用户不可直接访问底层存储，通过 SDK/API 管理
- **生命周期**：声明式构建（`Image.from_dockerfile()`）产物自动缓存 24 小时；预创建 Snapshot 永久保留直到手动删除
- **清理方式**：`daytona.snapshot.delete()` / CLI / Dashboard

**构建流程（从 Image 到 Snapshot）：**

1. `Image` 对象收集构建指令（Dockerfile 内容、`pip_install`、`run_commands`、`add_local_file` 等链式调用）
2. 本地文件/目录通过 `ObjectStorage.upload()` 上传到平台 S3 兼容存储（bucket: `daytona-volume-builds`），返回 content hash
3. 平台服务端根据 Image 定义自动创建 Snapshot
4. 从 Snapshot 启动沙箱

**Snapshot 管理接口：**

```python
class AsyncSnapshotService:
    async def create(params: CreateSnapshotParams, *, on_logs=None, timeout=0) -> Snapshot
    async def get(name: str) -> Snapshot
    async def list(page=None, limit=None) -> PaginatedSnapshots
    async def delete(snapshot: Snapshot) -> None
    async def activate(snapshot: Snapshot) -> Snapshot    # 激活已归档的 Snapshot

class CreateSnapshotParams(BaseModel):
    name: str                           # Snapshot 名称
    image: str | Image                  # 镜像定义
    resources: Resources | None = None  # CPU/GPU/内存/磁盘
    entrypoint: list[str] | None = None
    region_id: str | None = None        # 创建 Snapshot 的区域
```

**构建上下文传输：**

```python
class AsyncObjectStorage:
    endpoint_url: str
    aws_access_key_id: str
    aws_secret_access_key: str
    bucket_name: str   # 默认 "daytona-volume-builds"

    async def upload(path: str, organization_id: str) -> str   # 返回 content hash
```

### E2B — Firecracker microVM 快照

- **产物形式**：Firecracker microVM 快照（非标准 Docker 镜像），从 Dockerfile 构建后转换为 VM 快照
- **存储位置**：云对象存储（GCP: GCS bucket / AWS: S3 bucket），元数据存于 PostgreSQL + Redis 缓存
- **生命周期**：永久保留，无自动清理策略；构建失败时自动清理已上传对象
- **清理方式**：`e2b template delete` CLI / API

**快照文件组成：**

每个构建产物（以 `buildID` 为目录）包含以下文件：

| 文件 | 说明 |
|------|------|
| `rootfs.ext4` | ext4 文件系统镜像（VM 磁盘） |
| `rootfs.ext4.header` | block 级别差异头（COW/去重） |
| `memfile` | VM 内存快照（RAM 内容） |
| `memfile.header` | 内存 block 差异头 |
| `snapfile` | Firecracker VM 状态文件（CPU/设备状态） |
| `metadata.json` | 模板元数据（内核版本、FC 版本、环境变量、启动命令、预取映射） |

**构建流程（从 Dockerfile 到 VM 快照）：**

```
OCI 镜像（Docker registry）
    ↓ ToExt4()：提取 OCI layers → overlayFS → rsync 到 ext4
rootfs.ext4（本地构建目录）
    ↓ 启动 Firecracker VM（BusyBox init）→ 执行 provision.sh → 关机
已配置的 rootfs.ext4
    ↓ 启动 Firecracker VM（systemd）→ 逐步执行 Dockerfile 指令 → Pause()
Layer N 快照：(rootfs.ext4.header, memfile.header, snapfile, metadata.json)
    ↓ 并发上传到 GCS/S3
对象存储中的模板产物（按 buildID 组织）
    ↓ 注册到数据库（FinishTemplateBuild）
可运行的沙箱模板
```

每个 Dockerfile 步骤（RUN、COPY 等）生成一层独立的快照，只存储与上一层的 dirty blocks 差异，空间效率高。

**构建 Pipeline（服务端）：**

构建按阶段执行，每个阶段是一个 `BuilderPhase` 接口：

```
BaseBuilder → UserBuilder → StepBuilders（每条指令一个）→ PostProcessingBuilder → OptimizeBuilder
```

**存储架构：**

| 存储层 | Bucket / 位置 | 用途 |
|--------|--------------|------|
| 模板存储 | `TEMPLATE_BUCKET_NAME`（GCS bucket） | 最终快照，永久保存 |
| 构建缓存 | `BUILD_CACHE_BUCKET_NAME`（GCS bucket） | 层级缓存索引 + COPY 文件 tarball |
| 本地 NFS 缓存 | `SharedChunkCacheDir` | block 级别 chunk 缓存（可选，feature flag 控制） |
| 内存缓存 | TTL 25 小时的 `ttlcache` | Template 对象缓存，过期自动清理本地临时文件 |

GCS 客户端通过 gRPC 初始化（`storage.NewGRPCClient`），认证依赖 GCP 默认应用凭证（ADC）。Bucket 名称通过环境变量 `TEMPLATE_BUCKET_NAME` 和 `BUILD_CACHE_BUCKET_NAME` 配置，由 Terraform 创建并通过 Nomad Job 注入。

**缓存去重机制（内容寻址哈希）：**

每个 `BuilderPhase` 实现 `Hash()` 方法，计算当前层的 SHA-256：

| 阶段 | 哈希输入 |
|------|---------|
| Base 层 | `SHA256(provision_version + disk_size + from_image)` |
| Step 层 | `SHA256(上一层 hash + step_type + step_args + files_hash)` |
| Finalize 层 | `SHA256(上一层 hash + "config-run-cmd")` |
| Optimize 层 | `SHA256(上一层 hash + "optimize")` |

缓存查找流程：计算层 hash → 查 `{cacheScope}/index/{hash}` 获取 `buildID` → 查 `{buildID}/metadata.json` 是否存在 → 命中则跳过构建。缓存按 `teamID` 隔离。一旦某层 cache miss，后续所有层强制重建。

**生命周期管理：**

- 构建成功：写入数据库（rootfs 大小、版本信息），标记状态为 `uploaded`
- 构建失败：自动删除该 `buildID` 下所有已上传对象（`templateStorage.DeleteObjectsWithPrefix`）
- 构建前：调用 `InvalidateUnstartedTemplateBuilds()` 清理旧的 pending 构建

### Modal — 平台托管镜像缓存

- **产物形式**：文件系统快照（平台内部格式），按层缓存（类似 Docker layer 但由平台管理）
- **存储位置**：Modal 平台内部，完全抽象，用户无法直接访问
- **生命周期**：根据镜像定义（Dockerfile 内容、上下文文件哈希）自动缓存，定义变化时自动重建
- **清理方式**：无手动删除机制，`force_build=True` 或 `MODAL_FORCE_BUILD=1` 强制重建
- **费用**：构建按计算时间计费，存储包含在平台费用中

### Runloop — 平台托管 Blueprint

- **产物形式**：容器镜像（平台内部存储），支持基于已有 Blueprint 增量构建（`base_blueprint_id`）
- **存储位置**：Runloop 平台内部，用户通过 API/CLI 管理
- **生命周期**：永久保留，**持续产生存储费用**（官方文档明确提醒）
- **清理方式**：`blueprint.delete()` / API / CLI，官方建议清理旧版本

### GKE — 用户自管 Artifact Registry

- **产物形式**：标准 OCI/Docker 镜像
- **存储位置**：用户自有的 Google Artifact Registry，按 region 存储
- **生命周期**：用户完全自管，支持 cleanup policy（按 tag 状态、版本数、镜像年龄自动清理）
- **清理方式**：`gcloud artifacts docker images delete` / Console / cleanup policy
- **费用**：按 GB/月计费 + 跨 region 拉取的网络费用

### Docker — 本地 Docker daemon

- **产物形式**：标准 Docker 镜像，存储在本地 Docker daemon
- **存储位置**：宿主机本地磁盘
- **生命周期**：持久存在直到 `docker rmi` 或磁盘清理工具（如 `docuum`）自动清理
- **清理方式**：`docker compose down --rmi all` / `docker image prune`

---

## 对比

### 接口与缓存

| 平台 | 接口模式 | 缓存 key | 内容变更检测 |
|------|---------|---------|------------|
| Daytona | `Image.from_dockerfile()` → `create()` | 调用方指定的 Snapshot 名称 | 无 |
| E2B | `from_dockerfile()` → `build()` → `create()` | `name__sha256[:8]` | 自动（目录哈希） |
| Modal | `Image.from_dockerfile()` → `Sandbox.create()` | 平台侧计算（镜像定义哈希） | 自动（平台侧） |
| Runloop | `upload` → `blueprint.create()` → `devbox.create()` | `harbor_{name}_blueprint` | 无 |
| GKE | `gcloud builds submit` → `create_pod()` | `{name}:latest` | 无 |
| Docker | `docker compose build` → `up` | Docker layer cache | 自动（逐层比对） |

### 构建产物与存储

| 平台 | 产物形式 | 存储位置 | 构建上下文传输 | 清理方式 |
|------|---------|---------|--------------|---------|
| Daytona | Snapshot（平台专有格式） | 平台 S3 兼容存储，用户不可直接访问 | ObjectStorage 上传（`daytona-volume-builds` bucket） | `snapshot.delete()` / CLI |
| E2B | Firecracker VM 快照（rootfs + memfile + snapfile） | GCS/S3 bucket（`TEMPLATE_BUCKET_NAME`），按 `buildID` 组织 | SDK 将指令序列化为 steps 发送 API | `template delete` CLI / API；失败自动清理 |
| Modal | 文件系统快照（平台专有） | 平台内部，完全抽象 | SDK 序列化为 protobuf 发送 | 无手动删除；`force_build` 强制重建 |
| Runloop | 容器镜像（平台内部） | 平台内部 | `storage_object.upload_from_dir()` | `blueprint.delete()` / API |
| GKE | 标准 OCI/Docker 镜像 | 用户自有 Artifact Registry | `gcloud builds submit` 上传构建上下文 | `gcloud artifacts docker images delete` / cleanup policy |
| Docker | 标准 Docker 镜像 | 本地 Docker daemon | 本地文件系统直接访问 | `docker image prune` / `docker compose down --rmi all` |

### Harbor 使用方式参考

Harbor 的 `BaseEnvironment` 通过 `start(force_build: bool)` 统一入口，各环境在 `start()` 内部完成从 Dockerfile 到沙箱运行的完整流程。构建上下文统一为 `environment_dir`，Dockerfile 位于 `environment_dir / "Dockerfile"`。
