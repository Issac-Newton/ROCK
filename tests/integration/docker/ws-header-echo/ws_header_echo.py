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

FORWARDED_WS_HEADER_NAMES = {
    "authorization",
    "cookie",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "x-request-id",
    "traceparent",
    "tracestate",
    "eagleeye-traceid",
    "eagleeye-rpcid",
    "eagleeye-userdata",
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
        elif lower_key in FORWARDED_WS_HEADER_NAMES:
            tag = " [WHITELIST]"
        logger.info("  %-30s : %s%s", key, value, tag)
    logger.info("-" * 60)

    whitelist_found = {k: v for k, v in headers.items() if k.lower() in FORWARDED_WS_HEADER_NAMES}
    origin = headers.get("origin") or headers.get("Origin")
    non_whitelist = {
        k: v
        for k, v in headers.items()
        if k.lower() not in FORWARDED_WS_HEADER_NAMES
        and k.lower() != "origin"
        and not k.lower().startswith("sec-websocket")
        and k.lower() not in ("host", "connection", "upgrade")
    }

    logger.info("SUMMARY:")
    logger.info("  Origin:              %s", origin or "(not present)")
    logger.info("  Whitelist headers:   %d found %s", len(whitelist_found), list(whitelist_found.keys()))
    logger.info("  Non-whitelist extra: %d found %s", len(non_whitelist), list(non_whitelist.keys()))
    logger.info("=" * 60)

    response = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "remote_address": str(websocket.remote_address),
        "headers": headers,
        "analysis": {
            "origin": origin,
            "whitelist_headers": whitelist_found,
            "non_whitelist_headers": non_whitelist,
            "whitelist_count": len(whitelist_found),
            "non_whitelist_count": len(non_whitelist),
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
    logger.info("Whitelisted header names: %s", sorted(FORWARDED_WS_HEADER_NAMES))

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
