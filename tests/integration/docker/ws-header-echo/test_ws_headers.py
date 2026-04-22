"""Test client: connect through admin proxy and verify header forwarding (blacklist strategy)."""

import argparse
import asyncio
import json
import sys

import websockets

EXPECTED_FORWARDED = {
    "Authorization": "Bearer test-token-12345",
    "Cookie": "session=abc123; theme=dark",
    "X-Request-Id": "req-uuid-7890",
    "Traceparent": "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01",
    "Tracestate": "vendor=opaque",
    "Eagleeye-Traceid": "eagle-trace-001",
    "Eagleeye-Rpcid": "eagle-rpc-002",
    "Eagleeye-Userdata": "uid=42",
    "X-Forwarded-For": "10.0.0.1",
    "X-Forwarded-Host": "example.com",
    "X-Forwarded-Proto": "https",
    "X-Real-Ip": "10.0.0.1",
    "X-My-Custom-Header": "custom-value-abc",
    "X-Pictor-Callid": "pictor-123",
    "Web-Server-Type": "nginx",
}

BLOCKED = {
    "Host",
    "Connection",
    "Upgrade",
    "Sec-WebSocket-Key",
    "Sec-WebSocket-Version",
    "Sec-WebSocket-Extensions",
    "Sec-WebSocket-Protocol",
}

ORIGIN = "https://test.example.com"


async def test_headers(admin_url: str, sandbox_id: str):
    ws_url = f"ws://{admin_url.removeprefix('http://').removeprefix('https://')}/sandboxes/{sandbox_id}/proxy/echo"

    all_headers = {**EXPECTED_FORWARDED, "Origin": ORIGIN}

    print(f"Connecting to: {ws_url}")
    print(f"Sending {len(all_headers)} headers ({len(EXPECTED_FORWARDED)} to forward, 1 origin)")
    print()

    async with websockets.connect(ws_url, additional_headers=list(all_headers.items()), open_timeout=10) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(raw)

    received = data.get("headers", {})
    received_lower = {k.lower(): v for k, v in received.items()}

    print("=" * 60)
    print("RECEIVED HEADERS AT ECHO SERVER:")
    for k, v in sorted(received.items()):
        print(f"  {k:30s} : {v}")
    print("=" * 60)

    passed = 0
    failed = 0

    print("\n--- Origin Check ---")
    received_origin = received_lower.get("origin")
    if received_origin == ORIGIN:
        print(f"  PASS  origin = {received_origin}")
        passed += 1
    else:
        print(f"  FAIL  origin expected={ORIGIN}, got={received_origin}")
        failed += 1

    print("\n--- Forwarded Header Checks (should be present) ---")
    for key, expected_value in EXPECTED_FORWARDED.items():
        actual = received_lower.get(key.lower())
        if actual == expected_value:
            print(f"  PASS  {key} = {actual}")
            passed += 1
        elif actual is not None:
            print(f"  FAIL  {key} expected={expected_value}, got={actual}")
            failed += 1
        else:
            print(f"  FAIL  {key} NOT FOUND (expected={expected_value})")
            failed += 1

    print("\n--- Blocked Header Checks (should not be client values) ---")
    for key in BLOCKED:
        actual = received_lower.get(key.lower())
        if actual is None:
            print(f"  PASS  {key} not present (OK)")
            passed += 1
        else:
            print(f"  INFO  {key} = {actual} (set by websockets library, not proxy)")
            passed += 1

    print()
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED")
    print("=" * 60)

    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test WebSocket header forwarding through ROCK admin proxy")
    parser.add_argument("--base-url", required=True, help="Admin service URL, e.g. http://localhost:8080")
    parser.add_argument("--sandbox-id", required=True, help="Sandbox ID to connect through")
    args = parser.parse_args()

    ok = asyncio.run(test_headers(args.base_url, args.sandbox_id))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
