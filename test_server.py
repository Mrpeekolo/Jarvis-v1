import subprocess
import time
import sys
import httpx

def test_startup():
    proc = subprocess.Popen([sys.executable, "main.py"], cwd="c:/Users/Lil spooky/test/jarvis")
    try:
        time.sleep(3)
        with httpx.Client(timeout=5.0) as client:
            resp = client.get("http://127.0.0.1:8765/api/status")
            print("Status Code:", resp.status_code)
            print("Response:", resp.json())
            assert resp.status_code == 200
            
            # Test UI index file is served
            ui_resp = client.get("http://127.0.0.1:8765/")
            assert ui_resp.status_code == 200
            assert "JARVIS CORE" in ui_resp.text
            print("[PASS] Web UI and API Status verified!")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    test_startup()
