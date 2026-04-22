"""WebSocket echo server that logs and returns all received request headers."""

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("ws-header-echo")

BLOCKED_WS_HEADER_NAMES = {
    "host",
    "connection",
    "upgrade",
    "sec-websocket-key",
    "sec-websocket-version",
    "sec-websocket-extensions",
    "sec-websocket-protocol",
    "transfer-encoding",
    "te",
    "trailer",
    "keep-alive",
    "proxy-authorization",
    "proxy-connection",
    "content-length",
}

HOST = "0.0.0.0"
PORT = 8080


async def handler(websocket):
    request = websocket.request
    path = request.path if request else "/"
    headers = dict(websocket.request.headers) if request else {}

    logger.info("=" * 60)
    logger.info("New WebSocket connection from %s", websocket.remote_address)
    logger.info("Path: %s", path)
    logger.info("-" * 60)
    logger.info("ALL RECEIVED HEADERS:")
    for key, value in sorted(headers.items()):
        tag = ""
        lower_key = key.lower()
        if lower_key == "origin":
            tag = " [ORIGIN]"
        elif lower_key in BLOCKED_WS_HEADER_NAMES:
            tag = " [BLOCKED]"
        else:
            tag = " [FORWARDED]"
        logger.info("  %-30s : %s%s", key, value, tag)
    logger.info("-" * 60)

    origin = headers.get("origin") or headers.get("Origin")
    blocked = {k: v for k, v in headers.items() if k.lower() in BLOCKED_WS_HEADER_NAMES}
    forwarded = {k: v for k, v in headers.items() if k.lower() not in BLOCKED_WS_HEADER_NAMES and k.lower() != "origin"}

    logger.info("SUMMARY:")
    logger.info("  Origin:            %s", origin or "(not present)")
    logger.info("  Forwarded headers: %d found %s", len(forwarded), list(forwarded.keys()))
    logger.info("  Blocked headers:   %d found %s", len(blocked), list(blocked.keys()))
    logger.info("=" * 60)

    response = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "remote_address": str(websocket.remote_address),
        "headers": headers,
        "analysis": {
            "origin": origin,
            "forwarded_headers": forwarded,
            "blocked_headers": blocked,
            "forwarded_count": len(forwarded),
            "blocked_count": len(blocked),
        },
    }

    await websocket.send(json.dumps(response, indent=2, ensure_ascii=False))

    async for message in websocket:
        logger.info(
            "Received message from client: %s",
            message[:200] if isinstance(message, str) else f"<binary {len(message)} bytes>",
        )
        await websocket.send(json.dumps({"echo": message, "headers": headers}, ensure_ascii=False))


async def main():
    logger.info("Starting WebSocket Header Echo Server on %s:%d", HOST, PORT)
    logger.info("Blocked header names: %s", sorted(BLOCKED_WS_HEADER_NAMES))

    stop = asyncio.get_event_loop().create_future()

    def on_signal():
        logger.info("Shutting down...")
        stop.set_result(None)

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(sig, on_signal)

    async with websockets.serve(handler, HOST, PORT, origins=None):
        logger.info("Server ready. Waiting for connections...")
        await stop


if __name__ == "__main__":
    asyncio.run(main())
