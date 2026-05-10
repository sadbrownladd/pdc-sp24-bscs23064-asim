import requests
import time
import sys

BASE = "http://127.0.0.1:8000"

G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[1m"
X = "\033[0m"

def pause(msg):
    input(f"\n{Y}>> {msg} press ENTER to run{X}\n")

try:
    requests.get(BASE, timeout=3)
    print(f"{G}Server is running{X}")
except:
    print(f"{R}Server not running. Run: python -m uvicorn backend.main:app --reload{X}")
    sys.exit(1)


pause("TEST 1: Checking X-Student-ID header on every response")

r = requests.get(BASE)
sid = r.headers.get("X-Student-ID", "MISSING")
print(f"Status: {r.status_code}")
print(f"X-Student-ID: {sid}")
print(f"{G}PASS{X}" if sid == "BSCS23064" else f"{R}FAIL{X}")


pause("TEST 2: Two users editing the same document at the same time")

requests.post(f"{BASE}/api/documents/doc1/create", params={"content": "Original content"})
doc = requests.get(f"{BASE}/api/documents/doc1").json()
ver = doc["version"]
print(f"Document created at version {ver}")

r_a = requests.put(f"{BASE}/api/documents/doc1", json={"content": "User A edit", "version": ver})
print(f"User A: {r_a.status_code}")

r_b = requests.put(f"{BASE}/api/documents/doc1", json={"content": "User B edit", "version": ver})
print(f"User B: {r_b.status_code} — {r_b.json().get('detail', {}).get('error', r_b.json())}")
print(f"{G}PASS — conflict caught{X}" if r_b.status_code == 409 else f"{R}FAIL{X}")


pause("TEST 3: Sending the same webhook event twice")

payload = {"event_id": "evt_abc123", "user_id": "user_1", "event_type": "subscription.cancelled"}
r1 = requests.post(f"{BASE}/api/webhooks/clerk", json=payload)
print(f"First:  {r1.json()['status']}")
r2 = requests.post(f"{BASE}/api/webhooks/clerk", json=payload)
print(f"Second: {r2.json()['status']}")
print(f"{G}PASS — duplicate ignored{X}" if r2.json()["status"] == "already_processed" else f"{R}FAIL{X}")


pause("TEST 4: Circuit Breaker - LLM goes down, users still get a response")

requests.post(f"{BASE}/api/llm/reset")
prompt = {"prompt": "Explain photosynthesis"}
s = f = fb = 0

for i in range(1, 11):
    r = requests.post(f"{BASE}/api/llm/generate", json=prompt)
    data = r.json()
    state = data.get("circuit_state", "?")
    if r.status_code == 200:
        s += 1
        print(f"[{i:02d}] {G}OK{X}       circuit={state}")
    elif data.get("source") == "fallback":
        fb += 1
        print(f"[{i:02d}] {Y}FALLBACK{X} circuit={state}  <-- instant, LLM not called")
    else:
        f += 1
        print(f"[{i:02d}] {R}FAIL{X}     circuit={state}")
    time.sleep(0.2)

print(f"\nSuccesses={s}  Failures={f}  Fallbacks={fb}")
print(f"{G}PASS{X}" if fb > 0 else f"{Y}LLM got lucky, run again{X}")
