"""SAB Server - standalone launcher"""
import subprocess
import sys
import time
import urllib.request

PORT = 3000

def is_running():
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=2)
        return True
    except Exception:
        return False

if __name__ == "__main__":
    if is_running():
        print(f"SAB already running at http://localhost:{PORT}")
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
        sys.exit(0)

    print(f"Starting SAB on http://localhost:{PORT} ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sab.web.server:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=r"C:\Users\786 COMPUTERS\Downloads\sab",
    )

    for _ in range(30):
        time.sleep(1)
        if is_running():
            print(f"SAB running at http://localhost:{PORT}")
            import webbrowser
            webbrowser.open(f"http://localhost:{PORT}")
            break
    else:
        print("Server failed to start")
        proc.kill()
        sys.exit(1)

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
