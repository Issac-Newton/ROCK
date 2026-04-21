# WebSocket Header Echo — 验证 Proxy Header 转发

用于验证 ROCK Admin WebSocket 代理是否正确转发白名单 headers。

## 构建镜像

```bash
docker build -t ws-header-echo tests/integration/docker/ws-header-echo/
```

## 独立测试（不经过 ROCK）

```bash
# 启动 echo server
docker run --rm -p 8080:8080 ws-header-echo

# 另一个终端，用 websocat / wscat 连接
wscat -c ws://localhost:8080/test -H "Authorization: Bearer abc" -H "X-Custom: should-drop"
```

## 通过 ROCK Sandbox 测试

```bash
# 1. 用该镜像创建并启动 sandbox
#    (通过 SDK 或 CLI，image 指定为 ws-header-echo)

# 2. 在 sandbox 内启动 echo server
sandbox.exec("nohup python /app/ws_header_echo.py > /tmp/ws_echo.log 2>&1 &")

# 3. 运行测试客户端
python tests/integration/docker/ws-header-echo/test_ws_headers.py \
    --base-url http://localhost:8080 \
    --sandbox-id <SANDBOX_ID>

# 4. 查看 sandbox 内 echo server 的日志（可选）
sandbox.exec("cat /tmp/ws_echo.log")
```

## 验证内容

echo server 收到连接后会：
1. 在日志中打印所有收到的 request headers，标注 `[WHITELIST]` / `[ORIGIN]`
2. 将 headers 以 JSON 返回给客户端

test client 会检查：
- 12 个白名单 headers + Origin 是否到达
- 非白名单 headers 是否被过滤
