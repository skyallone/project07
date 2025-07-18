import requests
import sys

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost"

endpoints = ["/", "/chatbot"]

success = True
for ep in endpoints:
    url = BASE_URL.rstrip("/") + ep
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"[OK] {url} - {resp.status_code}")
        else:
            print(f"[FAIL] {url} - {resp.status_code}")
            success = False
    except Exception as e:
        print(f"[ERROR] {url} - {e}")
        success = False

if not success:
    sys.exit(1) 