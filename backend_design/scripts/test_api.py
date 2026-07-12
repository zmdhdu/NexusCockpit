#!/usr/bin/env python
"""Quick API test script — verifies chat, vehicle, and streaming endpoints."""
import requests
import json
import sys

BASE = "http://localhost:8000"

def get_token():
    r = requests.post(f"{BASE}/auth/token", json={"user_id": "nexus_dev", "password": ""})
    return r.json()["access_token"]

def test_chat(token, text, cockpit="cockpit-01"):
    headers = {"Authorization": f"Bearer {token}", "X-Cockpit-Id": cockpit}
    r = requests.post(f"{BASE}/chat", json={"text": text, "user_id": "nexus_dev", "session_id": "test"}, headers=headers, timeout=60)
    d = r.json()
    print(f"  Input:    {text}")
    print(f"  Response: {d['response']}")
    print(f"  Action:   {d['action']}")
    print(f"  Intent:   {d['intent']}")
    print(f"  Latency:  {d['latency_ms']:.0f}ms")
    print(f"  Metadata: {json.dumps(d.get('metadata', {}), ensure_ascii=False)}")
    return d

def test_vehicle(token, command, args):
    headers = {"Authorization": f"Bearer {token}", "X-Cockpit-Id": "cockpit-01"}
    r = requests.post(f"{BASE}/vehicle/command", json={"command": command, "arguments": args}, headers=headers, timeout=10)
    d = r.json()
    print(f"  Command:  {command} {json.dumps(args, ensure_ascii=False)}")
    print(f"  Success:  {d['success']}")
    print(f"  Message:  {d['message']}")
    return d

def test_stream(token, text):
    headers = {"Authorization": f"Bearer {token}", "X-Cockpit-Id": "cockpit-01"}
    r = requests.post(f"{BASE}/chat/stream", json={"text": text, "user_id": "nexus_dev", "stream": True}, headers=headers, timeout=60, stream=True)
    chunks = []
    for line in r.iter_lines():
        if line:
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("type") == "chunk":
                    chunks.append(data.get("data", {}).get("chunk", ""))
                elif data.get("type") == "done":
                    print(f"  Stream done: {data.get('data', {}).get('response', '')[:100]}")
                    return
    print(f"  Streamed {len(chunks)} chunks")

if __name__ == "__main__":
    print("=" * 60)
    print("NexusCockpit API Verification")
    print("=" * 60)

    print("\n[1] Getting auth token...")
    token = get_token()
    print(f"  Token: {token[:30]}...")

    print("\n[2] Testing chat — greeting...")
    test_chat(token, "你好")

    print("\n[3] Testing chat — vehicle command (AC)...")
    test_chat(token, "打开空调")

    print("\n[4] Testing chat — vehicle command (temp)...")
    test_chat(token, "把空调调到26度")

    print("\n[5] Testing chat — music...")
    test_chat(token, "播放音乐")

    print("\n[6] Testing vehicle API directly...")
    test_vehicle(token, "vehicle_climate", {"op": "set_temp", "target_temp": 24})
    test_vehicle(token, "vehicle_media", {"op": "play"})
    test_vehicle(token, "vehicle_window", {"op": "open", "position": "all"})

    print("\n[7] Testing streaming chat...")
    test_stream(token, "你好，今天天气怎么样")

    print("\n[8] Testing data platform...")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/dataplatform/overview", headers=headers, timeout=10)
    print(f"  Overview: {r.json()}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
